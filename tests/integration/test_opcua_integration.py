"""Integration tests for OPC-UA client with asyncua server.

These tests verify end-to-end OPC-UA functionality:
1. Connect to OPC-UA server
2. Read node values
3. Write node values
4. Subscribe to value changes
5. Browse node tree
"""

import asyncio
from typing import Any

import pytest

from titan.connectors.opcua.client import OpcUaClient, OpcUaConfig, OpcUaSecurityMode


class TestOpcUaClientIntegration:
    """Test OPC-UA client end-to-end with asyncua server."""

    @pytest.fixture
    async def opcua_server(self) -> tuple[Any, dict[str, str]]:
        """Start asyncua server for testing.

        Returns:
            Tuple of (server, node_ids) where node_ids maps variable names to NodeIds
        """
        from asyncua import Server

        server = Server()
        await server.init()
        server.set_endpoint("opc.tcp://localhost:4840/test/")

        # Setup namespace
        uri = "http://test.example.com"
        idx = await server.register_namespace(uri)

        # Create test objects
        objects = server.get_objects_node()
        test_obj = await objects.add_object(idx, "TestObject")

        # Create test variables and store their NodeIds
        temp_var = await test_obj.add_variable(idx, "Temperature", 25.5)
        await temp_var.set_writable()

        pressure_var = await test_obj.add_variable(idx, "Pressure", 101.3)
        await pressure_var.set_writable()

        # Map variable names to NodeIds for tests
        node_ids = {
            "Temperature": temp_var.nodeid.to_string(),
            "Pressure": pressure_var.nodeid.to_string(),
            "TestObject": test_obj.nodeid.to_string(),
        }

        # Start server
        async with server:
            yield server, node_ids

    @pytest.fixture
    def opcua_config(self) -> OpcUaConfig:
        """Create OPC-UA config for test server."""
        return OpcUaConfig(
            endpoint_url="opc.tcp://localhost:4840/test/",
            security_mode=OpcUaSecurityMode.NONE,
            timeout=5.0,
        )

    @pytest.mark.asyncio
    async def test_connect_to_server(
        self,
        opcua_server: tuple[Any, dict[str, str]],
        opcua_config: OpcUaConfig,
    ) -> None:
        """Connect to OPC-UA server successfully."""
        server, node_ids = opcua_server
        client = OpcUaClient(opcua_config)

        result = await client.connect()

        assert result is True
        assert client.is_connected

        await client.disconnect()
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_read_node_value(
        self,
        opcua_server: tuple[Any, dict[str, str]],
        opcua_config: OpcUaConfig,
    ) -> None:
        """Read node value from OPC-UA server."""
        server, node_ids = opcua_server
        client = OpcUaClient(opcua_config)
        await client.connect()

        # Read Temperature variable using actual NodeId
        result = await client.read_node(node_ids["Temperature"])

        assert result is not None
        assert result.value == 25.5
        assert result.status == "Good"

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_write_node_value(
        self,
        opcua_server: tuple[Any, dict[str, str]],
        opcua_config: OpcUaConfig,
    ) -> None:
        """Write node value to OPC-UA server."""
        server, node_ids = opcua_server
        client = OpcUaClient(opcua_config)
        await client.connect()

        # Write new temperature value
        write_result = await client.write_node(node_ids["Temperature"], 30.0)
        assert write_result is True

        # Read back to verify
        read_result = await client.read_node(node_ids["Temperature"])
        assert read_result is not None
        assert read_result.value == 30.0

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_subscribe_to_value_changes(
        self,
        opcua_server: tuple[Any, dict[str, str]],
        opcua_config: OpcUaConfig,
    ) -> None:
        """Subscribe to node value changes."""
        server, node_ids = opcua_server
        client = OpcUaClient(opcua_config)
        await client.connect()

        # Track received values
        received_values = []

        def on_value_change(node_id: str, value: Any) -> None:
            """Callback for value changes."""
            received_values.append((node_id, value))

        # Subscribe to Temperature
        subscription_id = await client.subscribe(
            [node_ids["Temperature"]],
            on_value_change,
            interval=0.5,
        )

        assert subscription_id is not None

        # Write a new value to trigger callback
        await client.write_node(node_ids["Temperature"], 35.0)

        # Wait for subscription notification
        await asyncio.sleep(2)

        # Verify callback was called
        assert len(received_values) > 0

        # Unsubscribe
        unsub_result = await client.unsubscribe(subscription_id)
        assert unsub_result is True

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_browse_nodes(
        self,
        opcua_server: tuple[Any, dict[str, str]],
        opcua_config: OpcUaConfig,
    ) -> None:
        """Browse OPC-UA server node tree."""
        server, node_ids = opcua_server
        client = OpcUaClient(opcua_config)
        await client.connect()

        # Browse Objects folder
        children = await client.browse("i=85")  # Objects folder

        assert len(children) > 0

        # Check that our TestObject is in the list
        test_obj_found = any("TestObject" in child.get("browse_name", "") for child in children)
        assert test_obj_found

        await client.disconnect()

    @pytest.mark.asyncio
    async def test_reconnection_after_disconnect(
        self,
        opcua_server: tuple[Any, dict[str, str]],
        opcua_config: OpcUaConfig,
    ) -> None:
        """Verify client can reconnect after disconnect."""
        server, node_ids = opcua_server
        client = OpcUaClient(opcua_config)

        # Initial connection
        await client.connect()
        assert client.is_connected

        # Read a value
        result1 = await client.read_node(node_ids["Temperature"])
        assert result1 is not None

        # Disconnect
        await client.disconnect()
        assert not client.is_connected

        # Reconnect
        await client.connect()
        assert client.is_connected

        # Read value again
        result2 = await client.read_node(node_ids["Temperature"])
        assert result2 is not None

        await client.disconnect()
