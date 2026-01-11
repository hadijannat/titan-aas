"""OPC-UA Connection Manager with reconnection logic.

Manages OPC-UA client lifecycle with exponential backoff reconnection.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from titan.config import settings
from titan.connectors.opcua.client import OpcUaClient, OpcUaConfig, OpcUaSecurityMode
from titan.observability.metrics import set_opcua_connection_state

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Connection State
# -----------------------------------------------------------------------------


class OpcUaConnectionState(str, Enum):
    """Connection state machine."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class OpcUaMetrics:
    """Metrics for OPC-UA operations."""

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


class OpcUaConnectionManager:
    """Manages OPC-UA client lifecycle with exponential backoff reconnection.

    Features:
    - Automatic reconnection with exponential backoff
    - Connection state tracking
    - Thread-safe client access
    - Graceful shutdown
    - Health check support
    """

    def __init__(self, config: OpcUaConfig):
        self.config = config
        self._client: OpcUaClient | None = None
        self._state = OpcUaConnectionState.DISCONNECTED
        self._lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._current_delay: float = config.reconnect_interval
        self._reconnect_attempts = 0
        self._shutdown_event = asyncio.Event()
        self.metrics = OpcUaMetrics()

    @property
    def state(self) -> OpcUaConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == OpcUaConnectionState.CONNECTED

    async def connect(self) -> bool:
        """Establish connection to OPC-UA server.

        Returns:
            True if connection successful, False otherwise.
        """
        async with self._lock:
            if self._state == OpcUaConnectionState.CONNECTED:
                return True

            self._state = OpcUaConnectionState.CONNECTING
            self.metrics.current_state = self._state.value
            self.metrics.connection_attempts += 1
            set_opcua_connection_state(self.config.endpoint_url, 1)  # connecting

            try:
                self._client = OpcUaClient(self.config)
                if await self._client.connect():
                    self._state = OpcUaConnectionState.CONNECTED
                    self.metrics.current_state = self._state.value
                    self.metrics.successful_connections += 1
                    self._reset_backoff()
                    set_opcua_connection_state(self.config.endpoint_url, 2)  # connected

                    logger.info(f"Connected to OPC-UA server at {self.config.endpoint_url}")
                    return True
                else:
                    self._state = OpcUaConnectionState.DISCONNECTED
                    self.metrics.current_state = self._state.value
                    set_opcua_connection_state(self.config.endpoint_url, 0)  # disconnected
                    logger.error(f"Failed to connect to OPC-UA server: {self.config.endpoint_url}")
                    return False

            except Exception as e:
                self._state = OpcUaConnectionState.DISCONNECTED
                self.metrics.current_state = self._state.value
                set_opcua_connection_state(self.config.endpoint_url, 0)  # disconnected
                logger.error(f"Failed to connect to OPC-UA server: {e}")
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
                    logger.warning(f"Error disconnecting from OPC-UA: {e}")
                finally:
                    self._client = None

            self._state = OpcUaConnectionState.DISCONNECTED
            self.metrics.current_state = self._state.value
            self.metrics.disconnections += 1
            set_opcua_connection_state(self.config.endpoint_url, 0)  # disconnected

        logger.info("Disconnected from OPC-UA server")

    async def ensure_connected(self) -> OpcUaClient:
        """Get connected client, reconnecting if necessary.

        Returns:
            Connected OPC-UA client.

        Raises:
            RuntimeError: If connection fails after max attempts.
        """
        if self._state == OpcUaConnectionState.CONNECTED and self._client is not None:
            return self._client

        if self._state == OpcUaConnectionState.FAILED:
            raise RuntimeError("OPC-UA connection failed after max reconnect attempts")

        # Try to connect
        if await self.connect():
            if self._client is not None:
                return self._client

        # Start reconnection in background
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        raise RuntimeError("OPC-UA not connected, reconnection in progress")

    async def _reconnect_loop(self) -> None:
        """Background task for reconnection with exponential backoff."""
        self._state = OpcUaConnectionState.RECONNECTING
        self.metrics.current_state = self._state.value
        set_opcua_connection_state(self.config.endpoint_url, 3)  # reconnecting

        # Get reconnection settings from config (using MQTT pattern)
        reconnect_delay_initial = getattr(
            settings, "opcua_reconnect_delay_initial", self.config.reconnect_interval
        )
        reconnect_delay_max = getattr(settings, "opcua_reconnect_delay_max", 60.0)
        reconnect_delay_multiplier = getattr(settings, "opcua_reconnect_delay_multiplier", 2.0)
        max_reconnect_attempts = getattr(settings, "opcua_max_reconnect_attempts", 10)

        self._current_delay = reconnect_delay_initial

        while not self._shutdown_event.is_set():
            try:
                if await self.connect():
                    return

                self._reconnect_attempts += 1
                if self._reconnect_attempts >= max_reconnect_attempts:
                    self._state = OpcUaConnectionState.FAILED
                    self.metrics.current_state = self._state.value
                    set_opcua_connection_state(self.config.endpoint_url, 4)  # failed
                    logger.error(f"Max reconnect attempts ({max_reconnect_attempts}) reached")
                    return

                # Exponential backoff
                delay = min(
                    self._current_delay * reconnect_delay_multiplier,
                    reconnect_delay_max,
                )
                self._current_delay = delay
                logger.warning(
                    f"Reconnect attempt {self._reconnect_attempts} failed, "
                    f"retrying in {delay:.1f}s"
                )

                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconnect loop: {e}")
                await asyncio.sleep(self._current_delay)

    def _reset_backoff(self) -> None:
        """Reset backoff state after successful connection."""
        reconnect_delay_initial = getattr(
            settings, "opcua_reconnect_delay_initial", self.config.reconnect_interval
        )
        self._current_delay = reconnect_delay_initial
        self._reconnect_attempts = 0

    async def health_check(self) -> dict[str, Any]:
        """Return connection health status."""
        return {
            "connected": self.is_connected,
            "state": self._state.value,
            "endpoint": self.config.endpoint_url,
            "reconnect_attempts": self._reconnect_attempts,
            "metrics": self.metrics.to_dict(),
        }


# -----------------------------------------------------------------------------
# Factory Functions
# -----------------------------------------------------------------------------


def create_opcua_config_from_settings() -> OpcUaConfig | None:
    """Create OPC-UA config from application settings.

    Returns:
        OpcUaConfig if OPC-UA is enabled and configured, None otherwise.
    """
    if not settings.opcua_enabled or not settings.opcua_endpoint:
        return None

    # Map security mode string to enum
    security_mode_map = {
        "None": OpcUaSecurityMode.NONE,
        "Sign": OpcUaSecurityMode.SIGN,
        "SignAndEncrypt": OpcUaSecurityMode.SIGN_AND_ENCRYPT,
    }
    security_mode = security_mode_map.get(
        settings.opcua_security_mode, OpcUaSecurityMode.NONE
    )

    return OpcUaConfig(
        endpoint_url=settings.opcua_endpoint,
        security_mode=security_mode,
        username=settings.opcua_username,
        password=settings.opcua_password,
        timeout=float(settings.opcua_timeout),
        reconnect_interval=settings.opcua_reconnect_delay_initial,
    )


# Module-level connection manager instance
_connection_manager: OpcUaConnectionManager | None = None


async def get_opcua_connection_manager() -> OpcUaConnectionManager | None:
    """Get or create OPC-UA connection manager.

    Returns:
        OpcUaConnectionManager if configured, None otherwise.
    """
    global _connection_manager

    config = create_opcua_config_from_settings()
    if config is None:
        return None

    if _connection_manager is None:
        _connection_manager = OpcUaConnectionManager(config)
        await _connection_manager.connect()

    return _connection_manager


async def close_opcua() -> None:
    """Close OPC-UA connection."""
    global _connection_manager

    if _connection_manager is not None:
        await _connection_manager.disconnect()
        _connection_manager = None
