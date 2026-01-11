"""MQTT Subscriber for receiving external commands.

Subscribes to configured MQTT topics and routes messages to handlers.

Topic patterns:
- titan/element/{submodel_id_b64}/{path}/value - Update element value
- titan/+/+/command/# - Generic command topics for extensions
"""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from titan.config import settings
from titan.connectors.mqtt import MqttConfig, MqttConnectionManager
from titan.core.element_operations import (
    ElementNotFoundError,
    InvalidPathError,
    update_element_value,
)
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url
from titan.core.model import Submodel
from titan.observability.metrics import record_mqtt_message_received, record_mqtt_processing_error

if TYPE_CHECKING:
    from aiomqtt import Message

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Message Handler Interface
# -----------------------------------------------------------------------------


@dataclass
class MqttMessage:
    """Parsed MQTT message."""

    topic: str
    payload: bytes
    qos: int
    retain: bool

    @property
    def payload_str(self) -> str:
        """Get payload as string."""
        return self.payload.decode("utf-8")

    @property
    def payload_json(self) -> Any:
        """Parse payload as JSON."""
        return orjson.loads(self.payload)


class MessageHandler(ABC):
    """Abstract base class for MQTT message handlers."""

    @abstractmethod
    def matches(self, topic: str) -> bool:
        """Check if this handler matches the topic."""
        ...

    @abstractmethod
    async def handle(self, message: MqttMessage) -> None:
        """Handle the message."""
        ...


# -----------------------------------------------------------------------------
# Handler Registry
# -----------------------------------------------------------------------------


@dataclass
class HandlerRegistration:
    """Registration for a message handler."""

    pattern: str
    handler: MessageHandler
    _regex: re.Pattern[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Compile topic pattern to regex."""
        # Convert MQTT pattern to regex
        # + matches single level, # matches multiple levels
        regex_pattern = self.pattern.replace("+", "[^/]+").replace("#", ".*")
        self._regex = re.compile(f"^{regex_pattern}$")

    def matches(self, topic: str) -> bool:
        """Check if topic matches this registration's pattern."""
        return bool(self._regex.match(topic))


class HandlerRegistry:
    """Registry for MQTT message handlers."""

    def __init__(self) -> None:
        self._handlers: list[HandlerRegistration] = []

    def register(self, pattern: str, handler: MessageHandler) -> None:
        """Register a handler for a topic pattern."""
        self._handlers.append(HandlerRegistration(pattern, handler))
        logger.debug(f"Registered handler for pattern: {pattern}")

    def get_handlers(self, topic: str) -> list[MessageHandler]:
        """Get all handlers that match a topic."""
        return [reg.handler for reg in self._handlers if reg.matches(topic)]

    def register_callback(
        self,
        pattern: str,
        callback: Callable[[MqttMessage], Coroutine[Any, Any, None]],
    ) -> None:
        """Register a callback function as a handler."""
        handler = CallbackHandler(callback)
        self.register(pattern, handler)


class CallbackHandler(MessageHandler):
    """Handler that wraps a callback function."""

    def __init__(self, callback: Callable[[MqttMessage], Coroutine[Any, Any, None]]) -> None:
        self._callback = callback

    def matches(self, topic: str) -> bool:
        """Always returns True - matching is done by registry."""
        return True

    async def handle(self, message: MqttMessage) -> None:
        """Handle by calling the callback."""
        await self._callback(message)


# -----------------------------------------------------------------------------
# Subscriber Metrics
# -----------------------------------------------------------------------------


@dataclass
class SubscriberMetrics:
    """Metrics for MQTT subscriber."""

    messages_received: int = 0
    messages_processed: int = 0
    processing_errors: int = 0
    no_handler_found: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dictionary."""
        return {
            "messages_received": self.messages_received,
            "messages_processed": self.messages_processed,
            "processing_errors": self.processing_errors,
            "no_handler_found": self.no_handler_found,
        }


# -----------------------------------------------------------------------------
# MQTT Subscriber
# -----------------------------------------------------------------------------


class MqttSubscriber:
    """Subscribes to MQTT topics and dispatches messages to handlers."""

    def __init__(
        self,
        connection_manager: MqttConnectionManager,
        registry: HandlerRegistry | None = None,
    ) -> None:
        self.connection_manager = connection_manager
        self.registry = registry or HandlerRegistry()
        self.metrics = SubscriberMetrics()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._subscribed_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        """Check if subscriber is running."""
        return self._running

    async def start(self, topics: list[str] | None = None) -> None:
        """Start subscribing to topics.

        Args:
            topics: List of topic patterns to subscribe to.
                   If None, uses topics from config.
        """
        if self._running:
            logger.warning("Subscriber already running")
            return

        if topics is None:
            config = self.connection_manager.config
            topics = config.subscribe_topics

        if not topics:
            logger.warning("No topics to subscribe to")
            return

        self._running = True
        self._subscribed_event.clear()
        self._task = asyncio.create_task(self._subscribe_loop(topics))
        logger.info(f"Started MQTT subscriber for topics: {topics}")

    async def stop(self) -> None:
        """Stop the subscriber."""
        self._running = False
        self._subscribed_event.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped MQTT subscriber")

    async def wait_until_ready(self, timeout: float | None = None) -> bool:
        """Wait until the subscriber has completed topic subscriptions."""
        try:
            await asyncio.wait_for(self._subscribed_event.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def _subscribe_loop(self, topics: list[str]) -> None:
        """Main subscription loop."""
        while self._running:
            try:
                self._subscribed_event.clear()
                client = await self.connection_manager.ensure_connected()

                # Subscribe to all topics
                for topic in topics:
                    await client.subscribe(topic)
                    logger.debug(f"Subscribed to: {topic}")
                self._subscribed_event.set()

                # Process messages - use manual iteration for clean shutdown
                message_iter = client.messages.__aiter__()
                while self._running:
                    try:
                        message = await asyncio.wait_for(message_iter.__anext__(), timeout=1.0)
                        await self._handle_message(message)
                    except TimeoutError:
                        continue
                    except StopAsyncIteration:
                        break

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Error in subscription loop: {e}")
                if self._running:
                    await asyncio.sleep(1)

    async def _handle_message(self, message: Message) -> None:
        """Handle an incoming MQTT message."""
        self.metrics.messages_received += 1
        record_mqtt_message_received(topic_pattern="titan/#")

        topic = str(message.topic)
        mqtt_msg = MqttMessage(
            topic=topic,
            payload=message.payload if isinstance(message.payload, bytes) else b"",
            qos=message.qos,
            retain=message.retain,
        )

        handlers = self.registry.get_handlers(topic)
        if not handlers:
            self.metrics.no_handler_found += 1
            logger.debug(f"No handler found for topic: {topic}")
            return

        for handler in handlers:
            try:
                await handler.handle(mqtt_msg)
                self.metrics.messages_processed += 1
            except Exception as e:
                self.metrics.processing_errors += 1
                record_mqtt_processing_error(topic_pattern="titan/#")
                logger.error(f"Error handling message on {topic}: {e}")


# -----------------------------------------------------------------------------
# Titan-Specific Handlers
# -----------------------------------------------------------------------------


class ElementValueHandler(MessageHandler):
    """Handler for element value updates via MQTT.

    Topic format: titan/element/{submodel_id_b64}/{path}/value
    Payload: JSON value to set
    """

    # Regex to extract submodel_id_b64 and path from topic
    TOPIC_PATTERN = re.compile(r"^titan/element/([^/]+)/(.+)/value$")

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory

    def matches(self, topic: str) -> bool:
        """Check if topic matches element value pattern."""
        return bool(self.TOPIC_PATTERN.match(topic))

    async def handle(self, message: MqttMessage) -> None:
        """Handle element value update."""
        match = self.TOPIC_PATTERN.match(message.topic)
        if not match:
            logger.warning(f"Invalid element value topic: {message.topic}")
            return

        submodel_id_b64 = match.group(1)
        id_short_path = match.group(2)

        try:
            value = message.payload_json
        except Exception as e:
            logger.error(f"Invalid JSON payload: {e}")
            return

        await self._update_element_value(submodel_id_b64, id_short_path, value)

    async def _update_element_value(
        self,
        submodel_id_b64: str,
        id_short_path: str,
        value: Any,
    ) -> None:
        """Update element value in database."""
        from titan.persistence.repositories import SubmodelRepository

        # Decode identifier from base64url
        try:
            identifier = decode_id_from_b64url(submodel_id_b64)
        except InvalidBase64Url:
            logger.warning(f"Invalid base64url identifier: {submodel_id_b64}")
            return

        async with self._session_factory() as session:
            repo = SubmodelRepository(session)

            # Get current submodel
            result = await repo.get_bytes(submodel_id_b64)
            if result is None:
                logger.warning(f"Submodel not found: {submodel_id_b64}")
                return

            doc_bytes, _etag = result
            doc = orjson.loads(doc_bytes)

            # Update element value
            try:
                updated_doc = update_element_value(doc, id_short_path, value)
            except ElementNotFoundError:
                logger.warning(f"Element not found: {id_short_path} in {submodel_id_b64}")
                return
            except InvalidPathError as e:
                logger.warning(f"Invalid path: {e}")
                return

            # Validate and save
            try:
                submodel = Submodel.model_validate(updated_doc)
                update_result = await repo.update(identifier, submodel)
                if update_result is None:
                    logger.warning(f"Submodel not found for update: {identifier}")
                    return
                await session.commit()
                logger.info(f"Updated element via MQTT: {submodel_id_b64}/{id_short_path}")
            except Exception as e:
                logger.error(f"Failed to save element update: {e}")
                await session.rollback()


class CommandHandler(MessageHandler):
    """Handler for generic command messages.

    Topic format: titan/{entity}/{id}/command/{action}
    Payload: Command-specific JSON
    """

    TOPIC_PATTERN = re.compile(r"^titan/([^/]+)/([^/]+)/command/(.+)$")

    def __init__(self) -> None:
        self._command_handlers: dict[str, Callable[[str, str, Any], Coroutine[Any, Any, None]]] = {}

    def register_command(
        self,
        action: str,
        handler: Callable[[str, str, Any], Coroutine[Any, Any, None]],
    ) -> None:
        """Register a handler for a specific command action.

        Args:
            action: The command action (e.g., "refresh", "sync")
            handler: Async function(entity, id, payload) -> None
        """
        self._command_handlers[action] = handler

    def matches(self, topic: str) -> bool:
        """Check if topic matches command pattern."""
        return bool(self.TOPIC_PATTERN.match(topic))

    async def handle(self, message: MqttMessage) -> None:
        """Handle command message."""
        match = self.TOPIC_PATTERN.match(message.topic)
        if not match:
            return

        entity = match.group(1)
        entity_id = match.group(2)
        action = match.group(3)

        handler = self._command_handlers.get(action)
        if not handler:
            logger.debug(f"No handler for command action: {action}")
            return

        try:
            payload = message.payload_json if message.payload else {}
        except Exception:
            payload = {}

        try:
            await handler(entity, entity_id, payload)
        except Exception as e:
            logger.error(f"Error executing command {action}: {e}")


# -----------------------------------------------------------------------------
# Factory Functions
# -----------------------------------------------------------------------------


def create_subscriber(
    session_factory: Callable[[], AsyncSession],
) -> MqttSubscriber | None:
    """Create MQTT subscriber with standard handlers.

    Returns None if MQTT is not configured or subscription is disabled.
    """
    config = MqttConfig.from_settings()
    if config is None:
        return None

    if not config.subscribe_enabled:
        logger.debug("MQTT subscription is disabled")
        return None

    connection_manager = MqttConnectionManager(config)
    registry = HandlerRegistry()

    # Register element value handler
    element_handler = ElementValueHandler(session_factory)
    registry.register("titan/element/+/+/value", element_handler)
    # Also handle nested paths
    registry.register("titan/element/+/#", element_handler)

    # Register command handler (extensible)
    command_handler = CommandHandler()
    registry.register("titan/+/+/command/#", command_handler)

    return MqttSubscriber(connection_manager, registry)


# Module-level subscriber instance
_subscriber: MqttSubscriber | None = None


async def get_mqtt_subscriber(
    session_factory: Callable[[], AsyncSession] | None = None,
) -> MqttSubscriber | None:
    """Get or create the MQTT subscriber singleton.

    Args:
        session_factory: Factory function to create database sessions.
                        Required on first call when subscription is enabled.

    Returns:
        MqttSubscriber instance, or None if not configured.
    """
    global _subscriber

    if _subscriber is not None:
        return _subscriber

    if not settings.mqtt_subscribe_enabled:
        return None

    if session_factory is None:
        logger.warning("Session factory required for MQTT subscriber")
        return None

    _subscriber = create_subscriber(session_factory)
    return _subscriber


async def close_mqtt_subscriber() -> None:
    """Stop and close the MQTT subscriber."""
    global _subscriber

    if _subscriber is not None:
        await _subscriber.stop()
        await _subscriber.connection_manager.disconnect()
        _subscriber = None
