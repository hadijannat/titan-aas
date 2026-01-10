"""S3-compatible blob storage backend.

Supports:
- AWS S3
- MinIO
- DigitalOcean Spaces
- Any S3-compatible object storage
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncIterator, BinaryIO, cast

if TYPE_CHECKING:
    import aioboto3

from titan.storage.base import BlobMetadata, BlobStorage


class S3BlobStorage(BlobStorage):
    """S3-compatible blob storage implementation.

    Uses aioboto3 for async S3 operations with streaming support.

    Configuration via:
    - bucket: S3 bucket name
    - prefix: Optional key prefix (e.g., "titan/blobs/")
    - endpoint_url: For non-AWS S3-compatible services
    - region_name: AWS region
    - credentials: via AWS SDK defaults or explicit aws_access_key_id/secret_access_key
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        region_name: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        chunk_size: int = 8 * 1024 * 1024,  # 8MB chunks for streaming
    ):
        """Initialize S3 blob storage.

        Args:
            bucket: S3 bucket name
            prefix: Key prefix for all blobs (optional)
            endpoint_url: Custom endpoint for S3-compatible services
            region_name: AWS region
            aws_access_key_id: Access key (optional, uses SDK defaults)
            aws_secret_access_key: Secret key (optional, uses SDK defaults)
            chunk_size: Chunk size for streaming operations
        """
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.chunk_size = chunk_size
        self._session: "aioboto3.Session | None" = None

    async def _get_session(self) -> "aioboto3.Session":
        """Get or create aioboto3 session."""
        if self._session is None:
            import aioboto3

            self._session = aioboto3.Session(
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.region_name,
            )
        return self._session

    def _build_key(self, submodel_id: str, blob_id: str) -> str:
        """Build S3 object key.

        Structure: {prefix}{submodel_id[:2]}/{submodel_id}/{blob_id}
        Using first 2 chars of submodel_id for sharding.
        """
        shard = submodel_id[:2] if len(submodel_id) >= 2 else "00"
        return f"{self.prefix}{shard}/{submodel_id}/{blob_id}"

    def _parse_uri(self, uri: str) -> str:
        """Parse storage URI to get S3 key.

        URI format: s3://{bucket}/{key}
        """
        if uri.startswith("s3://"):
            # Remove s3://bucket/ prefix
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
        """Store a blob in S3."""
        from uuid import uuid4

        blob_id = str(uuid4())
        key = self._build_key(submodel_id, blob_id)

        # Convert to bytes if needed
        if hasattr(content, "read"):
            content_bytes = content.read()
        else:
            content_bytes = content

        content_hash = self.compute_hash(content_bytes)
        size_bytes = len(content_bytes)

        session = await self._get_session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content_bytes,
                ContentType=content_type,
                Metadata={
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
            storage_type="s3",
            storage_uri=f"s3://{self.bucket}/{key}",
            content_type=content_type,
            filename=filename,
            size_bytes=size_bytes,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
        )

    async def retrieve(self, metadata: BlobMetadata) -> bytes:
        """Retrieve blob content from S3."""
        key = self._parse_uri(metadata.storage_uri)

        session = await self._get_session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            try:
                response = await s3.get_object(
                    Bucket=self.bucket,
                    Key=key,
                )
                async with response["Body"] as stream:
                    data = await stream.read()
                    return cast(bytes, data)
            except s3.exceptions.NoSuchKey:
                raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")

    async def stream(self, metadata: BlobMetadata) -> AsyncIterator[bytes]:
        """Stream blob content from S3 in chunks."""
        key = self._parse_uri(metadata.storage_uri)

        session = await self._get_session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            try:
                response = await s3.get_object(
                    Bucket=self.bucket,
                    Key=key,
                )
                async with response["Body"] as stream:
                    while True:
                        chunk = await stream.read(self.chunk_size)
                        if not chunk:
                            break
                        yield chunk
            except s3.exceptions.NoSuchKey:
                raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")

    async def delete(self, metadata: BlobMetadata) -> bool:
        """Delete a blob from S3."""
        key = self._parse_uri(metadata.storage_uri)

        session = await self._get_session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            try:
                await s3.delete_object(
                    Bucket=self.bucket,
                    Key=key,
                )
                return True
            except Exception:
                return False

    async def exists(self, metadata: BlobMetadata) -> bool:
        """Check if a blob exists in S3."""
        key = self._parse_uri(metadata.storage_uri)

        session = await self._get_session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            try:
                await s3.head_object(
                    Bucket=self.bucket,
                    Key=key,
                )
                return True
            except Exception:
                return False

    async def get_presigned_url(
        self,
        metadata: BlobMetadata,
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned URL for direct download.

        Args:
            metadata: Blob metadata
            expires_in: URL expiration time in seconds (default 1 hour)

        Returns:
            Presigned URL for direct download
        """
        key = self._parse_uri(metadata.storage_uri)

        session = await self._get_session()

        async with session.client(
            "s3",
            endpoint_url=self.endpoint_url,
        ) as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return cast(str, url)

    async def close(self) -> None:
        """Close the S3 session."""
        # aioboto3 sessions don't need explicit closing
        self._session = None
