"""Azure Blob Storage backend."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator, BinaryIO, cast
from uuid import uuid4

from titan.storage.base import BlobMetadata, BlobStorage


class AzureBlobStorage(BlobStorage):
    """Azure Blob Storage implementation using azure-storage-blob aio client."""

    def __init__(
        self,
        container: str,
        prefix: str = "",
        connection_string: str | None = None,
        account_url: str | None = None,
        credential: str | None = None,
        chunk_size: int = 8 * 1024 * 1024,  # 8MB chunks
    ) -> None:
        self.container = container
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.connection_string = connection_string
        self.account_url = account_url
        self.credential = credential
        self.chunk_size = chunk_size
        self._client: Any | None = None

    async def _get_client(self) -> Any:
        """Get or create BlobServiceClient."""
        if self._client is None:
            try:
                from azure.storage.blob.aio import BlobServiceClient
            except ImportError as exc:
                raise RuntimeError(
                    "azure-storage-blob is required for Azure blob storage"
                ) from exc

            if self.connection_string:
                self._client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
            elif self.account_url:
                self._client = BlobServiceClient(
                    account_url=self.account_url, credential=self.credential
                )
            else:
                raise ValueError(
                    "Azure storage requires AZURE_STORAGE_CONNECTION_STRING or AZURE_ACCOUNT_URL"
                )

        return self._client

    def _build_key(self, submodel_id: str, blob_id: str) -> str:
        """Build blob name with sharding."""
        shard = submodel_id[:2] if len(submodel_id) >= 2 else "00"
        return f"{self.prefix}{shard}/{submodel_id}/{blob_id}"

    def _parse_uri(self, uri: str) -> tuple[str, str]:
        """Parse storage URI to get container and blob name."""
        if uri.startswith("azure://"):
            parts = uri[8:].split("/", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
        return self.container, uri

    async def store(
        self,
        submodel_id: str,
        id_short_path: str,
        content: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        filename: str | None = None,
    ) -> BlobMetadata:
        """Store a blob in Azure Blob Storage."""
        blob_id = str(uuid4())
        blob_name = self._build_key(submodel_id, blob_id)

        if isinstance(content, bytes):
            content_bytes = content
        else:
            content_bytes = content.read()

        content_hash = self.compute_hash(content_bytes)
        size_bytes = len(content_bytes)

        client = await self._get_client()
        container_client = client.get_container_client(self.container)
        blob_client = container_client.get_blob_client(blob_name)

        from azure.storage.blob import ContentSettings

        await blob_client.upload_blob(
            content_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
            metadata={
                "submodel-id": submodel_id,
                "id-short-path": id_short_path,
                "content-hash": content_hash,
            },
        )

        now = datetime.now(timezone.utc)
        return BlobMetadata(
            id=blob_id,
            submodel_id=submodel_id,
            id_short_path=id_short_path,
            storage_type="azure",
            storage_uri=f"azure://{self.container}/{blob_name}",
            content_type=content_type,
            filename=filename,
            size_bytes=size_bytes,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
        )

    async def retrieve(self, metadata: BlobMetadata) -> bytes:
        """Retrieve blob content from Azure Blob Storage."""
        container, blob_name = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        try:
            stream = await blob_client.download_blob()
            data = await stream.readall()
            return cast(bytes, data)
        except Exception as exc:
            from azure.core.exceptions import ResourceNotFoundError

            if isinstance(exc, ResourceNotFoundError):
                raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")
            raise

    async def stream(self, metadata: BlobMetadata) -> AsyncIterator[bytes]:
        """Stream blob content from Azure Blob Storage in chunks."""
        container, blob_name = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        try:
            stream = await blob_client.download_blob()
            async for chunk in stream.chunks():
                yield cast(bytes, chunk)
        except Exception as exc:
            from azure.core.exceptions import ResourceNotFoundError

            if isinstance(exc, ResourceNotFoundError):
                raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")
            raise

    async def delete(self, metadata: BlobMetadata) -> bool:
        """Delete a blob from Azure Blob Storage."""
        container, blob_name = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        try:
            await blob_client.delete_blob()
            return True
        except Exception as exc:
            from azure.core.exceptions import ResourceNotFoundError

            if isinstance(exc, ResourceNotFoundError):
                return False
            raise

    async def exists(self, metadata: BlobMetadata) -> bool:
        """Check if a blob exists in Azure Blob Storage."""
        container, blob_name = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        blob_client = client.get_blob_client(container=container, blob=blob_name)

        try:
            return cast(bool, await blob_client.exists())
        except Exception:
            return False

    async def close(self) -> None:
        """Close the underlying client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
