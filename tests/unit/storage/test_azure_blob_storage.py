"""Unit tests for Azure blob storage backend."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from titan.storage.azure import AzureBlobStorage


def _install_azure_stubs() -> None:
    """Install minimal azure.* stubs to satisfy runtime imports."""
    azure_mod = types.ModuleType("azure")
    storage_mod = types.ModuleType("azure.storage")
    blob_mod = types.ModuleType("azure.storage.blob")

    class ContentSettings:
        def __init__(self, content_type: str | None = None) -> None:
            self.content_type = content_type

    blob_mod.ContentSettings = ContentSettings

    azure_mod.storage = storage_mod
    storage_mod.blob = blob_mod

    sys.modules.setdefault("azure", azure_mod)
    sys.modules.setdefault("azure.storage", storage_mod)
    sys.modules.setdefault("azure.storage.blob", blob_mod)


class FakeAzureDownload:
    def __init__(self, data: bytes, chunk_size: int = 4) -> None:
        self._data = data
        self._chunk_size = chunk_size

    async def readall(self) -> bytes:
        return self._data

    async def chunks(self):
        for i in range(0, len(self._data), self._chunk_size):
            yield self._data[i : i + self._chunk_size]


class FakeAzureBlobClient:
    def __init__(self, store: dict[str, bytes], name: str) -> None:
        self._store = store
        self._name = name

    async def upload_blob(self, data: bytes, **kwargs: Any) -> None:
        self._store[self._name] = data

    async def download_blob(self) -> FakeAzureDownload:
        return FakeAzureDownload(self._store[self._name])

    async def delete_blob(self) -> None:
        self._store.pop(self._name, None)

    async def exists(self) -> bool:
        return self._name in self._store


class FakeAzureContainerClient:
    def __init__(self, store: dict[str, bytes]) -> None:
        self._store = store

    def get_blob_client(self, blob_name: str) -> FakeAzureBlobClient:
        return FakeAzureBlobClient(self._store, blob_name)


class FakeAzureServiceClient:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get_container_client(self, container: str) -> FakeAzureContainerClient:
        return FakeAzureContainerClient(self._store)

    def get_blob_client(self, container: str, blob: str) -> FakeAzureBlobClient:
        return FakeAzureBlobClient(self._store, blob)


@pytest.mark.asyncio
async def test_azure_blob_storage_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Store, retrieve, stream, and delete using mocked Azure storage."""
    _install_azure_stubs()
    client = FakeAzureServiceClient()

    async def get_client() -> Any:
        return client

    storage = AzureBlobStorage(
        container="test-container",
        connection_string="UseDevelopmentStorage=true",
    )
    monkeypatch.setattr(storage, "_get_client", get_client)

    content = b"titan-azure-blob"
    metadata = await storage.store(
        submodel_id="urn:test:submodel:azure",
        id_short_path="Blob4",
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
