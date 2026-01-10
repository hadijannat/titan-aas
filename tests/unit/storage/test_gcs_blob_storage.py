"""Unit tests for GCS blob storage backend."""

from __future__ import annotations

import io
from typing import Any

import pytest

from titan.storage.gcs import GcsBlobStorage


class FakeGcsBlob:
    def __init__(self, store: dict[str, bytes], name: str) -> None:
        self._store = store
        self.name = name
        self.metadata: dict[str, str] | None = None

    def upload_from_string(self, data: bytes, content_type: str | None = None) -> None:
        self._store[self.name] = data

    def download_as_bytes(self) -> bytes:
        return self._store[self.name]

    def exists(self) -> bool:
        return self.name in self._store

    def delete(self) -> None:
        self._store.pop(self.name, None)

    def open(self, mode: str = "rb") -> io.BytesIO:
        return io.BytesIO(self._store.get(self.name, b""))


class FakeGcsBucket:
    def __init__(self, store: dict[str, bytes]) -> None:
        self._store = store

    def blob(self, name: str) -> FakeGcsBlob:
        return FakeGcsBlob(self._store, name)


class FakeGcsClient:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def bucket(self, name: str) -> FakeGcsBucket:
        return FakeGcsBucket(self._store)


@pytest.mark.asyncio
async def test_gcs_blob_storage_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Store, retrieve, stream, and delete using mocked GCS storage."""
    client = FakeGcsClient()

    async def get_client() -> Any:
        return client

    storage = GcsBlobStorage(bucket="test-bucket")
    monkeypatch.setattr(storage, "_get_client", get_client)

    content = b"titan-gcs-blob"
    metadata = await storage.store(
        submodel_id="urn:test:submodel:gcs",
        id_short_path="Blob3",
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
