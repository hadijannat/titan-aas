"""Object storage module for Titan-AAS.

Provides blob storage for large File/Blob elements:
- Local filesystem storage (default)
- S3-compatible storage (MinIO, AWS S3)
- Azure Blob Storage (future)

The "Binary Blob Trap" fix:
- Large binaries are externalized from JSONB
- Content is streamed directly to/from storage
- Only metadata is stored in PostgreSQL
"""

from titan.storage.base import BlobMetadata, BlobStorage
from titan.storage.local import LocalBlobStorage
from titan.storage.s3 import S3BlobStorage

__all__ = [
    "BlobStorage",
    "BlobMetadata",
    "LocalBlobStorage",
    "S3BlobStorage",
]
