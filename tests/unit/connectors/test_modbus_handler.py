"""Unit tests for Modbus event handler."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from titan.connectors.modbus.client import ModbusClient
from titan.connectors.modbus.handler import ModbusEventHandler, ModbusValueSyncHandler
from titan.connectors.modbus.mapping import ModbusMapper, RegisterMapping
from titan.core.ids import encode_id_to_b64url
from titan.events import SubmodelElementEvent


class TestModbusEventHandler:
    """Test ModbusEventHandler class."""

    @pytest.fixture
    def modbus_client_mock(self) -> MagicMock:
        """Create mock Modbus client."""
        client = MagicMock(spec=ModbusClient)
        client.write_coil = AsyncMock(return_value=True)
        client.write_register = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def mapper_with_mappings(self) -> ModbusMapper:
        """Create mapper with test mappings."""
        mappings = [
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="holding_register",
                data_type="float",
                scale_factor=0.1,
                direction="write",
            ),
            RegisterMapping(
                submodel_id="urn:example:submodel:actuators:1",
                element_path="MotorRunning",
                register_address=10,
                register_type="coil",
                data_type="bool",
                direction="write",
            ),
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="ReadOnlyTemp",
                register_address=200,
                register_type="input_register",
                data_type="float",
                direction="read",  # Read-only, won't write
            ),
        ]
        return ModbusMapper(mappings)

    @pytest.mark.asyncio
    async def test_handle_element_event_write_coil(
        self, modbus_client_mock: MagicMock, mapper_with_mappings: ModbusMapper
    ) -> None:
        """Handle element event and write to coil."""
        handler = ModbusEventHandler(modbus_client_mock, mapper_with_mappings)

        submodel_id = "urn:example:submodel:actuators:1"
        event = SubmodelElementEvent(
            event_type="value_changed",
            submodel_identifier=submodel_id,
            submodel_identifier_b64=encode_id_to_b64url(submodel_id),
            id_short_path="MotorRunning",
            value_bytes=json.dumps(True).encode("utf-8"),
        )

        await handler.handle_element_event(event)

        # Verify write_coil was called
        modbus_client_mock.write_coil.assert_called_once_with(10, True)

    @pytest.mark.asyncio
    async def test_handle_element_event_write_register(
        self, modbus_client_mock: MagicMock, mapper_with_mappings: ModbusMapper
    ) -> None:
        """Handle element event and write to holding register."""
        handler = ModbusEventHandler(modbus_client_mock, mapper_with_mappings)

        # Temperature: 23.5°C -> register value 235 (with scale 0.1)
        submodel_id = "urn:example:submodel:sensors:1"
        event = SubmodelElementEvent(
            event_type="value_changed",
            submodel_identifier=submodel_id,
            submodel_identifier_b64=encode_id_to_b64url(submodel_id),
            id_short_path="Temperature",
            value_bytes=json.dumps(23.5).encode("utf-8"),
        )

        await handler.handle_element_event(event)

        # Verify write_register was called with scaled value
        modbus_client_mock.write_register.assert_called_once_with(100, 235)

    @pytest.mark.asyncio
    async def test_handle_element_event_no_mapping(
        self, modbus_client_mock: MagicMock, mapper_with_mappings: ModbusMapper
    ) -> None:
        """Handle event with no mapping (should log and skip)."""
        handler = ModbusEventHandler(modbus_client_mock, mapper_with_mappings)

        submodel_id = "urn:example:submodel:unknown:1"
        event = SubmodelElementEvent(
            event_type="value_changed",
            submodel_identifier=submodel_id,
            submodel_identifier_b64=encode_id_to_b64url(submodel_id),
            id_short_path="UnknownElement",
            value_bytes=json.dumps(42).encode("utf-8"),
        )

        await handler.handle_element_event(event)

        # Verify no writes occurred
        modbus_client_mock.write_coil.assert_not_called()
        modbus_client_mock.write_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_element_event_read_only_mapping(
        self, modbus_client_mock: MagicMock, mapper_with_mappings: ModbusMapper
    ) -> None:
        """Handle event with read-only mapping (should skip write)."""
        handler = ModbusEventHandler(modbus_client_mock, mapper_with_mappings)

        submodel_id = "urn:example:submodel:sensors:1"
        event = SubmodelElementEvent(
            event_type="value_changed",
            submodel_identifier=submodel_id,
            submodel_identifier_b64=encode_id_to_b64url(submodel_id),
            id_short_path="ReadOnlyTemp",
            value_bytes=json.dumps(25.0).encode("utf-8"),
        )

        await handler.handle_element_event(event)

        # Verify no writes occurred (read-only mapping)
        modbus_client_mock.write_coil.assert_not_called()
        modbus_client_mock.write_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_element_event_no_value(
        self, modbus_client_mock: MagicMock, mapper_with_mappings: ModbusMapper
    ) -> None:
        """Handle event with no value_bytes."""
        handler = ModbusEventHandler(modbus_client_mock, mapper_with_mappings)

        submodel_id = "urn:example:submodel:sensors:1"
        event = SubmodelElementEvent(
            event_type="value_changed",
            submodel_identifier=submodel_id,
            submodel_identifier_b64=encode_id_to_b64url(submodel_id),
            id_short_path="Temperature",
            value_bytes=None,
        )

        await handler.handle_element_event(event)

        # Verify no writes occurred
        modbus_client_mock.write_coil.assert_not_called()
        modbus_client_mock.write_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_element_event_write_failure(
        self, modbus_client_mock: MagicMock, mapper_with_mappings: ModbusMapper
    ) -> None:
        """Handle write failure."""
        handler = ModbusEventHandler(modbus_client_mock, mapper_with_mappings)

        # Mock write failure
        modbus_client_mock.write_register = AsyncMock(return_value=False)

        submodel_id = "urn:example:submodel:sensors:1"
        event = SubmodelElementEvent(
            event_type="value_changed",
            submodel_identifier=submodel_id,
            submodel_identifier_b64=encode_id_to_b64url(submodel_id),
            id_short_path="Temperature",
            value_bytes=json.dumps(23.5).encode("utf-8"),
        )

        # Should not raise exception, just log error
        await handler.handle_element_event(event)

        # Verify write was attempted
        modbus_client_mock.write_register.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_element_event_invalid_value(
        self, modbus_client_mock: MagicMock, mapper_with_mappings: ModbusMapper
    ) -> None:
        """Handle event with invalid value (conversion error)."""
        handler = ModbusEventHandler(modbus_client_mock, mapper_with_mappings)

        # Value out of range for holding register
        submodel_id = "urn:example:submodel:sensors:1"
        event = SubmodelElementEvent(
            event_type="value_changed",
            submodel_identifier=submodel_id,
            submodel_identifier_b64=encode_id_to_b64url(submodel_id),
            id_short_path="Temperature",
            value_bytes=json.dumps(700000.0).encode("utf-8"),  # Too large
        )

        # Should catch ValueError and log, not raise
        await handler.handle_element_event(event)

        # Verify no write occurred
        modbus_client_mock.write_register.assert_not_called()


class TestModbusValueSyncHandler:
    """Test ModbusValueSyncHandler class."""

    @pytest.fixture
    def modbus_client_mock(self) -> MagicMock:
        """Create mock Modbus client."""
        client = MagicMock(spec=ModbusClient)
        return client

    @pytest.fixture
    def mapper_with_readable_mappings(self) -> ModbusMapper:
        """Create mapper with readable mappings."""
        mappings = [
            RegisterMapping(
                submodel_id="urn:example:submodel:sensors:1",
                element_path="Temperature",
                register_address=100,
                register_type="holding_register",
                data_type="float",
                scale_factor=0.1,
                direction="read",
            ),
            RegisterMapping(
                submodel_id="urn:example:submodel:actuators:1",
                element_path="MotorRunning",
                register_address=10,
                register_type="coil",
                data_type="bool",
                direction="both",  # Bidirectional
            ),
        ]
        return ModbusMapper(mappings)

    @pytest.mark.asyncio
    async def test_start_sync_creates_pollers(
        self, modbus_client_mock: MagicMock, mapper_with_readable_mappings: ModbusMapper
    ) -> None:
        """Start sync creates polling tasks for readable mappings."""
        event_publisher_mock = MagicMock()
        handler = ModbusValueSyncHandler(
            modbus_client_mock, mapper_with_readable_mappings, event_publisher_mock
        )

        await handler.start_sync(polling_interval=1.0)

        # Verify polling tasks were created
        assert handler.poller.is_running

        # 2 readable mappings (read + both)
        assert len(handler.poller._poll_tasks) == 2

    @pytest.mark.asyncio
    async def test_start_sync_no_readable_mappings(
        self, modbus_client_mock: MagicMock
    ) -> None:
        """Start sync with no readable mappings."""
        # Create mapper with only writable mapping
        mappings = [
            RegisterMapping(
                submodel_id="urn:example:submodel:actuators:1",
                element_path="Setpoint",
                register_address=200,
                register_type="holding_register",
                direction="write",
            ),
        ]
        mapper = ModbusMapper(mappings)

        event_publisher_mock = MagicMock()
        handler = ModbusValueSyncHandler(modbus_client_mock, mapper, event_publisher_mock)

        await handler.start_sync()

        # No polling tasks created
        assert not handler.poller.is_running

    @pytest.mark.asyncio
    async def test_stop_sync(
        self, modbus_client_mock: MagicMock, mapper_with_readable_mappings: ModbusMapper
    ) -> None:
        """Stop sync stops all polling."""
        event_publisher_mock = MagicMock()
        handler = ModbusValueSyncHandler(
            modbus_client_mock, mapper_with_readable_mappings, event_publisher_mock
        )

        await handler.start_sync()
        assert handler.poller.is_running

        await handler.stop_sync()
        assert not handler.poller.is_running

    def test_sync_handler_with_default_mapper(self, modbus_client_mock: MagicMock) -> None:
        """Create sync handler with default mapper."""
        handler = ModbusValueSyncHandler(modbus_client_mock)

        assert handler.mapper is not None
        assert len(handler.mapper.mappings) == 0

    def test_sync_handler_with_no_event_publisher(
        self, modbus_client_mock: MagicMock
    ) -> None:
        """Create sync handler without event publisher."""
        handler = ModbusValueSyncHandler(modbus_client_mock)

        assert handler.event_publisher is None
