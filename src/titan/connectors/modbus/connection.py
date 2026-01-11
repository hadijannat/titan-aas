"""Modbus Connection Manager with reconnection logic.

Manages Modbus client lifecycle with exponential backoff reconnection.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from titan.config import settings
from titan.connectors.modbus.client import ModbusClient, ModbusConfig
from titan.observability.metrics import set_modbus_connection_state

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Connection State
# -----------------------------------------------------------------------------


class ModbusConnectionState(str, Enum):
    """Connection state machine."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class ModbusMetrics:
    """Metrics for Modbus operations."""

    # Read/write metrics
    reads_total: int = 0
    writes_total: int = 0
    read_errors: int = 0
    write_errors: int = 0

    # Connection metrics
    connection_attempts: int = 0
    successful_connections: int = 0
    disconnections: int = 0
    current_state: str = "disconnected"

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            "reads_total": self.reads_total,
            "writes_total": self.writes_total,
            "read_errors": self.read_errors,
            "write_errors": self.write_errors,
            "connection_attempts": self.connection_attempts,
            "successful_connections": self.successful_connections,
            "disconnections": self.disconnections,
            "state": self.current_state,
        }


# -----------------------------------------------------------------------------
# Connection Manager
# -----------------------------------------------------------------------------


class ModbusConnectionManager:
    """Manages Modbus client lifecycle with exponential backoff reconnection.

    Features:
    - Automatic reconnection with exponential backoff
    - Connection state tracking
    - Thread-safe client access
    - Graceful shutdown
    - Health check support
    """

    def __init__(self, config: ModbusConfig):
        self.config = config
        self._client: ModbusClient | None = None
        self._state = ModbusConnectionState.DISCONNECTED
        self._lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._current_delay: float = config.reconnect_interval
        self._reconnect_attempts = 0
        self._shutdown_event = asyncio.Event()
        self.metrics = ModbusMetrics()

    @property
    def state(self) -> ModbusConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == ModbusConnectionState.CONNECTED

    async def connect(self) -> bool:
        """Establish connection to Modbus server.

        Returns:
            True if connection successful, False otherwise.
        """
        async with self._lock:
            if self._state == ModbusConnectionState.CONNECTED:
                return True

            self._state = ModbusConnectionState.CONNECTING
            self.metrics.current_state = self._state.value
            self.metrics.connection_attempts += 1
            set_modbus_connection_state(self.config.host, 1)  # connecting

            try:
                self._client = ModbusClient(self.config)
                if await self._client.connect():
                    self._state = ModbusConnectionState.CONNECTED
                    self.metrics.current_state = self._state.value
                    self.metrics.successful_connections += 1
                    self._reset_backoff()
                    set_modbus_connection_state(self.config.host, 2)  # connected

                    logger.info(
                        f"Connected to Modbus server at {self.config.mode}://"
                        f"{self.config.host}:{self.config.port}"
                    )
                    return True
                else:
                    self._state = ModbusConnectionState.DISCONNECTED
                    self.metrics.current_state = self._state.value
                    set_modbus_connection_state(self.config.host, 0)  # disconnected
                    logger.error(
                        f"Failed to connect to Modbus server: {self.config.host}:{self.config.port}"
                    )
                    return False

            except Exception as e:
                self._state = ModbusConnectionState.DISCONNECTED
                self.metrics.current_state = self._state.value
                set_modbus_connection_state(self.config.host, 0)  # disconnected
                logger.error(f"Failed to connect to Modbus server: {e}")
                return False

    async def disconnect(self) -> None:
        """Gracefully disconnect from server."""
        self._shutdown_event.set()

        # Cancel reconnect task if running
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.disconnect()
                except Exception as e:
                    logger.warning(f"Error disconnecting from Modbus: {e}")
                finally:
                    self._client = None

            self._state = ModbusConnectionState.DISCONNECTED
            self.metrics.current_state = self._state.value
            self.metrics.disconnections += 1
            set_modbus_connection_state(self.config.host, 0)  # disconnected

        logger.info("Disconnected from Modbus server")

    async def ensure_connected(self) -> ModbusClient:
        """Get connected client, reconnecting if necessary.

        Returns:
            Connected Modbus client.

        Raises:
            RuntimeError: If connection fails after max attempts.
        """
        if self._state == ModbusConnectionState.CONNECTED and self._client is not None:
            return self._client

        if self._state == ModbusConnectionState.FAILED:
            raise RuntimeError("Modbus connection failed after max reconnect attempts")

        # Try to connect
        if await self.connect():
            if self._client is not None:
                return self._client

        # Start reconnection in background
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        raise RuntimeError("Modbus not connected, reconnection in progress")

    async def _reconnect_loop(self) -> None:
        """Background task for reconnection with exponential backoff."""
        self._state = ModbusConnectionState.RECONNECTING
        self.metrics.current_state = self._state.value
        set_modbus_connection_state(self.config.host, 3)  # reconnecting

        # Get reconnection settings from config
        reconnect_delay_initial = self.config.reconnect_interval
        reconnect_delay_max = getattr(settings, "modbus_reconnect_delay_max", 60.0)
        reconnect_delay_multiplier = getattr(settings, "modbus_reconnect_delay_multiplier", 2.0)
        max_reconnect_attempts = getattr(settings, "modbus_max_reconnect_attempts", 10)

        self._current_delay = reconnect_delay_initial

        while not self._shutdown_event.is_set():
            try:
                if await self.connect():
                    return

                self._reconnect_attempts += 1
                if self._reconnect_attempts >= max_reconnect_attempts:
                    self._state = ModbusConnectionState.FAILED
                    self.metrics.current_state = self._state.value
                    set_modbus_connection_state(self.config.host, 4)  # failed
                    logger.error(f"Max reconnect attempts ({max_reconnect_attempts}) reached")
                    return

                # Exponential backoff
                delay = min(
                    self._current_delay * reconnect_delay_multiplier,
                    reconnect_delay_max,
                )
                self._current_delay = delay
                logger.warning(
                    f"Reconnect attempt {self._reconnect_attempts} failed, retrying in {delay:.1f}s"
                )

                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconnect loop: {e}")
                await asyncio.sleep(self._current_delay)

    def _reset_backoff(self) -> None:
        """Reset backoff state after successful connection."""
        self._current_delay = self.config.reconnect_interval
        self._reconnect_attempts = 0

    async def health_check(self) -> dict[str, Any]:
        """Return connection health status."""
        return {
            "connected": self.is_connected,
            "state": self._state.value,
            "host": self.config.host,
            "port": self.config.port,
            "mode": self.config.mode,
            "reconnect_attempts": self._reconnect_attempts,
            "metrics": self.metrics.to_dict(),
        }


# -----------------------------------------------------------------------------
# Factory Functions
# -----------------------------------------------------------------------------


def create_modbus_config_from_settings() -> ModbusConfig | None:
    """Create Modbus config from application settings.

    Returns:
        ModbusConfig if Modbus is enabled and configured, None otherwise.
    """
    if not settings.modbus_enabled or not settings.modbus_host:
        return None

    return ModbusConfig(
        host=settings.modbus_host,
        port=settings.modbus_port,
        mode=settings.modbus_mode,
        unit_id=settings.modbus_unit_id,
        timeout=settings.modbus_timeout,
        reconnect_interval=settings.modbus_reconnect_interval,
        serial_port=settings.modbus_serial_port,
        baudrate=settings.modbus_baudrate,
    )


# Module-level connection manager instance
_connection_manager: ModbusConnectionManager | None = None


async def get_modbus_connection_manager() -> ModbusConnectionManager | None:
    """Get or create Modbus connection manager.

    Returns:
        ModbusConnectionManager if configured, None otherwise.
    """
    global _connection_manager

    config = create_modbus_config_from_settings()
    if config is None:
        return None

    if _connection_manager is None:
        _connection_manager = ModbusConnectionManager(config)
        await _connection_manager.connect()

    return _connection_manager


async def close_modbus() -> None:
    """Close Modbus connection."""
    global _connection_manager

    if _connection_manager is not None:
        await _connection_manager.disconnect()
        _connection_manager = None
