"""Integration tests for Redis cache layer.

Tests cache operations with real Redis.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from titan.cache.keys import CacheKeys

# Skip if testcontainers not available
pytest.importorskip("testcontainers")


class TestCacheOperations:
    """Tests for Redis cache operations."""

    @pytest.mark.asyncio
    async def test_set_and_get_bytes(self, redis_client: Redis) -> None:
        """Test storing and retrieving bytes."""
        key = CacheKeys.submodel_bytes("test-submodel-id")
        content = b'{"id": "test", "modelType": "Submodel"}'

        await redis_client.set(key, content, ex=3600)
        result = await redis_client.get(key)

        assert result == content

    @pytest.mark.asyncio
    async def test_set_and_get_etag(self, redis_client: Redis) -> None:
        """Test storing and retrieving ETags."""
        key = CacheKeys.submodel_etag("test-submodel-id")
        etag = "abc123def456"

        await redis_client.set(key, etag, ex=3600)
        result = await redis_client.get(key)

        assert result.decode() == etag

    @pytest.mark.asyncio
    async def test_delete_key(self, redis_client: Redis) -> None:
        """Test deleting a key."""
        key = CacheKeys.aas_bytes("test-aas-id")
        await redis_client.set(key, b"test content")

        # Delete
        await redis_client.delete(key)

        # Verify
        result = await redis_client.get(key)
        assert result is None

    @pytest.mark.asyncio
    async def test_pattern_delete(self, redis_client: Redis) -> None:
        """Test deleting keys by pattern."""
        # Set multiple keys for same submodel
        submodel_id = "test-submodel-pattern"
        keys = [
            CacheKeys.submodel_bytes(submodel_id),
            CacheKeys.submodel_etag(submodel_id),
            CacheKeys.submodel_element_value(submodel_id, "Property1"),
            CacheKeys.submodel_element_value(submodel_id, "Property2"),
        ]

        for key in keys:
            await redis_client.set(key, b"test")

        # Delete all keys for this submodel using pattern
        pattern = CacheKeys.invalidation_pattern("sm", submodel_id)
        cursor = 0
        while True:
            cursor, found_keys = await redis_client.scan(
                cursor=cursor, match=pattern, count=100
            )
            if found_keys:
                await redis_client.delete(*found_keys)
            if cursor == 0:
                break

        # Verify all deleted
        for key in keys:
            result = await redis_client.get(key)
            assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiry(self, redis_client: Redis) -> None:
        """Test that TTL is set correctly."""
        key = CacheKeys.submodel_bytes("ttl-test")
        ttl_seconds = 3600

        await redis_client.set(key, b"test", ex=ttl_seconds)
        actual_ttl = await redis_client.ttl(key)

        # TTL should be close to what we set (allow 1 second tolerance)
        assert abs(actual_ttl - ttl_seconds) <= 1

    @pytest.mark.asyncio
    async def test_conditional_set_nx(self, redis_client: Redis) -> None:
        """Test SET NX (only set if not exists)."""
        key = "titan:test:conditional"

        # First set should succeed
        result1 = await redis_client.set(key, b"first", nx=True)
        assert result1 is True

        # Second set should fail (key exists)
        result2 = await redis_client.set(key, b"second", nx=True)
        assert result2 is None

        # Value should be "first"
        value = await redis_client.get(key)
        assert value == b"first"


class TestCacheConsistency:
    """Tests for cache consistency patterns."""

    @pytest.mark.asyncio
    async def test_read_through_pattern(self, redis_client: Redis) -> None:
        """Test read-through cache pattern."""
        submodel_id = "read-through-test"
        key = CacheKeys.submodel_bytes(submodel_id)

        # Simulate read-through:
        # 1. Check cache
        cached = await redis_client.get(key)
        assert cached is None  # Not in cache

        # 2. "Load from database" (simulated)
        db_content = b'{"id": "read-through-test", "modelType": "Submodel"}'

        # 3. Store in cache
        await redis_client.set(key, db_content, ex=3600)

        # 4. Verify cache hit on next read
        cached = await redis_client.get(key)
        assert cached == db_content

    @pytest.mark.asyncio
    async def test_write_invalidation_pattern(self, redis_client: Redis) -> None:
        """Test write-through with cache invalidation."""
        submodel_id = "write-invalidation-test"
        key = CacheKeys.submodel_bytes(submodel_id)

        # Pre-populate cache
        old_content = b'{"id": "test", "value": "old"}'
        await redis_client.set(key, old_content, ex=3600)

        # Simulate write operation:
        # 1. Write to database (simulated)
        new_content = b'{"id": "test", "value": "new"}'

        # 2. Invalidate cache
        await redis_client.delete(key)

        # 3. Optionally: write-through to cache
        await redis_client.set(key, new_content, ex=3600)

        # Verify new content
        cached = await redis_client.get(key)
        assert cached == new_content
