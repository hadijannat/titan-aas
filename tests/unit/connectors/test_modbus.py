"""Tests for Modbus client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from titan.connectors.modbus.client import ModbusClient, ModbusConfig
from titan.connectors.modbus.poller import ModbusPoller, PollConfig


class TestModbusClient:
    """Test ModbusClient."""

    @pytest.fixture
    def modbus_config_tcp(self) -> ModbusConfig:
        """Create Modbus TCP config for testing."""
        return ModbusConfig(
            host="localhost",
            port=502,
            mode="tcp",
            unit_id=1,
            timeout=3.0,
        )

    @pytest.fixture
    def modbus_config_rtu(self) -> ModbusConfig:
        """Create Modbus RTU config for testing."""
        return ModbusConfig(
            host="",  # Not used for RTU
            mode="rtu",
            serial_port="/dev/ttyUSB0",
            baudrate=9600,
            unit_id=1,
            timeout=3.0,
        )

    @pytest.fixture
    def mock_modbus_tcp_client(self) -> MagicMock:
        """Create mock pymodbus TCP client."""
        client = MagicMock()
        client.connect = AsyncMock()
        client.close = MagicMock()
        return client

    @pytest.fixture
    def modbus_client_tcp(self, modbus_config_tcp: ModbusConfig) -> ModbusClient:
        """Create ModbusClient instance for TCP."""
        return ModbusClient(modbus_config_tcp)

    @pytest.mark.asyncio
    async def test_config_validation_tcp(self) -> None:
        """Modbus TCP config validates correctly."""
        config = ModbusConfig(
            host="192.168.1.100",
            port=502,
            mode="tcp",
            unit_id=1,
        )
        assert config.host == "192.168.1.100"
        assert config.port == 502
        assert config.mode == "tcp"
        assert config.unit_id == 1
        assert config.timeout == 3.0

    @pytest.mark.asyncio
    async def test_config_validation_rtu(self) -> None:
        """Modbus RTU config validates correctly."""
        config = ModbusConfig(
            host="",
            mode="rtu",
            serial_port="/dev/ttyUSB0",
            baudrate=9600,
            parity="N",
            stopbits=1,
        )
        assert config.mode == "rtu"
        assert config.serial_port == "/dev/ttyUSB0"
        assert config.baudrate == 9600
        assert config.parity == "N"
        assert config.stopbits == 1

    @pytest.mark.asyncio
    async def test_connect_tcp_success(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Connect to Modbus TCP server successfully."""
        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            result = await modbus_client_tcp.connect()

            assert result is True
            assert modbus_client_tcp.is_connected
            mock_modbus_tcp_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_tcp_timeout(self, modbus_client_tcp: ModbusClient) -> None:
        """Connection timeout returns False."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=TimeoutError("Connection timeout"))

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_client):
            with patch("asyncio.wait_for", side_effect=TimeoutError("Connection timeout")):
                result = await modbus_client_tcp.connect()

                assert result is False
                assert not modbus_client_tcp.is_connected

    @pytest.mark.asyncio
    async def test_connect_tcp_error(self, modbus_client_tcp: ModbusClient) -> None:
        """Connection error returns False."""
        mock_client = MagicMock()
        mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_client):
            result = await modbus_client_tcp.connect()

            assert result is False
            assert not modbus_client_tcp.is_connected

    @pytest.mark.asyncio
    async def test_disconnect(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Disconnect from Modbus server."""
        # First connect
        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()
            assert modbus_client_tcp.is_connected

            # Then disconnect
            await modbus_client_tcp.disconnect()
            assert not modbus_client_tcp.is_connected
            mock_modbus_tcp_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_coils_not_connected(self, modbus_client_tcp: ModbusClient) -> None:
        """Reading coils when not connected returns None."""
        result = await modbus_client_tcp.read_coils(address=0, count=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_read_coils_success(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Read coils successfully."""
        # Mock response
        mock_response = MagicMock()
        mock_response.isError = MagicMock(return_value=False)
        mock_response.bits = [True, False, True]

        mock_modbus_tcp_client.read_coils = AsyncMock(return_value=mock_response)

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()

            result = await modbus_client_tcp.read_coils(address=0, count=3)

            assert result is not None
            assert result == [True, False, True]
            mock_modbus_tcp_client.read_coils.assert_called_once_with(
                address=0, count=3, slave=1
            )

    @pytest.mark.asyncio
    async def test_read_coils_error(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Reading coils with error returns None."""
        mock_response = MagicMock()
        mock_response.isError = MagicMock(return_value=True)

        mock_modbus_tcp_client.read_coils = AsyncMock(return_value=mock_response)

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()

            result = await modbus_client_tcp.read_coils(address=0, count=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_read_holding_registers_success(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Read holding registers successfully."""
        # Mock response
        mock_response = MagicMock()
        mock_response.isError = MagicMock(return_value=False)
        mock_response.registers = [100, 200, 300]

        mock_modbus_tcp_client.read_holding_registers = AsyncMock(return_value=mock_response)

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()

            result = await modbus_client_tcp.read_holding_registers(address=0, count=3)

            assert result is not None
            assert result == [100, 200, 300]
            mock_modbus_tcp_client.read_holding_registers.assert_called_once_with(
                address=0, count=3, slave=1
            )

    @pytest.mark.asyncio
    async def test_write_coil_not_connected(self, modbus_client_tcp: ModbusClient) -> None:
        """Writing coil when not connected returns False."""
        result = await modbus_client_tcp.write_coil(address=0, value=True)
        assert result is False

    @pytest.mark.asyncio
    async def test_write_coil_success(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Write coil successfully."""
        mock_response = MagicMock()
        mock_response.isError = MagicMock(return_value=False)

        mock_modbus_tcp_client.write_coil = AsyncMock(return_value=mock_response)

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()

            result = await modbus_client_tcp.write_coil(address=0, value=True)

            assert result is True
            mock_modbus_tcp_client.write_coil.assert_called_once_with(
                address=0, value=True, slave=1
            )

    @pytest.mark.asyncio
    async def test_write_register_success(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Write register successfully."""
        mock_response = MagicMock()
        mock_response.isError = MagicMock(return_value=False)

        mock_modbus_tcp_client.write_register = AsyncMock(return_value=mock_response)

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()

            result = await modbus_client_tcp.write_register(address=100, value=500)

            assert result is True
            mock_modbus_tcp_client.write_register.assert_called_once_with(
                address=100, value=500, slave=1
            )

    @pytest.mark.asyncio
    async def test_write_register_invalid_value(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Writing register with invalid value returns False."""
        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()

            # Value too large
            result = await modbus_client_tcp.write_register(address=100, value=70000)
            assert result is False

            # Negative value
            result = await modbus_client_tcp.write_register(address=100, value=-1)
            assert result is False

    @pytest.mark.asyncio
    async def test_write_multiple_registers_success(
        self, modbus_client_tcp: ModbusClient, mock_modbus_tcp_client: MagicMock
    ) -> None:
        """Write multiple registers successfully."""
        mock_response = MagicMock()
        mock_response.isError = MagicMock(return_value=False)

        mock_modbus_tcp_client.write_registers = AsyncMock(return_value=mock_response)

        with patch("pymodbus.client.AsyncModbusTcpClient", return_value=mock_modbus_tcp_client):
            await modbus_client_tcp.connect()

            result = await modbus_client_tcp.write_multiple_registers(
                address=100, values=[100, 200, 300]
            )

            assert result is True
            mock_modbus_tcp_client.write_registers.assert_called_once_with(
                address=100, values=[100, 200, 300], slave=1
            )


class TestModbusConfig:
    """Test Modbus configuration."""

    def test_default_tcp_config(self) -> None:
        """Default TCP config has sensible defaults."""
        config = ModbusConfig(host="localhost")

        assert config.host == "localhost"
        assert config.port == 502
        assert config.mode == "tcp"
        assert config.unit_id == 1
        assert config.timeout == 3.0
        assert config.reconnect_interval == 5.0

    def test_custom_tcp_config(self) -> None:
        """Custom TCP config values are set correctly."""
        config = ModbusConfig(
            host="192.168.1.100",
            port=5020,
            mode="tcp",
            unit_id=2,
            timeout=5.0,
            reconnect_interval=10.0,
        )

        assert config.host == "192.168.1.100"
        assert config.port == 5020
        assert config.unit_id == 2
        assert config.timeout == 5.0
        assert config.reconnect_interval == 10.0

    def test_rtu_config(self) -> None:
        """RTU config values are set correctly."""
        config = ModbusConfig(
            host="",
            mode="rtu",
            serial_port="/dev/ttyUSB0",
            baudrate=19200,
            parity="E",
            stopbits=1,
        )

        assert config.mode == "rtu"
        assert config.serial_port == "/dev/ttyUSB0"
        assert config.baudrate == 19200
        assert config.parity == "E"
        assert config.stopbits == 1


class TestModbusPoller:
    """Test ModbusPoller."""

    @pytest.fixture
    def modbus_client_mock(self) -> MagicMock:
        """Create mock ModbusClient."""
        client = MagicMock()
        client.read_holding_registers = AsyncMock(return_value=[100, 200])
        client.read_coils = AsyncMock(return_value=[True, False])
        return client

    @pytest.fixture
    def poller(self, modbus_client_mock: MagicMock) -> ModbusPoller:
        """Create ModbusPoller instance."""
        return ModbusPoller(modbus_client_mock)

    @pytest.mark.asyncio
    async def test_start_polling(self, poller: ModbusPoller) -> None:
        """Start polling creates a task."""
        config = PollConfig(
            register_address=100,
            register_type="holding_register",
            interval=0.1,
        )

        callback = MagicMock()
        poll_id = poller.start_polling(config, callback)
        assert poll_id
        assert poll_id
        assert poll_id

        assert poll_id == "holding_register:100"
        assert poller.is_running
        assert poll_id in poller._poll_tasks

        # Cleanup
        poller.stop_all()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_stop_polling(self, poller: ModbusPoller) -> None:
        """Stop polling cancels the task."""
        config = PollConfig(
            register_address=100,
            register_type="holding_register",
            interval=0.1,
        )

        callback = MagicMock()
        poll_id = poller.start_polling(config, callback)
        assert poll_id
        assert poll_id
        assert poll_id

        result = poller.stop_polling(poll_id)

        assert result is True
        assert not poller.is_running
        assert poll_id not in poller._poll_tasks

    @pytest.mark.asyncio
    async def test_stop_polling_not_found(self, poller: ModbusPoller) -> None:
        """Stopping non-existent poll returns False."""
        result = poller.stop_polling("nonexistent:0")
        assert result is False

    @pytest.mark.asyncio
    async def test_polling_value_change_callback(
        self, modbus_client_mock: MagicMock
    ) -> None:
        """Callback fires when value changes."""
        poller = ModbusPoller(modbus_client_mock)
        callback = MagicMock()

        # First read returns [100]
        modbus_client_mock.read_holding_registers = AsyncMock(return_value=[100])

        config = PollConfig(
            register_address=100,
            register_type="holding_register",
            count=1,
            interval=0.05,
            debounce_count=1,
        )

        poll_id = poller.start_polling(config, callback)
        assert poll_id

        # Wait for first poll
        await asyncio.sleep(0.1)

        # Change value
        modbus_client_mock.read_holding_registers = AsyncMock(return_value=[200])

        # Wait for change detection
        await asyncio.sleep(0.15)

        # Callback should have been called with new value
        assert callback.call_count >= 1
        callback.assert_called_with(100, [200])

        # Cleanup
        poller.stop_all()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_polling_debounce(self, modbus_client_mock: MagicMock) -> None:
        """Debouncing prevents spurious callbacks."""
        poller = ModbusPoller(modbus_client_mock)
        callback = MagicMock()

        # Initial value
        modbus_client_mock.read_holding_registers = AsyncMock(return_value=[100])

        config = PollConfig(
            register_address=100,
            register_type="holding_register",
            count=1,
            interval=0.05,
            debounce_count=3,  # Require 3 consecutive changes
        )

        poll_id = poller.start_polling(config, callback)
        assert poll_id

        # Wait for first poll
        await asyncio.sleep(0.1)

        # Change value (1st change)
        modbus_client_mock.read_holding_registers = AsyncMock(return_value=[200])
        await asyncio.sleep(0.1)

        # Callback should not fire yet (only 1 change)
        assert callback.call_count == 0

        # Wait for 2 more polls (2nd and 3rd changes)
        await asyncio.sleep(0.15)

        # Callback should fire now (3 consecutive changes)
        assert callback.call_count >= 1

        # Cleanup
        poller.stop_all()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_stop_all(self, modbus_client_mock: MagicMock) -> None:
        """Stop all cancels all polling tasks."""
        poller = ModbusPoller(modbus_client_mock)

        config1 = PollConfig(register_address=100, register_type="holding_register", interval=0.1)
        config2 = PollConfig(register_address=200, register_type="coil", interval=0.1)

        poller.start_polling(config1, MagicMock())
        poller.start_polling(config2, MagicMock())

        assert len(poller._poll_tasks) == 2
        assert poller.is_running

        poller.stop_all()

        assert len(poller._poll_tasks) == 0
        assert not poller.is_running

    @pytest.mark.asyncio
    async def test_polling_read_error(self, modbus_client_mock: MagicMock) -> None:
        """Polling continues after read errors."""
        poller = ModbusPoller(modbus_client_mock)
        callback = MagicMock()

        # First read fails
        modbus_client_mock.read_holding_registers = AsyncMock(return_value=None)

        config = PollConfig(
            register_address=100,
            register_type="holding_register",
            interval=0.05,
        )

        poll_id = poller.start_polling(config, callback)
        assert poll_id

        # Wait for failed poll
        await asyncio.sleep(0.1)

        # Now return valid value
        modbus_client_mock.read_holding_registers = AsyncMock(return_value=[100])

        # Wait for successful poll
        await asyncio.sleep(0.1)

        # Polling should still be active
        assert poller.is_running

        # Cleanup
        poller.stop_all()
        await asyncio.sleep(0.05)


class TestPollConfig:
    """Test PollConfig."""

    def test_default_config(self) -> None:
        """Default poll config has sensible defaults."""
        config = PollConfig(
            register_address=100,
            register_type="holding_register",
        )

        assert config.register_address == 100
        assert config.register_type == "holding_register"
        assert config.count == 1
        assert config.interval == 1.0
        assert config.debounce_count == 1

    def test_custom_config(self) -> None:
        """Custom poll config values are set correctly."""
        config = PollConfig(
            register_address=200,
            register_type="coil",
            count=5,
            interval=2.0,
            debounce_count=3,
        )

        assert config.register_address == 200
        assert config.register_type == "coil"
        assert config.count == 5
        assert config.interval == 2.0
        assert config.debounce_count == 3
