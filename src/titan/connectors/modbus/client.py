"""Modbus TCP/RTU client for reading and writing Modbus registers.

Supports both Modbus TCP (Ethernet) and Modbus RTU (Serial) protocols.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

logger = logging.getLogger(__name__)


@dataclass
class ModbusConfig:
    """Configuration for Modbus connection."""

    host: str
    port: int = 502
    mode: str = "tcp"  # tcp or rtu
    unit_id: int = 1  # Modbus slave ID
    timeout: float = 3.0
    reconnect_interval: float = 5.0
    # RTU-specific fields
    serial_port: str | None = None
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"  # N, E, O
    stopbits: int = 1


@dataclass
class ModbusValue:
    """Value read from or written to a Modbus register."""

    register_address: int
    value: int | float | bool
    register_type: str  # coil, discrete_input, holding_register, input_register
    timestamp: datetime


class ModbusClient:
    """Async Modbus TCP/RTU client.

    Provides methods for reading and writing Modbus registers with proper
    error handling and connection management.
    """

    def __init__(self, config: ModbusConfig):
        """Initialize Modbus client.

        Args:
            config: Modbus connection configuration
        """
        self.config = config
        self._client: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to Modbus server."""
        return self._connected

    async def connect(self) -> bool:
        """Connect to Modbus server (TCP or RTU).

        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            logger.warning("Already connected to Modbus server")
            return True

        try:
            if self.config.mode == "tcp":
                from pymodbus.client import AsyncModbusTcpClient

                self._client = AsyncModbusTcpClient(
                    host=self.config.host,
                    port=self.config.port,
                    timeout=self.config.timeout,
                )
            elif self.config.mode == "rtu":
                from pymodbus.client import AsyncModbusSerialClient

                if not self.config.serial_port:
                    logger.error("Serial port not configured for RTU mode")
                    return False

                self._client = AsyncModbusSerialClient(
                    port=self.config.serial_port,
                    baudrate=self.config.baudrate,
                    bytesize=self.config.bytesize,
                    parity=self.config.parity,
                    stopbits=self.config.stopbits,
                    timeout=self.config.timeout,
                )
            else:
                logger.error(f"Invalid Modbus mode: {self.config.mode}")
                return False

            # Connect with timeout
            await asyncio.wait_for(
                self._client.connect(),
                timeout=self.config.timeout,
            )

            self._connected = True
            logger.info(
                f"Connected to Modbus server: {self.config.mode}://{self.config.host}:{self.config.port}"
            )
            return True

        except TimeoutError:
            logger.error(
                f"Connection timeout to Modbus server {self.config.host}:{self.config.port}"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Modbus server: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Modbus server."""
        if not self._connected or not self._client:
            return

        try:
            self._client.close()
            self._connected = False
            logger.info("Disconnected from Modbus server")
        except Exception as e:
            logger.error(f"Error disconnecting from Modbus server: {e}")

    async def read_coils(self, address: int, count: int = 1) -> list[bool] | None:
        """Read coil values (function code 01).

        Args:
            address: Starting coil address (0-based)
            count: Number of coils to read

        Returns:
            List of boolean values, or None on error
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return None

        try:
            response = await self._client.read_coils(
                address=address,
                count=count,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error reading coils at address {address}: {response}")
                return None

            return cast(list[bool], response.bits[:count])

        except Exception as e:
            logger.error(f"Failed to read coils at address {address}: {e}")
            return None

    async def read_discrete_inputs(self, address: int, count: int = 1) -> list[bool] | None:
        """Read discrete input values (function code 02).

        Args:
            address: Starting input address (0-based)
            count: Number of inputs to read

        Returns:
            List of boolean values, or None on error
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return None

        try:
            response = await self._client.read_discrete_inputs(
                address=address,
                count=count,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error reading discrete inputs at address {address}: {response}")
                return None

            return cast(list[bool], response.bits[:count])

        except Exception as e:
            logger.error(f"Failed to read discrete inputs at address {address}: {e}")
            return None

    async def read_holding_registers(self, address: int, count: int = 1) -> list[int] | None:
        """Read holding register values (function code 03).

        Args:
            address: Starting register address (0-based)
            count: Number of registers to read

        Returns:
            List of integer values (16-bit unsigned), or None on error
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return None

        try:
            response = await self._client.read_holding_registers(
                address=address,
                count=count,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error reading holding registers at address {address}: {response}")
                return None

            return cast(list[int], response.registers)

        except Exception as e:
            logger.error(f"Failed to read holding registers at address {address}: {e}")
            return None

    async def read_input_registers(self, address: int, count: int = 1) -> list[int] | None:
        """Read input register values (function code 04).

        Args:
            address: Starting register address (0-based)
            count: Number of registers to read

        Returns:
            List of integer values (16-bit unsigned), or None on error
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return None

        try:
            response = await self._client.read_input_registers(
                address=address,
                count=count,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error reading input registers at address {address}: {response}")
                return None

            return cast(list[int], response.registers)

        except Exception as e:
            logger.error(f"Failed to read input registers at address {address}: {e}")
            return None

    async def write_coil(self, address: int, value: bool) -> bool:
        """Write single coil value (function code 05).

        Args:
            address: Coil address (0-based)
            value: Boolean value to write

        Returns:
            True if successful, False otherwise
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return False

        try:
            response = await self._client.write_coil(
                address=address,
                value=value,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error writing coil at address {address}: {response}")
                return False

            logger.debug(f"Wrote coil {address}: value={value}")
            return True

        except Exception as e:
            logger.error(f"Failed to write coil at address {address}: {e}")
            return False

    async def write_register(self, address: int, value: int) -> bool:
        """Write single holding register value (function code 06).

        Args:
            address: Register address (0-based)
            value: Integer value to write (16-bit unsigned, 0-65535)

        Returns:
            True if successful, False otherwise
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return False

        try:
            # Validate value range
            if not 0 <= value <= 65535:
                logger.error(f"Invalid register value {value}: must be 0-65535")
                return False

            response = await self._client.write_register(
                address=address,
                value=value,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error writing register at address {address}: {response}")
                return False

            logger.debug(f"Wrote register {address}: value={value}")
            return True

        except Exception as e:
            logger.error(f"Failed to write register at address {address}: {e}")
            return False

    async def write_multiple_coils(self, address: int, values: list[bool]) -> bool:
        """Write multiple coil values (function code 15).

        Args:
            address: Starting coil address (0-based)
            values: List of boolean values to write

        Returns:
            True if successful, False otherwise
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return False

        try:
            response = await self._client.write_coils(
                address=address,
                values=values,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error writing multiple coils at address {address}: {response}")
                return False

            logger.debug(f"Wrote {len(values)} coils starting at {address}")
            return True

        except Exception as e:
            logger.error(f"Failed to write multiple coils at address {address}: {e}")
            return False

    async def write_multiple_registers(self, address: int, values: list[int]) -> bool:
        """Write multiple holding register values (function code 16).

        Args:
            address: Starting register address (0-based)
            values: List of integer values to write (16-bit unsigned, 0-65535)

        Returns:
            True if successful, False otherwise
        """
        if not self._connected or not self._client:
            logger.warning("Not connected to Modbus server")
            return False

        try:
            # Validate all values
            for i, value in enumerate(values):
                if not 0 <= value <= 65535:
                    logger.error(
                        f"Invalid register value at index {i}: {value} (must be 0-65535)"
                    )
                    return False

            response = await self._client.write_registers(
                address=address,
                values=values,
                device_id=self.config.unit_id,
            )

            if response.isError():
                logger.error(f"Error writing multiple registers at address {address}: {response}")
                return False

            logger.debug(f"Wrote {len(values)} registers starting at {address}")
            return True

        except Exception as e:
            logger.error(f"Failed to write multiple registers at address {address}: {e}")
            return False
