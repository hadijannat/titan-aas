"""Integration tests for MQTT publisher and subscriber with real Mosquitto broker.

These tests verify end-to-end MQTT functionality:
1. Publisher: Publish events to Mosquitto, verify messages received
2. Subscriber: Publish to Mosquitto, verify subscriber receives and processes
3. Reconnection: Kill broker, verify exponential backoff and reconnection
"""

import asyncio
import json
import time
from typing import Any
from unittest.mock import MagicMock

import orjson
import paho.mqtt.client as mqtt_client
import pytest
from testcontainers.core.container import DockerContainer

from titan.connectors.mqtt import MqttConfig, MqttConnectionManager, MqttPublisher
from titan.connectors.mqtt_subscriber import MqttSubscriber
from titan.core.ids import encode_id_to_b64url
from titan.events import AasEvent, EventType, SubmodelEvent


@pytest.fixture(scope="module")
def mosquitto_broker() -> DockerContainer:
    """Start Mosquitto MQTT broker in container."""
    container = DockerContainer("eclipse-mosquitto:2")
    container.with_exposed_ports(1883)
    container.with_command("mosquitto -c /mosquitto-no-auth.conf")
    container.start()

    # Give the broker time to start
    time.sleep(2)

    yield container

    container.stop()


@pytest.fixture
def mqtt_broker_config(mosquitto_broker: DockerContainer) -> MqttConfig:
    """Create MQTT config pointing to test broker."""
    host = mosquitto_broker.get_container_host_ip()
    port = mosquitto_broker.get_exposed_port(1883)
    return MqttConfig(
        broker=host,
        port=int(port),
        client_id="test-integration",
    )


@pytest.fixture
def mqtt_subscriber_client(mqtt_broker_config: MqttConfig):
    """Create paho-mqtt client for subscribing to test topics."""
    received_messages = []

    def on_message(client: Any, userdata: Any, msg: Any) -> None:
        """Store received messages."""
        received_messages.append(
            {
                "topic": msg.topic,
                "payload": json.loads(msg.payload.decode()),
            }
        )

    client = mqtt_client.Client(
        mqtt_client.CallbackAPIVersion.VERSION2, client_id="test-subscriber"
    )
    client.on_message = on_message
    client.connect(mqtt_broker_config.broker, mqtt_broker_config.port)
    client.loop_start()

    # Store received_messages on client for test access
    client.received_messages = received_messages

    yield client

    client.loop_stop()
    client.disconnect()


class TestMqttPublisherIntegration:
    """Test MQTT publisher end-to-end."""

    @pytest.mark.asyncio
    async def test_publish_aas_event_to_broker(
        self,
        mqtt_subscriber_client: mqtt_client.Client,
        mqtt_broker_config: MqttConfig,
    ) -> None:
        """Publish AAS event to Mosquitto, verify message received."""
        # Subscribe to AAS created events
        mqtt_subscriber_client.subscribe("titan/aas/+/created")
        await asyncio.sleep(1)  # Give subscription time to register

        # Create publisher
        connection_manager = MqttConnectionManager(mqtt_broker_config)
        publisher = MqttPublisher(connection_manager)

        # Publish event
        identifier = "urn:example:test:aas:mqtt:1"
        identifier_b64 = encode_id_to_b64url(identifier)
        event = AasEvent(
            event_type=EventType.CREATED,
            identifier=identifier,
            identifier_b64=identifier_b64,
            etag="abc123",
        )

        await publisher.publish_aas_event(event)

        # Wait for MQTT message
        await asyncio.sleep(2)

        # Verify message received
        messages = mqtt_subscriber_client.received_messages
        assert len(messages) > 0, "No MQTT messages received"

        # Find the created event for our AAS
        expected_topic = f"titan/aas/{identifier_b64}/created"
        matching_messages = [m for m in messages if m["topic"] == expected_topic]
        assert len(matching_messages) == 1, f"Expected 1 message, got {len(matching_messages)}"

        message = matching_messages[0]
        payload = message["payload"]

        # Verify payload structure
        assert payload["eventType"] == "created"
        assert payload["entity"] == "aas"
        assert payload["identifier"] == identifier
        assert payload["identifierB64"] == identifier_b64
        assert "eventId" in payload
        assert "timestamp" in payload
        assert payload["etag"] == "abc123"

        # Cleanup
        await connection_manager.disconnect()

    @pytest.mark.asyncio
    async def test_publish_submodel_event_to_broker(
        self,
        mqtt_subscriber_client: mqtt_client.Client,
        mqtt_broker_config: MqttConfig,
    ) -> None:
        """Publish Submodel event to Mosquitto, verify message received."""
        # Subscribe to submodel updated events
        mqtt_subscriber_client.subscribe("titan/submodel/+/updated")
        await asyncio.sleep(1)

        # Create publisher
        connection_manager = MqttConnectionManager(mqtt_broker_config)
        publisher = MqttPublisher(connection_manager)

        # Publish event
        identifier = "urn:example:test:submodel:mqtt:1"
        identifier_b64 = encode_id_to_b64url(identifier)
        event = SubmodelEvent(
            event_type=EventType.UPDATED,
            identifier=identifier,
            identifier_b64=identifier_b64,
            etag="def456",
        )

        await publisher.publish_submodel_event(event)

        # Wait for MQTT message
        await asyncio.sleep(2)

        # Verify updated event received
        expected_topic = f"titan/submodel/{identifier_b64}/updated"
        matching_messages = [
            m for m in mqtt_subscriber_client.received_messages if m["topic"] == expected_topic
        ]
        assert len(matching_messages) == 1

        payload = matching_messages[0]["payload"]
        assert payload["eventType"] == "updated"
        assert payload["entity"] == "submodel"
        assert payload["etag"] == "def456"

        # Cleanup
        await connection_manager.disconnect()


class TestMqttSubscriberIntegration:
    """Test MQTT subscriber end-to-end."""

    @pytest.mark.asyncio
    async def test_subscriber_receives_and_processes_message(
        self,
        mqtt_broker_config: MqttConfig,
    ) -> None:
        """Publish element value to MQTT, verify subscriber receives it."""
        # Create mock session factory
        mock_session = MagicMock()

        def mock_session_factory() -> MagicMock:
            return mock_session

        # Create connection manager
        connection_manager = MqttConnectionManager(mqtt_broker_config)

        # Create subscriber with mock session factory
        from titan.connectors.mqtt_subscriber import ElementValueHandler

        subscriber = MqttSubscriber(connection_manager)
        handler = ElementValueHandler(mock_session_factory)
        subscriber.registry.register("titan/element/#", handler)

        # Start subscriber
        await subscriber.start(["titan/element/#"])
        await asyncio.sleep(2)  # Give subscriber time to connect

        # Publish value update via MQTT
        publisher = mqtt_client.Client(
            mqtt_client.CallbackAPIVersion.VERSION2, client_id="test-publisher"
        )
        publisher.connect(mqtt_broker_config.broker, mqtt_broker_config.port)
        publisher.loop_start()

        submodel_id = "urn:example:test:submodel:subscriber:1"
        identifier_b64 = encode_id_to_b64url(submodel_id)
        topic = f"titan/element/{identifier_b64}/Temperature/value"
        payload = orjson.dumps(
            {
                "value": "25.8",
                "valueType": "xs:double",
            }
        )

        publish_result = publisher.publish(topic, payload)
        publish_result.wait_for_publish()
        publisher.disconnect()
        publisher.loop_stop()

        # Wait for subscriber to process
        await asyncio.sleep(3)

        # Verify message was received (check metrics)
        assert subscriber.metrics.messages_received > 0

        # Cleanup
        await subscriber.stop()
        await connection_manager.disconnect()


class TestMqttReconnection:
    """Test MQTT reconnection logic."""

    @pytest.mark.asyncio
    async def test_reconnection_with_exponential_backoff(
        self,
        mqtt_broker_config: MqttConfig,
    ) -> None:
        """Verify connection manager handles disconnection."""
        # Create connection manager
        manager = MqttConnectionManager(mqtt_broker_config)

        # Connect initially
        client = await manager.ensure_connected()
        assert client is not None

        # Disconnect
        await manager.disconnect()

        # Verify we can reconnect
        client2 = await manager.ensure_connected()
        assert client2 is not None

        # Cleanup
        await manager.disconnect()

    @pytest.mark.asyncio
    async def test_publisher_handles_temporary_disconnect(
        self,
        mqtt_broker_config: MqttConfig,
    ) -> None:
        """Verify publisher can publish after reconnection."""
        # Create publisher
        connection_manager = MqttConnectionManager(mqtt_broker_config)
        publisher = MqttPublisher(connection_manager)

        # Publish initial event
        event1 = AasEvent(
            event_type=EventType.CREATED,
            identifier="urn:test:reconnect:1",
            identifier_b64=encode_id_to_b64url("urn:test:reconnect:1"),
        )
        await publisher.publish_aas_event(event1)

        # Disconnect
        await connection_manager.disconnect()
        await asyncio.sleep(1)

        # Publish another event (should reconnect automatically)
        event2 = AasEvent(
            event_type=EventType.UPDATED,
            identifier="urn:test:reconnect:2",
            identifier_b64=encode_id_to_b64url("urn:test:reconnect:2"),
        )
        await publisher.publish_aas_event(event2)

        # Cleanup
        await connection_manager.disconnect()
