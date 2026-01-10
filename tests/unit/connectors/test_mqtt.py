"""Tests for MQTT event publishing."""

from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from titan.connectors.mqtt import MqttPublisher
from titan.events import AasEvent, EventType, SubmodelEvent


class TestMqttPublisher:
    """Test MqttPublisher."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create mock MQTT client."""
        client = MagicMock()
        client.publish = AsyncMock()
        return client

    @pytest.fixture
    def publisher(self, mock_client: MagicMock) -> MqttPublisher:
        """Create MqttPublisher with mock client."""
        return MqttPublisher(mock_client)

    @pytest.fixture
    def aas_event(self) -> AasEvent:
        """Create sample AAS event."""
        return AasEvent(
            event_type=EventType.CREATED,
            identifier="urn:example:aas:1",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOjE",
            etag="abc123",
        )

    @pytest.fixture
    def submodel_event(self) -> SubmodelEvent:
        """Create sample Submodel event."""
        return SubmodelEvent(
            event_type=EventType.UPDATED,
            identifier="urn:example:submodel:1",
            identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ",
            etag="def456",
        )

    @pytest.mark.asyncio
    async def test_publish_aas_event(
        self,
        publisher: MqttPublisher,
        mock_client: MagicMock,
        aas_event: AasEvent,
    ) -> None:
        """Publish AAS event to MQTT."""
        await publisher.publish_aas_event(aas_event)

        mock_client.publish.assert_called_once()
        call_args = mock_client.publish.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert topic == "titan/aas/dXJuOmV4YW1wbGU6YWFzOjE/created"
        parsed = orjson.loads(payload)
        # EventType.CREATED.value is "created"
        assert parsed["eventType"] == "created"
        assert parsed["entity"] == "aas"

    @pytest.mark.asyncio
    async def test_publish_submodel_event(
        self,
        publisher: MqttPublisher,
        mock_client: MagicMock,
        submodel_event: SubmodelEvent,
    ) -> None:
        """Publish Submodel event to MQTT."""
        await publisher.publish_submodel_event(submodel_event)

        mock_client.publish.assert_called_once()
        call_args = mock_client.publish.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert topic == "titan/submodel/dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ/updated"
        parsed = orjson.loads(payload)
        # EventType.UPDATED.value is "updated"
        assert parsed["eventType"] == "updated"
        assert parsed["entity"] == "submodel"

    def test_build_topic_aas_created(self, publisher: MqttPublisher) -> None:
        """Build topic for AAS created event."""
        topic = publisher._build_topic("aas", "abc123", EventType.CREATED)
        assert topic == "titan/aas/abc123/created"

    def test_build_topic_submodel_updated(self, publisher: MqttPublisher) -> None:
        """Build topic for Submodel updated event."""
        topic = publisher._build_topic("submodel", "def456", EventType.UPDATED)
        assert topic == "titan/submodel/def456/updated"

    def test_build_topic_deleted(self, publisher: MqttPublisher) -> None:
        """Build topic for deleted event."""
        topic = publisher._build_topic("aas", "xyz789", EventType.DELETED)
        assert topic == "titan/aas/xyz789/deleted"

    def test_serialize_event_includes_required_fields(
        self, publisher: MqttPublisher, aas_event: AasEvent
    ) -> None:
        """Serialized event includes all required fields."""
        data = publisher._serialize_event(aas_event)
        parsed = orjson.loads(data)

        assert "eventId" in parsed
        assert "eventType" in parsed
        assert "entity" in parsed
        assert "identifier" in parsed
        assert "identifierB64" in parsed
        assert "timestamp" in parsed

    def test_serialize_event_includes_etag_when_present(
        self, publisher: MqttPublisher, aas_event: AasEvent
    ) -> None:
        """Serialized event includes etag when present."""
        data = publisher._serialize_event(aas_event)
        parsed = orjson.loads(data)
        assert parsed["etag"] == "abc123"

    def test_serialize_event_excludes_etag_when_none(
        self, publisher: MqttPublisher
    ) -> None:
        """Serialized event excludes etag when None."""
        event = AasEvent(
            event_type=EventType.DELETED,
            identifier="urn:example:aas:1",
            identifier_b64="abc123",
            etag=None,
        )
        data = publisher._serialize_event(event)
        parsed = orjson.loads(data)
        assert "etag" not in parsed
