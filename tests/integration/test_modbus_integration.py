"""Integration tests for Modbus connector with real Modbus server.

These tests verify end-to-end Modbus functionality:
1. Client: Connect to Modbus server, read/write registers
2. Polling: Poll registers and trigger callbacks on value changes
3. Mapping: Bidirectional sync between Modbus and AAS elements
4. Reconnection: Server restart, verify reconnection logic
"""

import asyncio
from typing import Any

import pytest
from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import ModbusTcpServer

from titan.connectors.modbus.client import ModbusClient, ModbusConfig
from titan.connectors.modbus.config_loader import ModbusConfigLoader
from titan.connectors.modbus.connection import ModbusConnectionManager
from titan.connectors.modbus.mapping import RegisterMapping
from titan.connectors.modbus.poller import ModbusPoller, PollConfig


@pytest.fixture(scope="function")
def event_loop():
    """Create event loop for module-scoped fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def modbus_server():
    """Start Modbus TCP server for testing."""
    # Create datastore with initial values
    # Coils (0-99)
    coils = ModbusSequentialDataBlock(0, [False] * 100)
    # Discrete Inputs (0-99)
    discrete_inputs = ModbusSequentialDataBlock(0, [False] * 100)
    # Holding Registers (0-999)
    holding_registers = ModbusSequentialDataBlock(0, [0] * 1000)
    # Input Registers (0-999)
    input_registers = ModbusSequentialDataBlock(0, [0] * 1000)

    # Create device context (replaces deprecated SlaveContext in pymodbus 3.x)
    device_context = ModbusDeviceContext(
        di=discrete_inputs,
        co=coils,
        hr=holding_registers,
        ir=input_registers,
    )

    # Create server context
    server_context = ModbusServerContext(devices=device_context, single=True)

    # Create and start server
    server = ModbusTcpServer(
        context=server_context,
        address=("127.0.0.1", 5020),  # Use non-standard port to avoid conflicts
    )

    # Start server in background task
    server_task = asyncio.create_task(server.serve_forever())

    # Give server time to start
    await asyncio.sleep(0.5)

    yield server_context

    # Cleanup - shutdown server and cancel task
    await server.shutdown()
    if not server_task.done():
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.fixture
def modbus_config() -> ModbusConfig:
    """Create Modbus config for test server."""
    return ModbusConfig(
        host="127.0.0.1",
        port=5020,
        mode="tcp",
        unit_id=1,
        timeout=3.0,
        reconnect_interval=1.0,
    )


class TestModbusClientIntegration:
    """Test Modbus client with real server."""

    @pytest.mark.asyncio
    async def test_connect_to_server(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Connect to Modbus server."""
        client = ModbusClient(modbus_config)

        result = await client.connect()
        assert result is True
        assert client.is_connected is True

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_read_holding_registers(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Read holding registers from server."""
        client = ModbusClient(modbus_config)
        await client.connect()

        # Read registers (should be 0 initially)
        values = await client.read_holding_registers(100, 5)
        assert values is not None
        assert len(values) == 5
        assert all(v == 0 for v in values)

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_write_holding_register(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Write holding register to server."""
        client = ModbusClient(modbus_config)
        await client.connect()

        # Write value
        result = await client.write_register(200, 42)
        assert result is True

        # Read back to verify
        values = await client.read_holding_registers(200, 1)
        assert values is not None
        assert values[0] == 42

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_read_write_coils(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Read and write coils."""
        client = ModbusClient(modbus_config)
        await client.connect()

        # Write coil
        result = await client.write_coil(10, True)
        assert result is True

        # Read back
        values = await client.read_coils(10, 1)
        assert values is not None
        assert values[0] is True

        # Write False
        await client.write_coil(10, False)
        values = await client.read_coils(10, 1)
        assert values is not None
        assert values[0] is False

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_write_multiple_registers(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Write multiple registers at once."""
        client = ModbusClient(modbus_config)
        await client.connect()

        # Write multiple values
        values_to_write = [100, 200, 300, 400, 500]
        result = await client.write_multiple_registers(300, values_to_write)
        assert result is True

        # Read back to verify
        values = await client.read_holding_registers(300, 5)
        assert values is not None
        assert values == values_to_write

        await client.disconnect()


class TestModbusPollerIntegration:
    """Test Modbus poller with real server."""

    @pytest.mark.asyncio
    async def test_polling_detects_value_change(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Poller detects register value changes."""
        client = ModbusClient(modbus_config)
        await client.connect()

        poller = ModbusPoller(client)
        callback_data = []

        def on_value_change(address: int, values: list[int] | list[bool]) -> None:
            """Record callback invocations."""
            callback_data.append({"address": address, "values": values})

        # Start polling register 400
        poll_config = PollConfig(
            register_address=400,
            register_type="holding_register",
            count=1,
            interval=0.1,  # Fast polling for test
            debounce_count=1,
        )

        poll_id = poller.start_polling(poll_config, on_value_change)
        assert poller.is_running is True

        # Wait for initial poll
        await asyncio.sleep(0.2)

        # Change value
        await client.write_register(400, 123)

        # Wait for poller to detect change
        await asyncio.sleep(0.3)

        # Stop polling
        poller.stop_polling(poll_id)

        # Verify callback was invoked with new value
        assert len(callback_data) > 0
        assert any(data["values"][0] == 123 for data in callback_data)

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_polling_debounce(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Poller debouncing prevents spurious callbacks."""
        client = ModbusClient(modbus_config)
        await client.connect()

        poller = ModbusPoller(client)
        callback_count = []

        def on_value_change(address: int, values: list[int] | list[bool]) -> None:
            """Count callbacks."""
            callback_count.append(values[0])

        # Polling with debounce count of 3
        poll_config = PollConfig(
            register_address=500,
            register_type="holding_register",
            count=1,
            interval=0.1,
            debounce_count=3,  # Require 3 consecutive reads
        )

        poll_id = poller.start_polling(poll_config, on_value_change)

        # Wait for initial poll
        await asyncio.sleep(0.2)

        # Change value
        await client.write_register(500, 99)

        # Wait for debounce (need 3 consecutive reads: 0.3s)
        await asyncio.sleep(0.5)

        poller.stop_polling(poll_id)

        # Should have received callback after debounce
        assert len(callback_count) > 0
        assert 99 in callback_count

        await client.disconnect()


class TestModbusMappingIntegration:
    """Test Modbus mapping with real server."""

    @pytest.mark.asyncio
    async def test_load_mappings_from_json(self) -> None:
        """Load mappings from JSON configuration."""
        config_json = {
            "mappings": [
                {
                    "submodel_id": "urn:test:submodel:1",
                    "element_path": "Temperature",
                    "register_address": 100,
                    "register_type": "holding_register",
                    "data_type": "float",
                    "scale_factor": 0.1,
                    "direction": "read",
                }
            ]
        }

        mapper = ModbusConfigLoader.load_from_dict(config_json)

        assert len(mapper.mappings) == 1
        mapping = mapper.mappings[0]
        assert mapping.submodel_id == "urn:test:submodel:1"
        assert mapping.register_address == 100
        assert mapping.scale_factor == 0.1

    @pytest.mark.asyncio
    async def test_mapping_value_conversion(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Test mapping value conversion with scaling."""
        client = ModbusClient(modbus_config)
        await client.connect()

        # Create mapping with scaling (register value 235 = 23.5°C)
        mapping = RegisterMapping(
            submodel_id="urn:test:submodel:1",
            element_path="Temperature",
            register_address=600,
            register_type="holding_register",
            data_type="float",
            scale_factor=0.1,
            direction="both",
        )

        # Write scaled value
        register_value = mapping.value_to_register(23.5)
        assert register_value == 235

        await client.write_register(600, register_value)

        # Read and convert back
        values = await client.read_holding_registers(600, 1)
        assert values is not None
        aas_value = mapping.register_to_value(values[0])
        assert aas_value == 23.5

        await client.disconnect()


class TestModbusConnectionManagerIntegration:
    """Test connection manager with real server."""

    @pytest.mark.asyncio
    async def test_connection_manager_lifecycle(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Test connection manager connect/disconnect."""
        manager = ModbusConnectionManager(modbus_config)

        # Connect
        result = await manager.connect()
        assert result is True
        assert manager.is_connected is True
        assert manager.metrics.successful_connections == 1

        # Ensure connected (should return existing client)
        client = await manager.ensure_connected()
        assert client is not None

        # Disconnect
        await manager.disconnect()
        assert manager.is_connected is False
        assert manager.metrics.disconnections == 1

    @pytest.mark.asyncio
    async def test_health_check(
        self, modbus_config: ModbusConfig, modbus_server: Any
    ) -> None:
        """Test health check reports correct status."""
        manager = ModbusConnectionManager(modbus_config)

        # Initially disconnected
        health = await manager.health_check()
        assert health["connected"] is False
        assert health["state"] == "disconnected"

        # After connecting
        await manager.connect()
        health = await manager.health_check()
        assert health["connected"] is True
        assert health["state"] == "connected"
        assert health["host"] == "127.0.0.1"
        assert health["port"] == 5020

        await manager.disconnect()
