"""Local filesystem blob storage.

Stores blobs in a local directory structure:
    {base_path}/{submodel_id[:2]}/{submodel_id}/{blob_id}

This provides:
- Simple deployment (no external services)
- Reasonable performance for moderate workloads
- Easy backup and inspection
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast
from uuid import uuid4

import aiofiles  # type: ignore[import-untyped]
import aiofiles.os  # type: ignore[import-untyped]

from titan.storage.base import BlobMetadata, BlobStorage

logger = logging.getLogger(__name__)


class LocalBlobStorage(BlobStorage):
    """Local filesystem blob storage backend."""

    CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming

    def __init__(self, base_path: str | Path = "/var/lib/titan/blobs"):
        """Initialize local blob storage.

        Args:
            base_path: Base directory for blob storage
        """
        self.base_path = Path(base_path)

    async def _ensure_directory(self, path: Path) -> None:
        """Ensure directory exists."""
        if not await aiofiles.os.path.exists(path):
            await aiofiles.os.makedirs(path, exist_ok=True)

    def _get_blob_path(self, submodel_id: str, blob_id: str) -> Path:
        """Get the full path for a blob.

        Uses sharding based on first 2 chars of submodel_id to avoid
        too many files in a single directory.
        """
        shard = submodel_id[:2] if len(submodel_id) >= 2 else "00"
        return self.base_path / shard / submodel_id / blob_id

    async def store(
        self,
        submodel_id: str,
        id_short_path: str,
        content: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        filename: str | None = None,
    ) -> BlobMetadata:
        """Store a blob in the local filesystem."""
        blob_id = str(uuid4())
        blob_path = self._get_blob_path(submodel_id, blob_id)

        # Ensure directory exists
        await self._ensure_directory(blob_path.parent)

        # Get content as bytes
        if isinstance(content, bytes):
            content_bytes = content
        else:
            content_bytes = content.read()

        # Compute hash and size
        content_hash = self.compute_hash(content_bytes)
        size_bytes = len(content_bytes)

        # Write to file
        async with aiofiles.open(blob_path, "wb") as f:
            await f.write(content_bytes)

        now = datetime.now(UTC)

        logger.debug(
            f"Stored blob {blob_id} for submodel {submodel_id} at {blob_path} ({size_bytes} bytes)"
        )

        return BlobMetadata(
            id=blob_id,
            submodel_id=submodel_id,
            id_short_path=id_short_path,
            storage_type="local",
            storage_uri=str(blob_path),
            content_type=content_type,
            filename=filename,
            size_bytes=size_bytes,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
        )

    async def retrieve(self, metadata: BlobMetadata) -> bytes:
        """Retrieve blob content from local filesystem."""
        blob_path = Path(metadata.storage_uri)

        if not await aiofiles.os.path.exists(blob_path):
            raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")

        async with aiofiles.open(blob_path, "rb") as f:
            content = await f.read()

        return cast(bytes, content)

    async def stream(self, metadata: BlobMetadata) -> AsyncIterator[bytes]:
        """Stream blob content in chunks."""
        blob_path = Path(metadata.storage_uri)

        if not await aiofiles.os.path.exists(blob_path):
            raise FileNotFoundError(f"Blob not found: {metadata.storage_uri}")

        async with aiofiles.open(blob_path, "rb") as f:
            while True:
                chunk = await f.read(self.CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk

    async def delete(self, metadata: BlobMetadata) -> bool:
        """Delete a blob from local filesystem."""
        blob_path = Path(metadata.storage_uri)

        if not await aiofiles.os.path.exists(blob_path):
            return False

        await aiofiles.os.remove(blob_path)
        logger.debug(f"Deleted blob at {blob_path}")

        # Try to remove empty parent directories
        try:
            parent = blob_path.parent
            if await aiofiles.os.path.exists(parent):
                entries = await aiofiles.os.listdir(parent)
                if not entries:
                    await aiofiles.os.rmdir(parent)
        except OSError:
            pass  # Ignore errors cleaning up directories

        return True

    async def exists(self, metadata: BlobMetadata) -> bool:
        """Check if a blob exists in local filesystem."""
        blob_path = Path(metadata.storage_uri)
        return cast(bool, await aiofiles.os.path.exists(blob_path))


# Global storage instance
_storage: LocalBlobStorage | None = None


def get_blob_storage() -> LocalBlobStorage:
    """Get the global blob storage instance."""
    global _storage

    if _storage is None:
        from titan.config import settings

        # Use a configurable path or default
        base_path = getattr(settings, "blob_storage_path", "/var/lib/titan/blobs")
        _storage = LocalBlobStorage(base_path=base_path)

    return _storage
