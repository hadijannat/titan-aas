"""Integration tests for blob storage backends."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import aioboto3
import pytest

from titan.storage.local import LocalBlobStorage
from titan.storage.s3 import S3BlobStorage

testcontainers_minio = pytest.importorskip("testcontainers.minio")
MinioContainer = testcontainers_minio.MinioContainer


@pytest.mark.asyncio
async def test_local_blob_storage_roundtrip(tmp_path: Path) -> None:
    """Store, retrieve, stream, and delete using local storage."""
    storage = LocalBlobStorage(base_path=tmp_path)
    content = b"titan-local-blob"

    metadata = await storage.store(
        submodel_id="urn:test:submodel:local",
        id_short_path="Blob1",
        content=content,
        content_type="application/octet-stream",
        filename="blob.bin",
    )

    assert await storage.exists(metadata)
    assert await storage.retrieve(metadata) == content

    streamed = b"".join([chunk async for chunk in storage.stream(metadata)])
    assert streamed == content

    assert await storage.delete(metadata) is True
    assert not await storage.exists(metadata)


@pytest.mark.asyncio
async def test_s3_blob_storage_roundtrip() -> None:
    """Store, retrieve, stream, and delete using MinIO (S3 compatible)."""
    with MinioContainer() as minio:
        host = minio.get_container_host_ip()
        port = minio.get_exposed_port(minio.port)
        endpoint = f"http://{host}:{port}"

        bucket = f"titan-test-{uuid4().hex}"

        session = aioboto3.Session(
            aws_access_key_id=minio.access_key,
            aws_secret_access_key=minio.secret_key,
            region_name="us-east-1",
        )
        async with session.client("s3", endpoint_url=endpoint) as s3:
            await s3.create_bucket(Bucket=bucket)

        storage = S3BlobStorage(
            bucket=bucket,
            endpoint_url=endpoint,
            region_name="us-east-1",
            aws_access_key_id=minio.access_key,
            aws_secret_access_key=minio.secret_key,
        )

        content = b"titan-s3-blob"
        metadata = await storage.store(
            submodel_id="urn:test:submodel:s3",
            id_short_path="Blob2",
            content=content,
            content_type="application/octet-stream",
            filename="blob.bin",
        )

        assert await storage.exists(metadata)
        assert await storage.retrieve(metadata) == content

        streamed = b"".join([chunk async for chunk in storage.stream(metadata)])
        assert streamed == content

        assert await storage.delete(metadata) is True
        assert not await storage.exists(metadata)
