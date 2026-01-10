"""Base blob storage interface.

Defines the abstract interface for blob storage backends.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import BinaryIO
from uuid import uuid4


@dataclass
class BlobMetadata:
    """Metadata for a stored blob."""

    id: str = field(default_factory=lambda: str(uuid4()))
    submodel_id: str = ""
    id_short_path: str = ""
    storage_type: str = "local"
    storage_uri: str = ""
    content_type: str = "application/octet-stream"
    filename: str | None = None
    size_bytes: int = 0
    content_hash: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BlobStorage(ABC):
    """Abstract base class for blob storage backends."""

    # Maximum size for inline storage (elements smaller than this stay in JSONB)
    # Default: 64KB - elements larger than this are externalized
    INLINE_THRESHOLD: int = 64 * 1024

    @abstractmethod
    async def store(
        self,
        submodel_id: str,
        id_short_path: str,
        content: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        filename: str | None = None,
    ) -> BlobMetadata:
        """Store a blob and return its metadata.

        Args:
            submodel_id: The parent submodel's internal UUID
            id_short_path: Path to the element (e.g., "Collection.Blob")
            content: Binary content or file-like object
            content_type: MIME type of the content
            filename: Optional original filename

        Returns:
            BlobMetadata with storage location and hash
        """
        ...

    @abstractmethod
    async def retrieve(self, metadata: BlobMetadata) -> bytes:
        """Retrieve blob content by metadata.

        Args:
            metadata: Blob metadata containing storage location

        Returns:
            Binary content

        Raises:
            FileNotFoundError: If blob not found
        """
        ...

    @abstractmethod
    def stream(self, metadata: BlobMetadata) -> AsyncIterator[bytes]:
        """Stream blob content in chunks.

        Args:
            metadata: Blob metadata containing storage location

        Yields:
            Chunks of binary content

        Raises:
            FileNotFoundError: If blob not found
        """
        ...

    @abstractmethod
    async def delete(self, metadata: BlobMetadata) -> bool:
        """Delete a blob.

        Args:
            metadata: Blob metadata containing storage location

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def exists(self, metadata: BlobMetadata) -> bool:
        """Check if a blob exists.

        Args:
            metadata: Blob metadata containing storage location

        Returns:
            True if exists, False otherwise
        """
        ...

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def should_externalize(content: bytes | None, content_type: str) -> bool:
        """Determine if content should be externalized to blob storage.

        Args:
            content: Binary content
            content_type: MIME type

        Returns:
            True if should be stored in blob storage, False if inline is OK
        """
        if content is None:
            return False

        # Always externalize large content
        if len(content) > BlobStorage.INLINE_THRESHOLD:
            return True

        # Always externalize certain content types that tend to grow
        externalize_types = {
            "application/pdf",
            "application/zip",
            "application/gzip",
            "application/x-tar",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/tiff",
            "video/",
            "audio/",
            "model/",  # 3D models
        }

        for ext_type in externalize_types:
            if content_type.startswith(ext_type):
                return True

        return False
