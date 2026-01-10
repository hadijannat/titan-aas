"""Tests for WebSocket event broadcasting."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from titan.api.routers.websocket import Subscription, WebSocketManager
from titan.events import AasEvent, EventType, SubmodelEvent


class TestSubscription:
    """Test Subscription dataclass."""

    def test_subscription_no_filters(self) -> None:
        """Subscription without filters."""
        ws = MagicMock()
        sub = Subscription(websocket=ws)
        assert sub.websocket == ws
        assert sub.entity_filter is None
        assert sub.identifier_filter is None

    def test_subscription_with_entity_filter(self) -> None:
        """Subscription with entity filter."""
        ws = MagicMock()
        sub = Subscription(websocket=ws, entity_filter="aas")
        assert sub.entity_filter == "aas"

    def test_subscription_with_identifier_filter(self) -> None:
        """Subscription with identifier filter."""
        ws = MagicMock()
        sub = Subscription(websocket=ws, identifier_filter="abc123")
        assert sub.identifier_filter == "abc123"

    def test_subscription_is_hashable(self) -> None:
        """Subscription can be hashed for WeakSet."""
        ws = MagicMock()
        sub = Subscription(websocket=ws)
        # Should not raise
        hash(sub)


class TestWebSocketManager:
    """Test WebSocketManager."""

    @pytest.fixture
    def manager(self) -> WebSocketManager:
        """Create WebSocketManager instance."""
        return WebSocketManager()

    @pytest.fixture
    def mock_websocket(self) -> MagicMock:
        """Create mock WebSocket."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_bytes = AsyncMock()
        return ws

    @pytest.fixture
    def aas_event(self) -> AasEvent:
        """Create sample AAS event."""
        return AasEvent(
            event_type=EventType.CREATED,
            identifier="urn:example:aas:1",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOjE",
            etag="abc123",
        )

    @pytest.fixture
    def submodel_event(self) -> SubmodelEvent:
        """Create sample Submodel event."""
        return SubmodelEvent(
            event_type=EventType.UPDATED,
            identifier="urn:example:submodel:1",
            identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ",
            etag="def456",
        )

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(
        self, manager: WebSocketManager, mock_websocket: MagicMock
    ) -> None:
        """Connect accepts the websocket."""
        subscription = await manager.connect(mock_websocket)
        mock_websocket.accept.assert_called_once()
        assert subscription.websocket == mock_websocket
        assert manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_subscription(
        self, manager: WebSocketManager, mock_websocket: MagicMock
    ) -> None:
        """Disconnect removes the subscription."""
        subscription = await manager.connect(mock_websocket)
        assert manager.connection_count == 1

        await manager.disconnect(subscription)
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_aas_event_sends_to_all(
        self,
        manager: WebSocketManager,
        mock_websocket: MagicMock,
        aas_event: AasEvent,
    ) -> None:
        """Broadcast sends to all connected clients."""
        await manager.connect(mock_websocket)
        await manager.broadcast_aas_event(aas_event)
        mock_websocket.send_bytes.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_respects_entity_filter(
        self,
        manager: WebSocketManager,
        mock_websocket: MagicMock,
        submodel_event: SubmodelEvent,
    ) -> None:
        """Broadcast respects entity filter."""
        # Subscribe only to AAS events
        await manager.connect(mock_websocket, entity_filter="aas")

        # Broadcast submodel event - should not be sent
        await manager.broadcast_submodel_event(submodel_event)
        mock_websocket.send_bytes.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_respects_identifier_filter(
        self,
        manager: WebSocketManager,
        mock_websocket: MagicMock,
        aas_event: AasEvent,
    ) -> None:
        """Broadcast respects identifier filter."""
        # Subscribe only to specific identifier
        await manager.connect(mock_websocket, identifier_filter="other-id")

        # Broadcast event for different identifier - should not be sent
        await manager.broadcast_aas_event(aas_event)
        mock_websocket.send_bytes.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_matches_correct_filter(
        self,
        manager: WebSocketManager,
        mock_websocket: MagicMock,
        aas_event: AasEvent,
    ) -> None:
        """Broadcast matches when filters match."""
        # Subscribe to matching filters
        await manager.connect(
            mock_websocket,
            entity_filter="aas",
            identifier_filter=aas_event.identifier_b64,
        )

        await manager.broadcast_aas_event(aas_event)
        mock_websocket.send_bytes.assert_called_once()

    def test_matches_filter_no_filters(self, manager: WebSocketManager) -> None:
        """No filters matches everything."""
        ws = MagicMock()
        sub = Subscription(websocket=ws)
        assert manager._matches_filter(sub, "aas", "abc123") is True
        assert manager._matches_filter(sub, "submodel", "def456") is True

    def test_matches_filter_entity_only(self, manager: WebSocketManager) -> None:
        """Entity filter matches correct entity."""
        ws = MagicMock()
        sub = Subscription(websocket=ws, entity_filter="aas")
        assert manager._matches_filter(sub, "aas", "abc123") is True
        assert manager._matches_filter(sub, "submodel", "abc123") is False

    def test_matches_filter_identifier_only(self, manager: WebSocketManager) -> None:
        """Identifier filter matches correct identifier."""
        ws = MagicMock()
        sub = Subscription(websocket=ws, identifier_filter="abc123")
        assert manager._matches_filter(sub, "aas", "abc123") is True
        assert manager._matches_filter(sub, "aas", "def456") is False

    def test_serialize_aas_event(
        self, manager: WebSocketManager, aas_event: AasEvent
    ) -> None:
        """Serialize AAS event to JSON."""
        data = manager._serialize_aas_event(aas_event)
        import orjson

        parsed = orjson.loads(data)
        # EventType.CREATED.value is "created"
        assert parsed["eventType"] == "created"
        assert parsed["entity"] == "aas"
        assert parsed["identifier"] == "urn:example:aas:1"
        assert parsed["etag"] == "abc123"

    def test_serialize_submodel_event(
        self, manager: WebSocketManager, submodel_event: SubmodelEvent
    ) -> None:
        """Serialize Submodel event to JSON."""
        data = manager._serialize_submodel_event(submodel_event)
        import orjson

        parsed = orjson.loads(data)
        # EventType.UPDATED.value is "updated"
        assert parsed["eventType"] == "updated"
        assert parsed["entity"] == "submodel"
        assert parsed["identifier"] == "urn:example:submodel:1"
