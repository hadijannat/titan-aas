"""MQTT Publisher for AAS events.

Publishes AAS/Submodel events to MQTT broker for IoT integration.

Topic structure:
- titan/aas/{identifier}/created
- titan/aas/{identifier}/updated
- titan/aas/{identifier}/deleted
- titan/submodel/{identifier}/created
- titan/submodel/{identifier}/updated
- titan/submodel/{identifier}/deleted

The payload is the canonical JSON of the event.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import orjson

from titan.config import settings
from titan.events import AasEvent, EventType, SubmodelEvent

if TYPE_CHECKING:
    from aiomqtt import Client

logger = logging.getLogger(__name__)

# Module-level MQTT client
_mqtt_client: "Client | None" = None
_mqtt_lock = asyncio.Lock()


class MqttPublisher:
    """Publishes AAS events to MQTT broker."""

    TOPIC_PREFIX = "titan"

    def __init__(self, client: "Client"):
        self.client = client

    async def publish_aas_event(self, event: AasEvent) -> None:
        """Publish an AAS event to MQTT."""
        topic = self._build_topic("aas", event.identifier_b64, event.event_type)
        payload = self._serialize_event(event)
        await self.client.publish(topic, payload, qos=1)
        logger.debug(f"Published AAS event to {topic}")

    async def publish_submodel_event(self, event: SubmodelEvent) -> None:
        """Publish a Submodel event to MQTT."""
        topic = self._build_topic("submodel", event.identifier_b64, event.event_type)
        payload = self._serialize_event(event)
        await self.client.publish(topic, payload, qos=1)
        logger.debug(f"Published Submodel event to {topic}")

    def _build_topic(self, entity: str, identifier_b64: str, event_type: EventType) -> str:
        """Build MQTT topic for event."""
        action = event_type.value.lower()
        return f"{self.TOPIC_PREFIX}/{entity}/{identifier_b64}/{action}"

    def _serialize_event(self, event: AasEvent | SubmodelEvent) -> bytes:
        """Serialize event to JSON bytes."""
        data = {
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


async def get_mqtt_client() -> "Client | None":
    """Get or create MQTT client.

    Returns None if MQTT is not configured.
    """
    global _mqtt_client

    if not settings.mqtt_broker:
        return None

    async with _mqtt_lock:
        if _mqtt_client is None:
            try:
                from aiomqtt import Client

                _mqtt_client = Client(
                    hostname=settings.mqtt_broker,
                    port=settings.mqtt_port,
                    identifier=f"titan-aas-{settings.instance_id}",
                )
                await _mqtt_client.__aenter__()
                logger.info(f"Connected to MQTT broker at {settings.mqtt_broker}")
            except Exception as e:
                logger.warning(f"Failed to connect to MQTT broker: {e}")
                return None

    return _mqtt_client


async def close_mqtt() -> None:
    """Close MQTT connection."""
    global _mqtt_client

    if _mqtt_client is not None:
        try:
            await _mqtt_client.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing MQTT connection: {e}")
        finally:
            _mqtt_client = None


async def get_mqtt_publisher() -> MqttPublisher | None:
    """Get MQTT publisher instance.

    Returns None if MQTT is not configured or connection failed.
    """
    client = await get_mqtt_client()
    if client is None:
        return None
    return MqttPublisher(client)


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
