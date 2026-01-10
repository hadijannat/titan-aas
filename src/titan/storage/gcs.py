"""Google Cloud Storage blob storage backend."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, BinaryIO, cast
from uuid import uuid4

from titan.storage.base import BlobMetadata, BlobStorage


class GcsBlobStorage(BlobStorage):
    """GCS blob storage implementation.

    Uses google-cloud-storage with asyncio.to_thread for non-blocking I/O.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        project: str | None = None,
        credentials_path: str | None = None,
        chunk_size: int = 8 * 1024 * 1024,  # 8MB chunks
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.project = project
        self.credentials_path = credentials_path
        self.chunk_size = chunk_size
        self._client: Any | None = None

    async def _get_client(self) -> Any:
        """Get or create GCS client."""
        if self._client is None:
            try:
                from google.cloud import storage
            except ImportError as exc:
                raise RuntimeError("google-cloud-storage is required for GCS blob storage") from exc

            if self.credentials_path:
                self._client = storage.Client.from_service_account_json(
                    self.credentials_path, project=self.project
                )
            else:
                self._client = storage.Client(project=self.project)
        return self._client

    def _build_key(self, submodel_id: str, blob_id: str) -> str:
        """Build object key with sharding."""
        shard = submodel_id[:2] if len(submodel_id) >= 2 else "00"
        return f"{self.prefix}{shard}/{submodel_id}/{blob_id}"

    def _parse_uri(self, uri: str) -> str:
        """Parse storage URI to get object key."""
        if uri.startswith("gs://"):
            parts = uri[5:].split("/", 1)
            if len(parts) > 1:
                return parts[1]
        return uri

    async def store(
        self,
        submodel_id: str,
        id_short_path: str,
        content: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        filename: str | None = None,
    ) -> BlobMetadata:
        """Store a blob in GCS."""
        blob_id = str(uuid4())
        key = self._build_key(submodel_id, blob_id)

        if isinstance(content, bytes):
            content_bytes = content
        else:
            content_bytes = content.read()

        content_hash = self.compute_hash(content_bytes)
        size_bytes = len(content_bytes)

        client = await self._get_client()
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(key)
        blob.metadata = {
            "submodel-id": submodel_id,
            "id-short-path": id_short_path,
            "content-hash": content_hash,
        }
        await asyncio.to_thread(blob.upload_from_string, content_bytes, content_type=content_type)

        now = datetime.now(timezone.utc)
        return BlobMetadata(
            id=blob_id,
            submodel_id=submodel_id,
            id_short_path=id_short_path,
            storage_type="gcs",
            storage_uri=f"gs://{self.bucket}/{key}",
            content_type=content_type,
            filename=filename,
            size_bytes=size_bytes,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
        )

    async def retrieve(self, metadata: BlobMetadata) -> bytes:
        """Retrieve blob content from GCS."""
        key = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(key)

        exists = await asyncio.to_thread(blob.exists)
        if not exists:
            raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")

        data = await asyncio.to_thread(blob.download_as_bytes)
        return cast(bytes, data)

    async def stream(self, metadata: BlobMetadata) -> AsyncIterator[bytes]:
        """Stream blob content from GCS in chunks."""
        key = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(key)

        exists = await asyncio.to_thread(blob.exists)
        if not exists:
            raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")

        open_fn = getattr(blob, "open", None)
        if callable(open_fn):
            file_obj = await asyncio.to_thread(open_fn, "rb")
            try:
                while True:
                    chunk = await asyncio.to_thread(file_obj.read, self.chunk_size)
                    if not chunk:
                        break
                    yield cast(bytes, chunk)
            finally:
                await asyncio.to_thread(file_obj.close)
            return

        # Fallback: download and yield in chunks (not true streaming)
        data = await asyncio.to_thread(blob.download_as_bytes)
        for i in range(0, len(data), self.chunk_size):
            yield cast(bytes, data[i : i + self.chunk_size])

    async def delete(self, metadata: BlobMetadata) -> bool:
        """Delete a blob from GCS."""
        key = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(key)

        exists = await asyncio.to_thread(blob.exists)
        if not exists:
            return False

        await asyncio.to_thread(blob.delete)
        return True

    async def exists(self, metadata: BlobMetadata) -> bool:
        """Check if a blob exists in GCS."""
        key = self._parse_uri(metadata.storage_uri)

        client = await self._get_client()
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(key)
        return cast(bool, await asyncio.to_thread(blob.exists))
