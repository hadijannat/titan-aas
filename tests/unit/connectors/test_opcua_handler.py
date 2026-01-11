"""Tests for OPC-UA event handler."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from titan.connectors.opcua.connection import OpcUaConnectionManager
from titan.connectors.opcua.handler import OpcUaEventHandler, OpcUaValueSyncHandler
from titan.events import EventType, SubmodelElementEvent


class TestOpcUaEventHandler:
    """Test OPC-UA event handler."""

    @pytest.fixture
    def mock_connection_manager(self) -> MagicMock:
        """Create mock connection manager."""
        manager = MagicMock(spec=OpcUaConnectionManager)
        manager.config = MagicMock()
        manager.config.endpoint_url = "opc.tcp://localhost:4840"

        mock_client = MagicMock()
        mock_client.write_node = AsyncMock(return_value=True)
        manager.ensure_connected = AsyncMock(return_value=mock_client)

        return manager

    @pytest.fixture
    def event_handler(
        self, mock_connection_manager: MagicMock
    ) -> OpcUaEventHandler:
        """Create event handler instance."""
        return OpcUaEventHandler(mock_connection_manager)

    @pytest.mark.asyncio
    async def test_handle_element_event_with_mapping(
        self,
        event_handler: OpcUaEventHandler,
        mock_connection_manager: MagicMock,
    ) -> None:
        """Handle element event with mapping."""
        # Mock mapper to return a node ID
        event_handler.mapper.get_node_id = MagicMock(
            return_value="ns=2;s=Temperature"
        )

        event = SubmodelElementEvent(
            event_type=EventType.UPDATED,
            submodel_identifier="urn:example:submodel:1",
            submodel_identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ",
            id_short_path="Temperature",
            value_bytes=b'{"value": 25.5}',
        )

        # Should not raise an error
        await event_handler.handle_element_event(event)

    @pytest.mark.asyncio
    async def test_handle_element_event_no_mapping(
        self,
        event_handler: OpcUaEventHandler,
    ) -> None:
        """Handle element event with no mapping does nothing."""
        # Mock mapper to return None (no mapping)
        event_handler.mapper.get_node_id = MagicMock(return_value=None)

        event = SubmodelElementEvent(
            event_type=EventType.UPDATED,
            submodel_identifier="urn:example:submodel:1",
            submodel_identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ",
            id_short_path="UnmappedProperty",
            value_bytes=b'{"value": 100}',
        )

        # Should not raise an error
        await event_handler.handle_element_event(event)

    @pytest.mark.asyncio
    async def test_handle_element_event_no_value(
        self,
        event_handler: OpcUaEventHandler,
    ) -> None:
        """Handle element event with no value does nothing."""
        event_handler.mapper.get_node_id = MagicMock(
            return_value="ns=2;s=Temperature"
        )

        event = SubmodelElementEvent(
            event_type=EventType.UPDATED,
            submodel_identifier="urn:example:submodel:1",
            submodel_identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ",
            id_short_path="Temperature",
            value_bytes=None,  # No value
        )

        # Should not raise an error
        await event_handler.handle_element_event(event)


class TestOpcUaValueSyncHandler:
    """Test OPC-UA bidirectional value sync handler."""

    @pytest.fixture
    def mock_connection_manager(self) -> MagicMock:
        """Create mock connection manager."""
        manager = MagicMock(spec=OpcUaConnectionManager)

        mock_client = MagicMock()
        mock_client.subscribe = AsyncMock(return_value="sub_0")
        mock_client.unsubscribe = AsyncMock(return_value=True)
        manager.ensure_connected = AsyncMock(return_value=mock_client)

        return manager

    @pytest.fixture
    def sync_handler(
        self, mock_connection_manager: MagicMock
    ) -> OpcUaValueSyncHandler:
        """Create sync handler instance."""
        return OpcUaValueSyncHandler(mock_connection_manager)

    @pytest.mark.asyncio
    async def test_start_sync_bidirectional(
        self,
        sync_handler: OpcUaValueSyncHandler,
        mock_connection_manager: MagicMock,
    ) -> None:
        """Start sync for bidirectional mappings."""
        mappings = [
            {
                "submodel_id": "urn:example:submodel:1",
                "element_path": "Temperature",
                "node_id": "ns=2;s=Temperature",
                "direction": "bidirectional",
            },
            {
                "submodel_id": "urn:example:submodel:1",
                "element_path": "Pressure",
                "node_id": "ns=2;s=Pressure",
                "direction": "bidirectional",
            },
        ]

        await sync_handler.start_sync(mappings)

        # Verify subscription was created
        client = await mock_connection_manager.ensure_connected()
        client.subscribe.assert_called_once()

        # Verify nodes were subscribed
        assert len(sync_handler._subscriptions) == 2

    @pytest.mark.asyncio
    async def test_start_sync_read_only(
        self,
        sync_handler: OpcUaValueSyncHandler,
        mock_connection_manager: MagicMock,
    ) -> None:
        """Start sync for read-only mappings."""
        mappings = [
            {
                "submodel_id": "urn:example:submodel:1",
                "element_path": "Temperature",
                "node_id": "ns=2;s=Temperature",
                "direction": "read",
            }
        ]

        await sync_handler.start_sync(mappings)

        # Verify subscription was created for read mapping
        client = await mock_connection_manager.ensure_connected()
        client.subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_sync_write_only(
        self,
        sync_handler: OpcUaValueSyncHandler,
        mock_connection_manager: MagicMock,
    ) -> None:
        """Start sync for write-only mappings (no subscriptions)."""
        mappings = [
            {
                "submodel_id": "urn:example:submodel:1",
                "element_path": "SetPoint",
                "node_id": "ns=2;s=SetPoint",
                "direction": "write",
            }
        ]

        await sync_handler.start_sync(mappings)

        # Verify no subscription was created for write-only
        client = await mock_connection_manager.ensure_connected()
        client.subscribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_sync(
        self,
        sync_handler: OpcUaValueSyncHandler,
        mock_connection_manager: MagicMock,
    ) -> None:
        """Stop all active subscriptions."""
        mappings = [
            {
                "submodel_id": "urn:example:submodel:1",
                "element_path": "Temperature",
                "node_id": "ns=2;s=Temperature",
                "direction": "read",
            }
        ]

        # Start sync first
        await sync_handler.start_sync(mappings)
        assert len(sync_handler._subscriptions) > 0

        # Then stop
        await sync_handler.stop_sync()

        # Verify unsubscribe was called
        client = await mock_connection_manager.ensure_connected()
        client.unsubscribe.assert_called_once_with("sub_0")

        # Verify subscriptions cleared
        assert len(sync_handler._subscriptions) == 0
