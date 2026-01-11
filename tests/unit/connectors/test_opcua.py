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
            password="password123",
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
            password="pass123",
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
