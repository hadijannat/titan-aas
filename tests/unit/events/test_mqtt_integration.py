"""Tests for MQTT event integration.

Tests the wiring between event publishers, event bus, and MQTT handlers.
"""

from typing import Any

import pytest

from titan.connectors.mqtt import MqttConfig, MqttEventHandler, MqttMetrics, MqttPublisher
from titan.events import (
    EventType,
    InMemoryEventBus,
    publish_aas_deleted,
    publish_aas_event,
    publish_submodel_event,
)
from titan.events.schemas import AasEvent, AnyEvent, SubmodelEvent


class MockMqttClient:
    """Mock MQTT client for testing."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(
        self, topic: str, payload: bytes, qos: int = 0, retain: bool = False
    ) -> None:
        self.published.append((topic, payload))


class StubConnectionManager:
    """Minimal connection manager for publisher tests."""

    def __init__(self, client: Any, config: MqttConfig | None = None) -> None:
        self.config = config or MqttConfig(broker="test-broker")
        self.metrics = MqttMetrics()
        self._client = client

    async def ensure_connected(self) -> Any:
        return self._client


@pytest.fixture
async def event_bus() -> InMemoryEventBus:
    """Create and start an in-memory event bus."""
    bus = InMemoryEventBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
def mock_mqtt_client() -> MockMqttClient:
    """Create a mock MQTT client for testing."""
    return MockMqttClient()


@pytest.fixture
def mqtt_publisher(mock_mqtt_client: MockMqttClient) -> MqttPublisher:
    """Create an MQTT publisher with mock client."""
    return MqttPublisher(StubConnectionManager(mock_mqtt_client))


@pytest.fixture
def mqtt_handler(mqtt_publisher: MqttPublisher) -> MqttEventHandler:
    """Create an MQTT event handler."""
    return MqttEventHandler(mqtt_publisher)


class TestMqttEventBusIntegration:
    """Tests for event bus to MQTT handler integration."""

    @pytest.mark.asyncio
    async def test_aas_event_published_to_mqtt(
        self,
        event_bus: InMemoryEventBus,
        mqtt_handler: MqttEventHandler,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """AAS events published to bus are sent to MQTT broker."""

        # Wire handler to event bus
        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await mqtt_handler.handle_aas_event(event)

        await event_bus.subscribe(broadcast_handler)

        # Publish event
        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:test",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOnRlc3Q",
            doc_bytes=b'{"id": "test"}',
            etag="etag123",
        )

        # Wait for event to be processed
        await event_bus.drain()

        # Verify MQTT received the event
        assert len(mock_mqtt_client.published) == 1
        topic, payload = mock_mqtt_client.published[0]
        assert topic == "titan/aas/dXJuOmV4YW1wbGU6YWFzOnRlc3Q/created"
        assert b"urn:example:aas:test" in payload

    @pytest.mark.asyncio
    async def test_submodel_event_published_to_mqtt(
        self,
        event_bus: InMemoryEventBus,
        mqtt_handler: MqttEventHandler,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """Submodel events published to bus are sent to MQTT broker."""

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, SubmodelEvent):
                await mqtt_handler.handle_submodel_event(event)

        await event_bus.subscribe(broadcast_handler)

        await publish_submodel_event(
            event_bus=event_bus,
            event_type=EventType.UPDATED,
            identifier="urn:example:submodel:test",
            identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6dGVzdA",
            doc_bytes=b'{"id": "test"}',
            etag="etag456",
            semantic_id="urn:example:semantic:1",
        )

        await event_bus.drain()

        assert len(mock_mqtt_client.published) == 1
        topic, payload = mock_mqtt_client.published[0]
        assert topic == "titan/submodel/dXJuOmV4YW1wbGU6c3VibW9kZWw6dGVzdA/updated"
        assert b"urn:example:submodel:test" in payload

    @pytest.mark.asyncio
    async def test_deleted_event_published_to_mqtt(
        self,
        event_bus: InMemoryEventBus,
        mqtt_handler: MqttEventHandler,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """Deleted events are published to MQTT."""

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await mqtt_handler.handle_aas_event(event)

        await event_bus.subscribe(broadcast_handler)

        await publish_aas_deleted(
            event_bus=event_bus,
            identifier="urn:example:aas:deleted",
            identifier_b64="b64deleted",
        )

        await event_bus.drain()

        assert len(mock_mqtt_client.published) == 1
        topic, payload = mock_mqtt_client.published[0]
        assert topic == "titan/aas/b64deleted/deleted"
        assert b"deleted" in payload

    @pytest.mark.asyncio
    async def test_multiple_events_all_published(
        self,
        event_bus: InMemoryEventBus,
        mqtt_handler: MqttEventHandler,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """Multiple events are all published to MQTT."""

        async def broadcast_handler(event: AnyEvent) -> None:
            if isinstance(event, AasEvent):
                await mqtt_handler.handle_aas_event(event)
            elif isinstance(event, SubmodelEvent):
                await mqtt_handler.handle_submodel_event(event)

        await event_bus.subscribe(broadcast_handler)

        # Publish multiple events
        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:aas:1",
            identifier_b64="aas1",
            doc_bytes=b"{}",
            etag="etag1",
        )

        await publish_submodel_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:sm:1",
            identifier_b64="sm1",
            doc_bytes=b"{}",
            etag="etag2",
        )

        await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.UPDATED,
            identifier="urn:aas:1",
            identifier_b64="aas1",
            doc_bytes=b"{}",
            etag="etag3",
        )

        await event_bus.drain()

        # All three events should be published
        assert len(mock_mqtt_client.published) == 3
        topics = [t for t, _ in mock_mqtt_client.published]
        assert "titan/aas/aas1/created" in topics
        assert "titan/submodel/sm1/created" in topics
        assert "titan/aas/aas1/updated" in topics


class TestMqttPublisher:
    """Tests for MQTT publisher."""

    @pytest.mark.asyncio
    async def test_topic_structure_aas_created(
        self,
        mqtt_publisher: MqttPublisher,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """AAS created events have correct topic structure."""
        event = AasEvent(
            event_type=EventType.CREATED,
            entity="aas",
            identifier="urn:example:aas:1",
            identifier_b64="encoded_id",
            doc_bytes=b"{}",
            etag="etag",
        )

        await mqtt_publisher.publish_aas_event(event)

        topic, _ = mock_mqtt_client.published[0]
        assert topic == "titan/aas/encoded_id/created"

    @pytest.mark.asyncio
    async def test_topic_structure_submodel_updated(
        self,
        mqtt_publisher: MqttPublisher,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """Submodel updated events have correct topic structure."""
        event = SubmodelEvent(
            event_type=EventType.UPDATED,
            entity="submodel",
            identifier="urn:example:sm:1",
            identifier_b64="sm_encoded",
            doc_bytes=b"{}",
            etag="etag",
        )

        await mqtt_publisher.publish_submodel_event(event)

        topic, _ = mock_mqtt_client.published[0]
        assert topic == "titan/submodel/sm_encoded/updated"

    @pytest.mark.asyncio
    async def test_payload_contains_event_data(
        self,
        mqtt_publisher: MqttPublisher,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """Payload contains all event data."""
        event = AasEvent(
            event_type=EventType.CREATED,
            entity="aas",
            identifier="urn:example:aas:payload",
            identifier_b64="payload_b64",
            doc_bytes=b"{}",
            etag="my_etag",
        )

        await mqtt_publisher.publish_aas_event(event)

        _, payload = mock_mqtt_client.published[0]
        assert b"eventId" in payload
        assert b"created" in payload  # lowercase in serialization
        assert b"urn:example:aas:payload" in payload
        assert b"payload_b64" in payload
        assert b"my_etag" in payload


class TestMqttEventHandler:
    """Tests for MQTT event handler."""

    @pytest.mark.asyncio
    async def test_handler_catches_publish_errors(
        self,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """Handler catches and logs errors without propagating."""

        class FailingClient:
            async def publish(
                self, topic: str, payload: bytes, qos: int = 0, retain: bool = False
            ) -> None:
                raise ConnectionError("MQTT connection lost")

        failing_publisher = MqttPublisher(StubConnectionManager(FailingClient()))
        handler = MqttEventHandler(failing_publisher)

        event = AasEvent(
            event_type=EventType.CREATED,
            entity="aas",
            identifier="urn:fail",
            identifier_b64="fail_b64",
            doc_bytes=b"{}",
            etag="etag",
        )

        # Should not raise - errors are caught
        await handler.handle_aas_event(event)

    @pytest.mark.asyncio
    async def test_handler_continues_after_error(
        self,
        mock_mqtt_client: MockMqttClient,
    ) -> None:
        """Handler continues processing after an error."""
        call_count = 0

        class FlakeyClient:
            async def publish(
                self, topic: str, payload: bytes, qos: int = 0, retain: bool = False
            ) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ConnectionError("Temporary failure")
                # Second call succeeds
                mock_mqtt_client.published.append((topic, payload))

        flakey_publisher = MqttPublisher(StubConnectionManager(FlakeyClient()))
        handler = MqttEventHandler(flakey_publisher)

        event1 = AasEvent(
            event_type=EventType.CREATED,
            entity="aas",
            identifier="urn:first",
            identifier_b64="first_b64",
            doc_bytes=b"{}",
            etag="etag1",
        )
        event2 = AasEvent(
            event_type=EventType.CREATED,
            entity="aas",
            identifier="urn:second",
            identifier_b64="second_b64",
            doc_bytes=b"{}",
            etag="etag2",
        )

        # First event fails silently
        await handler.handle_aas_event(event1)

        # Second event succeeds
        await handler.handle_aas_event(event2)

        # Only second event was published
        assert len(mock_mqtt_client.published) == 1
        topic, _ = mock_mqtt_client.published[0]
        assert "second_b64" in topic
