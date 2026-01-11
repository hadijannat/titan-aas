"""Tests for OPC-UA client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from titan.connectors.opcua.client import OpcUaClient, OpcUaConfig, OpcUaSecurityMode


class TestOpcUaClient:
    """Test OpcUaClient."""

    @pytest.fixture
    def opcua_config(self) -> OpcUaConfig:
        """Create OPC-UA config for testing."""
        return OpcUaConfig(
            endpoint_url="opc.tcp://localhost:4840",
            security_mode=OpcUaSecurityMode.NONE,
        )

    @pytest.fixture
    def mock_asyncua_client(self) -> MagicMock:
        """Create mock asyncua client."""
        client = MagicMock()
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        client.set_user = MagicMock()
        client.set_password = MagicMock()
        client.set_security_string = AsyncMock()
        return client

    @pytest.fixture
    def opcua_client(self, opcua_config: OpcUaConfig) -> OpcUaClient:
        """Create OpcUaClient instance."""
        return OpcUaClient(opcua_config)

    @pytest.mark.asyncio
    async def test_config_validation(self) -> None:
        """OPC-UA config validates endpoint URL."""
        config = OpcUaConfig(
            endpoint_url="opc.tcp://localhost:4840",
            security_mode=OpcUaSecurityMode.NONE,
        )
        assert config.endpoint_url == "opc.tcp://localhost:4840"
        assert config.security_mode == OpcUaSecurityMode.NONE
        assert config.timeout == 10.0

    @pytest.mark.asyncio
    async def test_connect_success(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Connect to OPC-UA server successfully."""
        with patch("asyncua.Client", return_value=mock_asyncua_client):
            result = await opcua_client.connect()

            assert result is True
            assert opcua_client.is_connected
            mock_asyncua_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_credentials(self, mock_asyncua_client: MagicMock) -> None:
        """Connect with username/password."""
        config = OpcUaConfig(
            endpoint_url="opc.tcp://localhost:4840",
            security_mode=OpcUaSecurityMode.NONE,
            username="admin",
            password="password123",  # noqa: S106
        )
        client = OpcUaClient(config)

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            result = await client.connect()

            assert result is True
            mock_asyncua_client.set_user.assert_called_once_with("admin")
            mock_asyncua_client.set_password.assert_called_once_with("password123")

    @pytest.mark.asyncio
    async def test_connect_timeout(self, opcua_client: OpcUaClient) -> None:
        """Connection timeout returns False."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=TimeoutError("Connection timeout"))

        with patch("asyncua.Client", return_value=mock_client):
            with patch("asyncio.wait_for", side_effect=TimeoutError("Connection timeout")):
                result = await opcua_client.connect()

                assert result is False
                assert not opcua_client.is_connected

    @pytest.mark.asyncio
    async def test_connect_error(self, opcua_client: OpcUaClient) -> None:
        """Connection error returns False."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("asyncua.Client", return_value=mock_client):
            result = await opcua_client.connect()

            assert result is False
            assert not opcua_client.is_connected

    @pytest.mark.asyncio
    async def test_disconnect(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Disconnect from OPC-UA server."""
        # First connect
        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()
            assert opcua_client.is_connected

            # Then disconnect
            await opcua_client.disconnect()
            assert not opcua_client.is_connected
            mock_asyncua_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_node_not_connected(self, opcua_client: OpcUaClient) -> None:
        """Reading node when not connected returns None."""
        result = await opcua_client.read_node("ns=2;s=Temperature")
        assert result is None

    @pytest.mark.asyncio
    async def test_read_node_success(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Read node value successfully."""
        # Mock node and data value
        mock_node = MagicMock()
        mock_node.read_value = AsyncMock(return_value=25.5)
        mock_node.read_data_type = AsyncMock(return_value="Double")

        mock_data_value = MagicMock()
        mock_status_code = MagicMock()
        mock_status_code.is_good = MagicMock(return_value=True)
        mock_data_value.StatusCode = mock_status_code
        mock_node.read_data_value = AsyncMock(return_value=mock_data_value)

        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.read_node("ns=2;s=Temperature")

            assert result is not None
            assert result.node_id == "ns=2;s=Temperature"
            assert result.value == 25.5
            assert result.status == "Good"

    @pytest.mark.asyncio
    async def test_read_node_error(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Reading node with error returns None."""
        mock_node = MagicMock()
        mock_node.read_value = AsyncMock(side_effect=Exception("Node not found"))
        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.read_node("ns=2;s=InvalidNode")
            assert result is None

    @pytest.mark.asyncio
    async def test_write_node_not_connected(self, opcua_client: OpcUaClient) -> None:
        """Writing node when not connected returns False."""
        result = await opcua_client.write_node("ns=2;s=Temperature", 30.5)
        assert result is False

    @pytest.mark.asyncio
    async def test_write_node_success(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Write node value successfully."""
        # Mock node
        mock_node = MagicMock()
        mock_node.write_value = AsyncMock()
        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.write_node("ns=2;s=Temperature", 30.5)

            assert result is True
            mock_asyncua_client.get_node.assert_called_once_with("ns=2;s=Temperature")
            mock_node.write_value.assert_called_once_with(30.5)

    @pytest.mark.asyncio
    async def test_write_node_error(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Writing node with error returns False."""
        mock_node = MagicMock()
        mock_node.write_value = AsyncMock(side_effect=Exception("Write failed"))
        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.write_node("ns=2;s=InvalidNode", 100)
            assert result is False

    @pytest.mark.asyncio
    async def test_subscribe_not_connected(self, opcua_client: OpcUaClient) -> None:
        """Subscribing when not connected returns None."""
        callback = MagicMock()
        result = await opcua_client.subscribe(["ns=2;s=Temperature"], callback)
        assert result is None

    @pytest.mark.asyncio
    async def test_subscribe_success(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Subscribe to node value changes successfully."""
        # Mock subscription and node
        mock_subscription = MagicMock()
        mock_subscription.subscribe_data_change = AsyncMock(return_value="handle_1")
        mock_asyncua_client.create_subscription = AsyncMock(return_value=mock_subscription)

        mock_node = MagicMock()
        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        callback = MagicMock()

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.subscribe(
                ["ns=2;s=Temperature", "ns=2;s=Pressure"], callback, interval=2.0
            )

            assert result is not None
            assert result.startswith("sub_")
            mock_asyncua_client.create_subscription.assert_called_once()
            assert mock_subscription.subscribe_data_change.call_count == 2

    @pytest.mark.asyncio
    async def test_subscribe_error(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Subscribing with error returns None."""
        mock_asyncua_client.create_subscription = AsyncMock(
            side_effect=Exception("Subscription failed")
        )

        callback = MagicMock()

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.subscribe(["ns=2;s=Temperature"], callback)
            assert result is None

    @pytest.mark.asyncio
    async def test_unsubscribe_success(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Unsubscribe from value changes successfully."""
        # First subscribe
        mock_subscription = MagicMock()
        mock_subscription.subscribe_data_change = AsyncMock(return_value="handle_1")
        mock_subscription.delete = AsyncMock()
        mock_asyncua_client.create_subscription = AsyncMock(return_value=mock_subscription)

        mock_node = MagicMock()
        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        callback = MagicMock()

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            subscription_id = await opcua_client.subscribe(["ns=2;s=Temperature"], callback)
            assert subscription_id is not None

            # Then unsubscribe
            result = await opcua_client.unsubscribe(subscription_id)
            assert result is True
            mock_subscription.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe_not_found(self, opcua_client: OpcUaClient) -> None:
        """Unsubscribing non-existent subscription returns False."""
        result = await opcua_client.unsubscribe("sub_nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_browse_not_connected(self, opcua_client: OpcUaClient) -> None:
        """Browsing when not connected returns empty list."""
        result = await opcua_client.browse("i=84")
        assert result == []

    @pytest.mark.asyncio
    async def test_browse_success(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Browse child nodes successfully."""
        # Mock node and children
        mock_child1 = MagicMock()
        mock_child1.nodeid = "ns=2;s=Child1"
        mock_child1.read_browse_name = AsyncMock(
            return_value=MagicMock(to_string=lambda: "2:Child1")
        )
        mock_child1.read_node_class = AsyncMock(
            return_value=MagicMock(__str__=lambda self: "Variable")
        )
        mock_child1.read_display_name = AsyncMock(
            return_value=MagicMock(to_string=lambda: "Child Node 1")
        )

        mock_child2 = MagicMock()
        mock_child2.nodeid = "ns=2;s=Child2"
        mock_child2.read_browse_name = AsyncMock(
            return_value=MagicMock(to_string=lambda: "2:Child2")
        )
        mock_child2.read_node_class = AsyncMock(
            return_value=MagicMock(__str__=lambda self: "Object")
        )
        mock_child2.read_display_name = AsyncMock(
            return_value=MagicMock(to_string=lambda: "Child Node 2")
        )

        mock_node = MagicMock()
        mock_node.get_children = AsyncMock(return_value=[mock_child1, mock_child2])
        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.browse("i=84")

            assert len(result) == 2
            assert result[0]["nodeid"] == "ns=2;s=Child1"
            assert result[0]["browse_name"] == "2:Child1"
            assert result[0]["node_class"] == "Variable"
            assert result[0]["display_name"] == "Child Node 1"
            assert result[1]["nodeid"] == "ns=2;s=Child2"

    @pytest.mark.asyncio
    async def test_browse_error(
        self, opcua_client: OpcUaClient, mock_asyncua_client: MagicMock
    ) -> None:
        """Browsing with error returns empty list."""
        mock_node = MagicMock()
        mock_node.get_children = AsyncMock(side_effect=Exception("Browse failed"))
        mock_asyncua_client.get_node = MagicMock(return_value=mock_node)

        with patch("asyncua.Client", return_value=mock_asyncua_client):
            await opcua_client.connect()

            result = await opcua_client.browse("i=84")
            assert result == []


class TestOpcUaConfig:
    """Test OPC-UA configuration."""

    def test_default_config(self) -> None:
        """Default config has sensible defaults."""
        config = OpcUaConfig(endpoint_url="opc.tcp://localhost:4840")

        assert config.endpoint_url == "opc.tcp://localhost:4840"
        assert config.security_mode == OpcUaSecurityMode.NONE
        assert config.username is None
        assert config.password is None
        assert config.timeout == 10.0
        assert config.reconnect_interval == 5

    def test_custom_config(self) -> None:
        """Custom config values are set correctly."""
        config = OpcUaConfig(
            endpoint_url="opc.tcp://remote-server:4840",
            security_mode=OpcUaSecurityMode.SIGN,
            username="user1",
            password="pass123",  # noqa: S106
            timeout=15.0,
            reconnect_interval=20,
        )

        assert config.endpoint_url == "opc.tcp://remote-server:4840"
        assert config.security_mode == OpcUaSecurityMode.SIGN
        assert config.username == "user1"
        assert config.password == "pass123"
        assert config.timeout == 15.0
        assert config.reconnect_interval == 20

    def test_security_modes(self) -> None:
        """Security mode enum has correct values."""
        assert OpcUaSecurityMode.NONE.value == "None"
        assert OpcUaSecurityMode.SIGN.value == "Sign"
        assert OpcUaSecurityMode.SIGN_AND_ENCRYPT.value == "SignAndEncrypt"
