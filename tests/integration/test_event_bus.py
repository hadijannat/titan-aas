"""Integration tests for the event bus backends."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from titan.events.redis_bus import RedisStreamEventBus
from titan.events.schemas import AasEvent, EventType


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

    @pytest.mark.asyncio
    async def test_publish_and_consume(
        self, redis_client: Redis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Publishing an event should reach subscribed handlers."""

        async def get_test_redis() -> Redis:
            return redis_client

        import titan.events.redis_bus as redis_bus_module

        monkeypatch.setattr(redis_bus_module, "get_redis", get_test_redis)

        stream_name = f"titan:test:events:{uuid4().hex}"
        group_name = f"titan-test-group-{uuid4().hex[:8]}"

        bus = RedisStreamEventBus(
            stream_name=stream_name,
            consumer_group=group_name,
            consumer_id="test-consumer",
        )

        received: list[AasEvent] = []
        received_event = asyncio.Event()

        async def handler(event: AasEvent) -> None:
            received.append(event)
            received_event.set()

        await bus.subscribe(handler)
        await bus.start()

        test_event = AasEvent(
            event_type=EventType.CREATED,
            identifier="urn:example:aas:test",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOnRlc3Q",
            doc_bytes=b"{}",
            etag="etag",
        )

        await bus.publish(test_event)

        await asyncio.wait_for(received_event.wait(), timeout=5)
        assert len(received) == 1
        assert received[0].identifier == test_event.identifier
        assert received[0].event_type == EventType.CREATED

        await bus.stop()
