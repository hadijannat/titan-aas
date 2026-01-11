"""MQTT Publisher for AAS events.

Publishes AAS/Submodel events to MQTT broker for IoT integration.

Topic structure:
- titan/aas/{identifier}/created
- titan/aas/{identifier}/updated
- titan/aas/{identifier}/deleted
- titan/submodel/{identifier}/created
- titan/submodel/{identifier}/updated
- titan/submodel/{identifier}/deleted
- titan/element/{submodel_id}/{path}/value

The payload is the canonical JSON of the event.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import orjson

from titan.config import settings
from titan.events import AasEvent, EventType, SubmodelElementEvent, SubmodelEvent
from titan.observability.metrics import (
    record_mqtt_message_published,
    record_mqtt_publish_error,
    set_mqtt_connection_state,
)

if TYPE_CHECKING:
    from aiomqtt import Client

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------


@dataclass
class MqttConfig:
    """Configuration for MQTT connection."""

    broker: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    use_tls: bool = False
    client_id: str = ""

    # Reconnection
    reconnect_delay_initial: float = 1.0
    reconnect_delay_max: float = 60.0
    reconnect_delay_multiplier: float = 2.0
    max_reconnect_attempts: int = 10

    # Publishing defaults
    default_qos: int = 1
    retain_events: bool = False

    # Consumer settings
    subscribe_enabled: bool = False
    subscribe_topics: list[str] = field(default_factory=list)

    @classmethod
    def from_settings(cls) -> MqttConfig | None:
        """Create config from application settings."""
        if not settings.mqtt_broker:
            return None

        topics = []
        if settings.mqtt_subscribe_topics:
            topics = [t.strip() for t in settings.mqtt_subscribe_topics.split(",")]

        return cls(
            broker=settings.mqtt_broker,
            port=settings.mqtt_port,
            username=settings.mqtt_username,
            password=settings.mqtt_password,
            use_tls=settings.mqtt_use_tls,
            client_id=f"{settings.mqtt_client_id_prefix}-{settings.instance_id}",
            reconnect_delay_initial=settings.mqtt_reconnect_delay_initial,
            reconnect_delay_max=settings.mqtt_reconnect_delay_max,
            reconnect_delay_multiplier=settings.mqtt_reconnect_delay_multiplier,
            max_reconnect_attempts=settings.mqtt_max_reconnect_attempts,
            default_qos=settings.mqtt_default_qos,
            retain_events=settings.mqtt_retain_events,
            subscribe_enabled=settings.mqtt_subscribe_enabled,
            subscribe_topics=topics,
        )


@dataclass
class TopicConfig:
    """Per-topic MQTT configuration."""

    qos: int = 1  # 0=at most once, 1=at least once, 2=exactly once
    retain: bool = False


class TopicConfigRegistry:
    """Registry for topic-specific MQTT settings."""

    def __init__(self, default_qos: int = 1, default_retain: bool = False):
        self.default_qos = default_qos
        self.default_retain = default_retain
        self._configs: dict[str, TopicConfig] = {}

    def register(self, topic_pattern: str, config: TopicConfig) -> None:
        """Register configuration for a topic pattern."""
        self._configs[topic_pattern] = config

    def get_config(self, topic: str) -> TopicConfig:
        """Get configuration for a topic (with pattern matching)."""
        # Exact match first
        if topic in self._configs:
            return self._configs[topic]

        # Pattern matching (e.g., "titan/aas/+/created")
        for pattern, config in self._configs.items():
            if self._matches_pattern(topic, pattern):
                return config

        return TopicConfig(qos=self.default_qos, retain=self.default_retain)

    def _matches_pattern(self, topic: str, pattern: str) -> bool:
        """Match MQTT topic pattern with + and # wildcards."""
        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")

        if "#" in pattern_parts:
            # Multi-level wildcard
            idx = pattern_parts.index("#")
            return topic_parts[:idx] == pattern_parts[:idx]

        if len(topic_parts) != len(pattern_parts):
            return False

        for t, p in zip(topic_parts, pattern_parts, strict=False):
            if p != "+" and p != t:
                return False
        return True


# -----------------------------------------------------------------------------
# Connection Manager
# -----------------------------------------------------------------------------


class MqttConnectionState(str, Enum):
    """Connection state machine."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class MqttMetrics:
    """Metrics for MQTT operations."""

    # Publisher metrics
    messages_published: int = 0
    publish_errors: int = 0

    # Connection metrics
    connection_attempts: int = 0
    successful_connections: int = 0
    disconnections: int = 0
    current_state: str = "disconnected"

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            "messages_published": self.messages_published,
            "publish_errors": self.publish_errors,
            "connection_attempts": self.connection_attempts,
            "successful_connections": self.successful_connections,
            "disconnections": self.disconnections,
            "state": self.current_state,
        }


class MqttConnectionManager:
    """Manages MQTT client lifecycle with exponential backoff reconnection.

    Features:
    - Automatic reconnection with exponential backoff
    - Connection state tracking
    - Thread-safe client access
    - Graceful shutdown
    - Health check support
    """

    def __init__(self, config: MqttConfig):
        self.config = config
        self._client: Client | None = None
        self._state = MqttConnectionState.DISCONNECTED
        self._lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._current_delay = config.reconnect_delay_initial
        self._reconnect_attempts = 0
        self._shutdown_event = asyncio.Event()
        self.metrics = MqttMetrics()

    @property
    def state(self) -> MqttConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == MqttConnectionState.CONNECTED

    async def connect(self) -> bool:
        """Establish connection to MQTT broker.

        Returns:
            True if connection successful, False otherwise.
        """
        async with self._lock:
            if self._state == MqttConnectionState.CONNECTED:
                return True

            self._state = MqttConnectionState.CONNECTING
            self.metrics.current_state = self._state.value
            self.metrics.connection_attempts += 1

            try:
                from aiomqtt import Client

                self._client = Client(
                    hostname=self.config.broker,
                    port=self.config.port,
                    identifier=self.config.client_id,
                    username=self.config.username,
                    password=self.config.password,
                )
                await self._client.__aenter__()

                self._state = MqttConnectionState.CONNECTED
                self.metrics.current_state = self._state.value
                self.metrics.successful_connections += 1
                self._reset_backoff()
                set_mqtt_connection_state(self.config.broker, 2)  # connected

                logger.info(f"Connected to MQTT broker at {self.config.broker}:{self.config.port}")
                return True

            except Exception as e:
                self._state = MqttConnectionState.DISCONNECTED
                self.metrics.current_state = self._state.value
                logger.error(f"Failed to connect to MQTT broker: {e}")
                return False

    async def disconnect(self) -> None:
        """Gracefully disconnect from broker."""
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
                    await self._client.__aexit__(None, None, None)
                except Exception as e:
                    logger.warning(f"Error disconnecting from MQTT: {e}")
                finally:
                    self._client = None

            self._state = MqttConnectionState.DISCONNECTED
            self.metrics.current_state = self._state.value
            self.metrics.disconnections += 1
            set_mqtt_connection_state(self.config.broker, 0)

        logger.info("Disconnected from MQTT broker")

    async def ensure_connected(self) -> Client:
        """Get connected client, reconnecting if necessary.

        Returns:
            Connected MQTT client.

        Raises:
            RuntimeError: If connection fails after max attempts.
        """
        if self._state == MqttConnectionState.CONNECTED and self._client is not None:
            return self._client

        if self._state == MqttConnectionState.FAILED:
            raise RuntimeError("MQTT connection failed after max reconnect attempts")

        # Try to connect
        if await self.connect():
            if self._client is not None:
                return self._client

        # Start reconnection in background
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        raise RuntimeError("MQTT not connected, reconnection in progress")

    async def _reconnect_loop(self) -> None:
        """Background task for reconnection with exponential backoff."""
        self._state = MqttConnectionState.RECONNECTING
        self.metrics.current_state = self._state.value

        while not self._shutdown_event.is_set():
            try:
                if await self.connect():
                    return

                self._reconnect_attempts += 1
                if self._reconnect_attempts >= self.config.max_reconnect_attempts:
                    self._state = MqttConnectionState.FAILED
                    self.metrics.current_state = self._state.value
                    set_mqtt_connection_state(self.config.broker, 4)
                    logger.error(
                        f"Max reconnect attempts ({self.config.max_reconnect_attempts}) reached"
                    )
                    return

                # Exponential backoff
                delay = min(
                    self._current_delay * self.config.reconnect_delay_multiplier,
                    self.config.reconnect_delay_max,
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
        self._current_delay = self.config.reconnect_delay_initial
        self._reconnect_attempts = 0

    async def health_check(self) -> dict[str, Any]:
        """Return connection health status."""
        return {
            "connected": self.is_connected,
            "state": self._state.value,
            "broker": self.config.broker,
            "port": self.config.port,
            "reconnect_attempts": self._reconnect_attempts,
            "metrics": self.metrics.to_dict(),
        }


# -----------------------------------------------------------------------------
# Publisher
# -----------------------------------------------------------------------------


class MqttPublisher:
    """Publishes AAS events to MQTT broker with QoS and retain support."""

    TOPIC_PREFIX = "titan"

    def __init__(
        self,
        connection_manager: MqttConnectionManager,
        topic_config: TopicConfigRegistry | None = None,
    ):
        self.connection_manager = connection_manager
        self.topic_config = topic_config or TopicConfigRegistry(
            default_qos=connection_manager.config.default_qos,
            default_retain=connection_manager.config.retain_events,
        )

    async def publish_aas_event(
        self,
        event: AasEvent,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> None:
        """Publish an AAS event to MQTT."""
        topic = self._build_topic("aas", event.identifier_b64, event.event_type)
        await self._publish(topic, self._serialize_event(event), qos, retain)

    async def publish_submodel_event(
        self,
        event: SubmodelEvent,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> None:
        """Publish a Submodel event to MQTT."""
        topic = self._build_topic("submodel", event.identifier_b64, event.event_type)
        await self._publish(topic, self._serialize_event(event), qos, retain)

    async def publish_element_event(
        self,
        event: SubmodelElementEvent,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> None:
        """Publish a SubmodelElement event to MQTT."""
        topic = (
            f"{self.TOPIC_PREFIX}/element/{event.submodel_identifier_b64}/"
            f"{event.id_short_path}/{event.event_type.value.lower()}"
        )
        await self._publish(topic, self._serialize_element_event(event), qos, retain)

    async def _publish(
        self,
        topic: str,
        payload: bytes,
        qos: int | None = None,
        retain: bool | None = None,
    ) -> None:
        """Publish message with topic-specific or override configuration."""
        config = self.topic_config.get_config(topic)
        actual_qos = qos if qos is not None else config.qos
        actual_retain = retain if retain is not None else config.retain

        try:
            client = await self.connection_manager.ensure_connected()
            await client.publish(topic, payload, qos=actual_qos, retain=actual_retain)
            self.connection_manager.metrics.messages_published += 1
            record_mqtt_message_published(topic_prefix="titan")
            logger.debug(f"Published to {topic} (qos={actual_qos}, retain={actual_retain})")
        except Exception as e:
            self.connection_manager.metrics.publish_errors += 1
            record_mqtt_publish_error(topic_prefix="titan")
            logger.error(f"Failed to publish to {topic}: {e}")
            raise

    def _build_topic(self, entity: str, identifier_b64: str, event_type: EventType) -> str:
        """Build MQTT topic for event."""
        action = event_type.value.lower()
        return f"{self.TOPIC_PREFIX}/{entity}/{identifier_b64}/{action}"

    def _serialize_event(self, event: AasEvent | SubmodelEvent) -> bytes:
        """Serialize event to JSON bytes."""
        data: dict[str, Any] = {
            "eventId": event.event_id,
            "eventType": event.event_type.value,
            "entity": event.entity,
            "identifier": event.identifier,
            "identifierB64": event.identifier_b64,
            "timestamp": event.timestamp.isoformat(),
        }
        if event.etag:
            data["etag"] = event.etag
        return orjson.dumps(data)

    def _serialize_element_event(self, event: SubmodelElementEvent) -> bytes:
        """Serialize element event to JSON bytes."""
        data: dict[str, Any] = {
            "eventId": event.event_id,
            "eventType": event.event_type.value,
            "entity": event.entity,
            "submodelIdentifier": event.submodel_identifier,
            "submodelIdentifierB64": event.submodel_identifier_b64,
            "idShortPath": event.id_short_path,
            "timestamp": event.timestamp.isoformat(),
        }
        return orjson.dumps(data)


# -----------------------------------------------------------------------------
# Event Handler
# -----------------------------------------------------------------------------


class MqttEventHandler:
    """Event handler that publishes events to MQTT."""

    def __init__(self, publisher: MqttPublisher):
        self.publisher = publisher

    async def handle_aas_event(self, event: AasEvent) -> None:
        """Handle AAS event by publishing to MQTT."""
        try:
            await self.publisher.publish_aas_event(event)
        except Exception as e:
            logger.error(f"Failed to publish AAS event to MQTT: {e}")

    async def handle_submodel_event(self, event: SubmodelEvent) -> None:
        """Handle Submodel event by publishing to MQTT."""
        try:
            await self.publisher.publish_submodel_event(event)
        except Exception as e:
            logger.error(f"Failed to publish Submodel event to MQTT: {e}")

    async def handle_element_event(self, event: SubmodelElementEvent) -> None:
        """Handle SubmodelElement event by publishing to MQTT."""
        try:
            await self.publisher.publish_element_event(event)
        except Exception as e:
            logger.error(f"Failed to publish SubmodelElement event to MQTT: {e}")


# -----------------------------------------------------------------------------
# Module-level convenience functions
# -----------------------------------------------------------------------------

_connection_manager: MqttConnectionManager | None = None
_publisher: MqttPublisher | None = None


async def get_mqtt_connection_manager() -> MqttConnectionManager | None:
    """Get or create MQTT connection manager.

    Returns None if MQTT is not configured.
    """
    global _connection_manager

    config = MqttConfig.from_settings()
    if config is None:
        return None

    if _connection_manager is None:
        _connection_manager = MqttConnectionManager(config)
        await _connection_manager.connect()

    return _connection_manager


async def get_mqtt_publisher() -> MqttPublisher | None:
    """Get MQTT publisher instance.

    Returns None if MQTT is not configured or connection failed.
    """
    global _publisher

    manager = await get_mqtt_connection_manager()
    if manager is None:
        return None

    if _publisher is None:
        _publisher = MqttPublisher(manager)

    return _publisher


async def close_mqtt() -> None:
    """Close MQTT connection."""
    global _connection_manager, _publisher

    if _connection_manager is not None:
        await _connection_manager.disconnect()
        _connection_manager = None
        _publisher = None
