"""Blob storage factory for Titan-AAS."""

from __future__ import annotations

from titan.config import settings
from titan.storage.base import BlobStorage
from titan.storage.local import LocalBlobStorage
from titan.storage.s3 import S3BlobStorage

_storage: BlobStorage | None = None


def get_blob_storage() -> BlobStorage:
    """Return a singleton BlobStorage based on settings."""
    global _storage
    if _storage is not None:
        return _storage

    storage_type = settings.blob_storage_type.lower()
    if storage_type in {"s3", "minio"}:
        if not settings.s3_bucket:
            raise ValueError("S3_BUCKET is required for blob_storage_type='s3' or 'minio'")
        _storage = S3BlobStorage(
            bucket=settings.s3_bucket,
            prefix=settings.s3_prefix,
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )
    elif storage_type == "local":
        _storage = LocalBlobStorage(base_path=settings.blob_storage_path)
    else:
        raise ValueError("Unsupported blob_storage_type. Supported values: local, s3, minio.")

    # Configure inline threshold from settings
    BlobStorage.INLINE_THRESHOLD = settings.blob_inline_threshold
    return _storage
