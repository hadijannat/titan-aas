"""Tests for WebSocket event integration.

Tests the wiring between event publishers, event bus, and WebSocket handlers.
"""

import pytest

from titan.api.routers.websocket import WebSocketEventHandler, WebSocketManager
from titan.events import (
    EventType,
    InMemoryEventBus,
    publish_aas_deleted,
    publish_aas_event,
    publish_submodel_event,
)
from titan.events.schemas import AasEvent, AnyEvent, SubmodelEvent


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self) -> None:
        self.sent_messages: list[bytes] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_bytes(self, data: bytes) -> None:
        self.sent_messages.append(data)


@pytest.fixture
async def event_bus() -> InMemoryEventBus:
    """Create and start an in-memory event bus."""
    bus = InMemoryEventBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
def ws_manager() -> WebSocketManager:
    """Create a WebSocket manager for testing."""
    return WebSocketManager()


@pytest.fixture
def ws_handler(ws_manager: WebSocketManager) -> WebSocketEventHandler:
    """Create a WebSocket event handler."""
    return WebSocketEventHandler(ws_manager)


class TestEventBusWebSocketIntegration:
    """Tests for event bus to WebSocket handler integration."""

    @pytest.mark.asyncio
    async def test_aas_event_broadcast_to_websocket(
        self,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
        ws_handler: WebSocketEventHandler,
    ) -> None:
        """AAS events published to bus are broadcast to WebSocket clients."""
        # Create mock websocket and subscribe
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        # Wire handler to event bus
        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await ws_handler.handle_aas_event(event)

        await event_bus.subscribe(broadcast_handler)

        # Publish event
        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:test",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOnRlc3Q",
            doc_bytes=b'{"id": "test"}',
            etag="etag123",
        )

        # Wait for event to be processed
        await event_bus.drain()

        # Verify WebSocket received the event
        assert len(mock_ws.sent_messages) == 1
        assert b"created" in mock_ws.sent_messages[0]
        assert b"urn:example:aas:test" in mock_ws.sent_messages[0]

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_submodel_event_broadcast_to_websocket(
        self,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
        ws_handler: WebSocketEventHandler,
    ) -> None:
        """Submodel events published to bus are broadcast to WebSocket clients."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, SubmodelEvent):
                await ws_handler.handle_submodel_event(event)

        await event_bus.subscribe(broadcast_handler)

        await publish_submodel_event(
            event_bus=event_bus,
            event_type=EventType.UPDATED,
            identifier="urn:example:submodel:test",
            identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6dGVzdA",
            doc_bytes=b'{"id": "test"}',
            etag="etag456",
            semantic_id="urn:example:semantic:1",
        )

        await event_bus.drain()

        assert len(mock_ws.sent_messages) == 1
        assert b"updated" in mock_ws.sent_messages[0]
        assert b"urn:example:submodel:test" in mock_ws.sent_messages[0]

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_deleted_event_broadcast(
        self,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
        ws_handler: WebSocketEventHandler,
    ) -> None:
        """Deleted events are broadcast to WebSocket clients."""
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws)

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await ws_handler.handle_aas_event(event)

        await event_bus.subscribe(broadcast_handler)

        await publish_aas_deleted(
            event_bus=event_bus,
            identifier="urn:example:aas:deleted",
            identifier_b64="b64deleted",
        )

        await event_bus.drain()

        assert len(mock_ws.sent_messages) == 1
        assert b"deleted" in mock_ws.sent_messages[0]

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_entity_filter_only_receives_matching_events(
        self,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
        ws_handler: WebSocketEventHandler,
    ) -> None:
        """WebSocket with entity filter only receives matching events."""
        # Create websocket with AAS filter
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws, entity_filter="aas")

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await ws_handler.handle_aas_event(event)
            elif isinstance(event, SubmodelEvent):
                await ws_handler.handle_submodel_event(event)

        await event_bus.subscribe(broadcast_handler)

        # Publish Submodel event (should NOT be received)
        await publish_submodel_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:submodel:filtered",
            identifier_b64="b64sm",
            doc_bytes=b"{}",
            etag="etag",
        )

        await event_bus.drain()

        # Should NOT have received the submodel event
        assert len(mock_ws.sent_messages) == 0

        # Publish AAS event (should be received)
        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:filtered",
            identifier_b64="b64aas",
            doc_bytes=b"{}",
            etag="etag",
        )

        await event_bus.drain()

        # Should have received the AAS event
        assert len(mock_ws.sent_messages) == 1
        assert b"aas" in mock_ws.sent_messages[0]

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_identifier_filter_only_receives_matching_events(
        self,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
        ws_handler: WebSocketEventHandler,
    ) -> None:
        """WebSocket with identifier filter only receives matching events."""
        target_id_b64 = "target_id_b64"
        mock_ws = MockWebSocket()
        subscription = await ws_manager.connect(mock_ws, identifier_filter=target_id_b64)

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await ws_handler.handle_aas_event(event)

        await event_bus.subscribe(broadcast_handler)

        # Publish event with different identifier
        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:other",
            identifier_b64="other_id_b64",
            doc_bytes=b"{}",
            etag="etag",
        )

        await event_bus.drain()
        assert len(mock_ws.sent_messages) == 0

        # Publish event with target identifier
        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.UPDATED,
            identifier="urn:example:aas:target",
            identifier_b64=target_id_b64,
            doc_bytes=b"{}",
            etag="etag",
        )

        await event_bus.drain()
        assert len(mock_ws.sent_messages) == 1

        await ws_manager.disconnect(subscription)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive_events(
        self,
        event_bus: InMemoryEventBus,
        ws_manager: WebSocketManager,
        ws_handler: WebSocketEventHandler,
    ) -> None:
        """Multiple WebSocket subscribers all receive events."""
        mock_ws1 = MockWebSocket()
        mock_ws2 = MockWebSocket()
        mock_ws3 = MockWebSocket()

        sub1 = await ws_manager.connect(mock_ws1)
        sub2 = await ws_manager.connect(mock_ws2)
        sub3 = await ws_manager.connect(mock_ws3)

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await ws_handler.handle_aas_event(event)

        await event_bus.subscribe(broadcast_handler)

        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:multi",
            identifier_b64="b64multi",
            doc_bytes=b"{}",
            etag="etag",
        )

        await event_bus.drain()

        # All three should have received the event
        assert len(mock_ws1.sent_messages) == 1
        assert len(mock_ws2.sent_messages) == 1
        assert len(mock_ws3.sent_messages) == 1

        await ws_manager.disconnect(sub1)
        await ws_manager.disconnect(sub2)
        await ws_manager.disconnect(sub3)
