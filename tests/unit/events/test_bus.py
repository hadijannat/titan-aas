"""Tests for event bus implementation."""

import asyncio

import pytest

from titan.events.bus import InMemoryEventBus
from titan.events.schemas import AasEvent, EventType


class TestInMemoryEventBus:
    """Test in-memory event bus."""

    @pytest.fixture
    def bus(self) -> InMemoryEventBus:
        """Create a fresh event bus."""
        return InMemoryEventBus(max_size=100)

    @pytest.fixture
    def sample_event(self) -> AasEvent:
        """Create a sample AAS event."""
        return AasEvent(
            event_type=EventType.CREATED,
            identifier="https://example.com/aas/1",
            identifier_b64="aHR0cHM6Ly9leGFtcGxlLmNvbS9hYXMvMQ",
            doc_bytes=b'{"id": "https://example.com/aas/1"}',
            etag="abc123",
        )

    async def test_publish_adds_to_queue(
        self, bus: InMemoryEventBus, sample_event: AasEvent
    ) -> None:
        """Publishing adds event to the queue."""
        assert bus.pending_count == 0
        await bus.publish(sample_event)
        assert bus.pending_count == 1

    async def test_subscribe_registers_handler(self, bus: InMemoryEventBus) -> None:
        """Subscribing registers a handler."""
        received: list[AasEvent] = []

        async def handler(event: AasEvent) -> None:
            received.append(event)

        await bus.subscribe(handler)
        # Handler is registered but not called yet
        assert len(received) == 0

    async def test_event_processed_by_handler(
        self, bus: InMemoryEventBus, sample_event: AasEvent
    ) -> None:
        """Events are processed by subscribed handlers."""
        received: list[AasEvent] = []

        async def handler(event: AasEvent) -> None:
            received.append(event)

        await bus.subscribe(handler)
        await bus.publish(sample_event)

        # Start the bus and let it process
        await bus.start()
        await asyncio.sleep(0.1)  # Give time to process
        await bus.stop()

        assert len(received) == 1
        assert received[0].identifier == sample_event.identifier

    async def test_multiple_handlers(self, bus: InMemoryEventBus, sample_event: AasEvent) -> None:
        """Multiple handlers all receive the event."""
        received1: list[AasEvent] = []
        received2: list[AasEvent] = []

        async def handler1(event: AasEvent) -> None:
            received1.append(event)

        async def handler2(event: AasEvent) -> None:
            received2.append(event)

        await bus.subscribe(handler1)
        await bus.subscribe(handler2)
        await bus.publish(sample_event)

        await bus.start()
        await asyncio.sleep(0.1)
        await bus.stop()

        assert len(received1) == 1
        assert len(received2) == 1

    async def test_drain_waits_for_all_events(
        self, bus: InMemoryEventBus, sample_event: AasEvent
    ) -> None:
        """Drain waits for all events to be processed."""
        processed = []

        async def handler(event: AasEvent) -> None:
            await asyncio.sleep(0.05)  # Simulate slow processing
            processed.append(event)

        await bus.subscribe(handler)

        # Publish multiple events
        for _i in range(3):
            await bus.publish(sample_event)

        await bus.start()
        await bus.drain()
        await bus.stop()

        assert len(processed) == 3

    async def test_stop_is_idempotent(self, bus: InMemoryEventBus) -> None:
        """Stopping multiple times is safe."""
        await bus.stop()
        await bus.stop()
        # Should not raise

    async def test_start_is_idempotent(self, bus: InMemoryEventBus) -> None:
        """Starting multiple times is safe."""
        await bus.start()
        await bus.start()
        await bus.stop()
        # Should not raise


class TestEventSchemas:
    """Test event dataclass behavior."""

    def test_aas_event_has_defaults(self) -> None:
        """AasEvent has default event_id and timestamp."""
        event = AasEvent(
            event_type=EventType.CREATED,
            identifier="test",
            identifier_b64="dGVzdA",
        )
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_aas_event_is_immutable(self) -> None:
        """AasEvent is immutable (frozen)."""
        event = AasEvent(
            event_type=EventType.CREATED,
            identifier="test",
            identifier_b64="dGVzdA",
        )
        with pytest.raises(AttributeError):
            event.identifier = "changed"  # type: ignore

    def test_event_type_enum(self) -> None:
        """EventType enum has expected values."""
        assert EventType.CREATED.value == "created"
        assert EventType.UPDATED.value == "updated"
        assert EventType.DELETED.value == "deleted"
