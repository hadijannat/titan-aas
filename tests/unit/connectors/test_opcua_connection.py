"""Tests for OPC-UA connection manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from titan.connectors.opcua.client import OpcUaConfig, OpcUaSecurityMode
from titan.connectors.opcua.connection import (
    OpcUaConnectionManager,
    OpcUaConnectionState,
    create_opcua_config_from_settings,
)


class TestOpcUaConnectionManager:
    """Test OPC-UA connection manager."""

    @pytest.fixture
    def opcua_config(self) -> OpcUaConfig:
        """Create OPC-UA config for testing."""
        return OpcUaConfig(
            endpoint_url="opc.tcp://localhost:4840",
            security_mode=OpcUaSecurityMode.NONE,
        )

    @pytest.fixture
    def connection_manager(self, opcua_config: OpcUaConfig) -> OpcUaConnectionManager:
        """Create connection manager instance."""
        return OpcUaConnectionManager(opcua_config)

    def test_initial_state(self, connection_manager: OpcUaConnectionManager) -> None:
        """Connection manager starts in disconnected state."""
        assert connection_manager.state == OpcUaConnectionState.DISCONNECTED
        assert not connection_manager.is_connected
        assert connection_manager.metrics.connection_attempts == 0

    @pytest.mark.asyncio
    async def test_connect_success(
        self, connection_manager: OpcUaConnectionManager
    ) -> None:
        """Connect successfully to OPC-UA server."""
        with patch("titan.connectors.opcua.connection.OpcUaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            result = await connection_manager.connect()

            assert result is True
            assert connection_manager.state == OpcUaConnectionState.CONNECTED
            assert connection_manager.is_connected
            assert connection_manager.metrics.connection_attempts == 1
            assert connection_manager.metrics.successful_connections == 1

    @pytest.mark.asyncio
    async def test_connect_failure(
        self, connection_manager: OpcUaConnectionManager
    ) -> None:
        """Connection failure sets state to disconnected."""
        with patch("titan.connectors.opcua.connection.OpcUaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            result = await connection_manager.connect()

            assert result is False
            assert connection_manager.state == OpcUaConnectionState.DISCONNECTED
            assert not connection_manager.is_connected
            assert connection_manager.metrics.connection_attempts == 1
            assert connection_manager.metrics.successful_connections == 0

    @pytest.mark.asyncio
    async def test_connect_already_connected(
        self, connection_manager: OpcUaConnectionManager
    ) -> None:
        """Connecting when already connected returns True immediately."""
        with patch("titan.connectors.opcua.connection.OpcUaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            # First connection
            await connection_manager.connect()
            first_attempts = connection_manager.metrics.connection_attempts

            # Second connection attempt
            result = await connection_manager.connect()

            assert result is True
            # Should not increment attempts since already connected
            assert connection_manager.metrics.connection_attempts == first_attempts

    @pytest.mark.asyncio
    async def test_disconnect(self, connection_manager: OpcUaConnectionManager) -> None:
        """Disconnect from OPC-UA server."""
        with patch("titan.connectors.opcua.connection.OpcUaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client.disconnect = AsyncMock()
            mock_client_class.return_value = mock_client

            # Connect first
            await connection_manager.connect()
            assert connection_manager.is_connected

            # Then disconnect
            await connection_manager.disconnect()

            assert connection_manager.state == OpcUaConnectionState.DISCONNECTED
            assert not connection_manager.is_connected
            assert connection_manager.metrics.disconnections == 1
            mock_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_connected_when_connected(
        self, connection_manager: OpcUaConnectionManager
    ) -> None:
        """ensure_connected returns client when already connected."""
        with patch("titan.connectors.opcua.connection.OpcUaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.connect = AsyncMock(return_value=True)
            mock_client_class.return_value = mock_client

            await connection_manager.connect()

            client = await connection_manager.ensure_connected()

            assert client is mock_client

    @pytest.mark.asyncio
    async def test_health_check(self, connection_manager: OpcUaConnectionManager) -> None:
        """Health check returns status information."""
        health = await connection_manager.health_check()

        assert "connected" in health
        assert "state" in health
        assert "endpoint" in health
        assert "reconnect_attempts" in health
        assert "metrics" in health
        assert health["connected"] is False
        assert health["state"] == "disconnected"
        assert health["endpoint"] == "opc.tcp://localhost:4840"


class TestOpcUaConfigFactory:
    """Test OPC-UA config factory functions."""

    @pytest.mark.asyncio
    async def test_create_config_from_settings_disabled(self) -> None:
        """Config is None when OPC-UA is disabled."""
        with patch("titan.connectors.opcua.connection.settings") as mock_settings:
            mock_settings.opcua_enabled = False

            config = create_opcua_config_from_settings()

            assert config is None

    @pytest.mark.asyncio
    async def test_create_config_from_settings_no_endpoint(self) -> None:
        """Config is None when no endpoint configured."""
        with patch("titan.connectors.opcua.connection.settings") as mock_settings:
            mock_settings.opcua_enabled = True
            mock_settings.opcua_endpoint = None

            config = create_opcua_config_from_settings()

            assert config is None

    @pytest.mark.asyncio
    async def test_create_config_from_settings_success(self) -> None:
        """Config created from settings."""
        with patch("titan.connectors.opcua.connection.settings") as mock_settings:
            mock_settings.opcua_enabled = True
            mock_settings.opcua_endpoint = "opc.tcp://localhost:4840"
            mock_settings.opcua_security_mode = "None"
            mock_settings.opcua_username = None
            mock_settings.opcua_password = None
            mock_settings.opcua_timeout = 5
            mock_settings.opcua_reconnect_delay_initial = 1.0

            config = create_opcua_config_from_settings()

            assert config is not None
            assert config.endpoint_url == "opc.tcp://localhost:4840"
            assert config.security_mode == OpcUaSecurityMode.NONE
            assert config.timeout == 5.0
            assert config.reconnect_interval == 1.0
