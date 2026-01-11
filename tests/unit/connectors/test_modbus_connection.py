"""Unit tests for Modbus connection manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from titan.connectors.modbus.client import ModbusClient, ModbusConfig
from titan.connectors.modbus.connection import (
    ModbusConnectionManager,
    ModbusConnectionState,
    create_modbus_config_from_settings,
)


class TestModbusConnectionManager:
    """Test ModbusConnectionManager class."""

    @pytest.fixture
    def modbus_config(self) -> ModbusConfig:
        """Create test Modbus config."""
        return ModbusConfig(
            host="localhost",
            port=502,
            mode="tcp",
            unit_id=1,
            timeout=3.0,
            reconnect_interval=1.0,
        )

    @pytest.fixture
    def connection_manager(self, modbus_config: ModbusConfig) -> ModbusConnectionManager:
        """Create connection manager instance."""
        return ModbusConnectionManager(modbus_config)

    def test_initial_state(self, connection_manager: ModbusConnectionManager) -> None:
        """Connection manager starts in disconnected state."""
        assert connection_manager.state == ModbusConnectionState.DISCONNECTED
        assert connection_manager.is_connected is False
        assert connection_manager.metrics.connection_attempts == 0

    @pytest.mark.asyncio
    async def test_connect_success(self, connection_manager: ModbusConnectionManager) -> None:
        """Successfully connect to Modbus server."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            result = await connection_manager.connect()

            assert result is True
            assert connection_manager.state == ModbusConnectionState.CONNECTED
            assert connection_manager.is_connected is True
            assert connection_manager.metrics.connection_attempts == 1
            assert connection_manager.metrics.successful_connections == 1

    @pytest.mark.asyncio
    async def test_connect_already_connected(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """Connect when already connected returns True."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            # First connection
            await connection_manager.connect()
            assert connection_manager.metrics.connection_attempts == 1

            # Second connection attempt (already connected)
            result = await connection_manager.connect()
            assert result is True
            assert connection_manager.metrics.connection_attempts == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_connect_failure(self, connection_manager: ModbusConnectionManager) -> None:
        """Connection failure sets disconnected state."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = False
            result = await connection_manager.connect()

            assert result is False
            assert connection_manager.state == ModbusConnectionState.DISCONNECTED
            assert connection_manager.is_connected is False
            assert connection_manager.metrics.connection_attempts == 1
            assert connection_manager.metrics.successful_connections == 0

    @pytest.mark.asyncio
    async def test_connect_exception(self, connection_manager: ModbusConnectionManager) -> None:
        """Connection exception sets disconnected state."""
        with patch.object(
            ModbusClient,
            "connect",
            new_callable=AsyncMock,
            side_effect=Exception("Connection error"),
        ):
            result = await connection_manager.connect()

            assert result is False
            assert connection_manager.state == ModbusConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_disconnect(self, connection_manager: ModbusConnectionManager) -> None:
        """Disconnect from Modbus server."""
        # First connect
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            await connection_manager.connect()
            assert connection_manager.is_connected is True

        # Then disconnect
        with patch.object(ModbusClient, "disconnect", new_callable=AsyncMock):
            await connection_manager.disconnect()

            assert connection_manager.state == ModbusConnectionState.DISCONNECTED
            assert connection_manager.is_connected is False
            assert connection_manager.metrics.disconnections == 1

    @pytest.mark.asyncio
    async def test_ensure_connected_when_connected(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """ensure_connected returns client when already connected."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            await connection_manager.connect()

            client = await connection_manager.ensure_connected()
            assert isinstance(client, ModbusClient)

    @pytest.mark.asyncio
    async def test_ensure_connected_when_disconnected(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """ensure_connected connects and returns client."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            client = await connection_manager.ensure_connected()

            assert isinstance(client, ModbusClient)
            assert connection_manager.is_connected is True

    @pytest.mark.asyncio
    async def test_ensure_connected_when_failed(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """ensure_connected raises when in failed state."""
        connection_manager._state = ModbusConnectionState.FAILED

        with pytest.raises(RuntimeError, match="failed after max reconnect attempts"):
            await connection_manager.ensure_connected()

    @pytest.mark.asyncio
    async def test_ensure_connected_starts_reconnect_on_failure(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """ensure_connected starts reconnect task on connection failure."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = False
            with pytest.raises(RuntimeError, match="reconnection in progress"):
                await connection_manager.ensure_connected()

            # Reconnect task should be created
            assert connection_manager._reconnect_task is not None

            # Clean up the task
            if connection_manager._reconnect_task:
                connection_manager._reconnect_task.cancel()

    @pytest.mark.asyncio
    async def test_health_check(self, connection_manager: ModbusConnectionManager) -> None:
        """Health check returns connection status."""
        health = await connection_manager.health_check()

        assert "connected" in health
        assert "state" in health
        assert "host" in health
        assert "port" in health
        assert "mode" in health
        assert "metrics" in health

        assert health["connected"] is False
        assert health["state"] == "disconnected"
        assert health["host"] == "localhost"
        assert health["port"] == 502

    @pytest.mark.asyncio
    async def test_reconnect_backoff_reset_on_success(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """Successful connection resets backoff delay."""
        connection_manager._current_delay = 10.0
        connection_manager._reconnect_attempts = 3

        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            await connection_manager.connect()

            assert connection_manager._current_delay == 1.0  # Reset to initial
            assert connection_manager._reconnect_attempts == 0  # Reset


class TestModbusConnectionManagerMetrics:
    """Test ModbusConnectionManager metrics tracking."""

    @pytest.fixture
    def connection_manager(self) -> ModbusConnectionManager:
        """Create connection manager instance."""
        config = ModbusConfig(
            host="localhost",
            port=502,
            mode="tcp",
            reconnect_interval=1.0,
        )
        return ModbusConnectionManager(config)

    @pytest.mark.asyncio
    async def test_metrics_track_connection_attempts(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """Metrics track all connection attempts."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = False
            # First attempt will set state to CONNECTING
            await connection_manager.connect()
            assert connection_manager.metrics.connection_attempts == 1

            # Reset to disconnected manually for next attempts
            connection_manager._state = ModbusConnectionState.DISCONNECTED
            await connection_manager.connect()
            assert connection_manager.metrics.connection_attempts == 2

            connection_manager._state = ModbusConnectionState.DISCONNECTED
            await connection_manager.connect()
            assert connection_manager.metrics.connection_attempts == 3

    @pytest.mark.asyncio
    async def test_metrics_track_successful_connections(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """Metrics track successful connections."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            await connection_manager.connect()

            assert connection_manager.metrics.connection_attempts == 1
            assert connection_manager.metrics.successful_connections == 1

    @pytest.mark.asyncio
    async def test_metrics_track_disconnections(
        self, connection_manager: ModbusConnectionManager
    ) -> None:
        """Metrics track disconnections."""
        with patch.object(ModbusClient, "connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            await connection_manager.connect()

        with patch.object(ModbusClient, "disconnect", new_callable=AsyncMock):
            await connection_manager.disconnect()
            assert connection_manager.metrics.disconnections == 1

    def test_metrics_to_dict(self, connection_manager: ModbusConnectionManager) -> None:
        """Metrics can be exported as dictionary."""
        metrics_dict = connection_manager.metrics.to_dict()

        assert "reads_total" in metrics_dict
        assert "writes_total" in metrics_dict
        assert "connection_attempts" in metrics_dict
        assert "state" in metrics_dict


class TestCreateModbusConfigFromSettings:
    """Test factory function for creating config from settings."""

    def test_create_config_when_disabled(self) -> None:
        """Returns None when Modbus is disabled."""
        with patch("titan.connectors.modbus.connection.settings") as mock_settings:
            mock_settings.modbus_enabled = False

            config = create_modbus_config_from_settings()
            assert config is None

    def test_create_config_when_no_host(self) -> None:
        """Returns None when no host configured."""
        with patch("titan.connectors.modbus.connection.settings") as mock_settings:
            mock_settings.modbus_enabled = True
            mock_settings.modbus_host = None

            config = create_modbus_config_from_settings()
            assert config is None

    def test_create_config_success(self) -> None:
        """Creates config from settings."""
        with patch("titan.connectors.modbus.connection.settings") as mock_settings:
            mock_settings.modbus_enabled = True
            mock_settings.modbus_host = "192.168.1.100"
            mock_settings.modbus_port = 502
            mock_settings.modbus_mode = "tcp"
            mock_settings.modbus_unit_id = 1
            mock_settings.modbus_timeout = 5.0
            mock_settings.modbus_reconnect_interval = 2.0
            mock_settings.modbus_serial_port = None
            mock_settings.modbus_baudrate = 9600

            config = create_modbus_config_from_settings()

            assert config is not None
            assert config.host == "192.168.1.100"
            assert config.port == 502
            assert config.mode == "tcp"
            assert config.unit_id == 1
            assert config.timeout == 5.0
            assert config.reconnect_interval == 2.0
