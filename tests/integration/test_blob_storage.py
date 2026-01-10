"""Integration tests for blob storage backends."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from uuid import uuid4

import aioboto3
import pytest

from tests.integration.docker_utils import run_container
from titan.storage.local import LocalBlobStorage
from titan.storage.s3 import S3BlobStorage


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
async def test_s3_blob_storage_roundtrip(docker_client) -> None:
    """Store, retrieve, stream, and delete using MinIO (S3 compatible)."""
    access_key = "minioadmin"
    secret_key = "minioadmin"

    env = {
        "MINIO_ROOT_USER": access_key,
        "MINIO_ROOT_PASSWORD": secret_key,
    }
    ports = {"9000/tcp": None}

    with run_container(
        docker_client,
        "minio/minio:latest",
        env=env,
        ports=ports,
        command="server /data --console-address :9001",
    ) as minio:
        host = minio.host
        port = minio.port(9000)
        endpoint = f"http://{host}:{port}"

        bucket = f"titan-test-{uuid4().hex}"

        await _wait_for_minio(endpoint, access_key, secret_key)

        session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )
        async with session.client("s3", endpoint_url=endpoint) as s3:
            await s3.create_bucket(Bucket=bucket)

        storage = S3BlobStorage(
            bucket=bucket,
            endpoint_url=endpoint,
            region_name="us-east-1",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
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


async def _wait_for_minio(endpoint: str, access_key: str, secret_key: str) -> None:
    """Wait for MinIO to accept S3 requests."""
    deadline = time.monotonic() + 30.0
    session = aioboto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )
    while True:
        try:
            async with session.client("s3", endpoint_url=endpoint) as s3:
                await s3.list_buckets()
            return
        except Exception:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.5)
