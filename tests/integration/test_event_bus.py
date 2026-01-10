"""Integration tests for the event bus backends."""

from __future__ import annotations

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from titan.events.redis_bus import RedisStreamEventBus

# Skip if testcontainers not available
pytest.importorskip("testcontainers")


class TestRedisStreamEventBus:
    """Tests for RedisStreamEventBus with a real Redis instance."""

    @pytest.mark.asyncio
    async def test_creates_stream_group(
        self, redis_client: Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Starting the bus should create the stream and consumer group."""

        async def get_test_redis() -> Redis:
            return redis_client

        # Patch the Redis factory used by the bus
        import titan.events.redis_bus as redis_bus_module

        monkeypatch.setattr(redis_bus_module, "get_redis", get_test_redis)

        stream_name = f"titan:test:events:{uuid4().hex}"
        group_name = f"titan-test-group-{uuid4().hex[:8]}"

        bus = RedisStreamEventBus(
            stream_name=stream_name,
            consumer_group=group_name,
            consumer_id="test-consumer",
        )

        await bus.start()

        groups = await redis_client.xinfo_groups(stream_name)
        group_names = {
            g["name"].decode() if isinstance(g["name"], bytes) else g["name"] for g in groups
        }
        assert group_name in group_names

        await bus.stop()
