"""Tests for event publisher helper functions."""

import pytest

from titan.events import (
    EventType,
    InMemoryEventBus,
    publish_aas_deleted,
    publish_aas_event,
    publish_concept_description_event,
    publish_submodel_deleted,
    publish_submodel_element_event,
    publish_submodel_event,
)
from titan.events.schemas import (
    AasEvent,
    AnyEvent,
    ConceptDescriptionEvent,
    SubmodelElementEvent,
    SubmodelEvent,
)


@pytest.fixture
async def event_bus() -> InMemoryEventBus:
    """Create an in-memory event bus for testing."""
    bus = InMemoryEventBus()
    await bus.start()
    yield bus
    await bus.stop()


class TestPublishAasEvent:
    """Tests for publish_aas_event function."""

    @pytest.mark.asyncio
    async def test_publishes_created_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_aas_event publishes CREATED event correctly."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:1",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOjE",
            doc_bytes=b'{"id": "urn:example:aas:1"}',
            etag="abc123",
        )

        # Wait for event to be processed
        await event_bus.drain()

        assert isinstance(result, AasEvent)
        assert result.event_type == EventType.CREATED
        assert result.identifier == "urn:example:aas:1"
        assert result.identifier_b64 == "dXJuOmV4YW1wbGU6YWFzOjE"
        assert result.doc_bytes == b'{"id": "urn:example:aas:1"}'
        assert result.etag == "abc123"
        assert result.entity == "aas"
        assert len(events_received) == 1
        assert events_received[0] == result

    @pytest.mark.asyncio
    async def test_publishes_updated_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_aas_event publishes UPDATED event correctly."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.UPDATED,
            identifier="urn:example:aas:1",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOjE",
            doc_bytes=b'{"id": "urn:example:aas:1", "version": 2}',
            etag="def456",
        )

        await event_bus.drain()

        assert result.event_type == EventType.UPDATED
        assert result.etag == "def456"
        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_event_has_unique_id(self, event_bus: InMemoryEventBus) -> None:
        """Each published event has a unique event_id."""
        event1 = await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:1",
            identifier_b64="b64_1",
            doc_bytes=b"{}",
            etag="etag1",
        )
        event2 = await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:2",
            identifier_b64="b64_2",
            doc_bytes=b"{}",
            etag="etag2",
        )

        assert event1.event_id != event2.event_id


class TestPublishAasDeleted:
    """Tests for publish_aas_deleted function."""

    @pytest.mark.asyncio
    async def test_publishes_deleted_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_aas_deleted publishes DELETED event correctly."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_aas_deleted(
            event_bus=event_bus,
            identifier="urn:example:aas:1",
            identifier_b64="dXJuOmV4YW1wbGU6YWFzOjE",
        )

        await event_bus.drain()

        assert isinstance(result, AasEvent)
        assert result.event_type == EventType.DELETED
        assert result.identifier == "urn:example:aas:1"
        assert result.doc_bytes is None
        assert result.etag is None
        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_deleted_event_has_entity_aas(self, event_bus: InMemoryEventBus) -> None:
        """Deleted event has entity type 'aas'."""
        result = await publish_aas_deleted(
            event_bus=event_bus,
            identifier="urn:example:aas:1",
            identifier_b64="b64",
        )

        assert result.entity == "aas"


class TestPublishSubmodelEvent:
    """Tests for publish_submodel_event function."""

    @pytest.mark.asyncio
    async def test_publishes_created_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_submodel_event publishes CREATED event correctly."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_submodel_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:submodel:1",
            identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ",
            doc_bytes=b'{"id": "urn:example:submodel:1"}',
            etag="xyz789",
            semantic_id="urn:example:semantic:tech",
        )

        await event_bus.drain()

        assert isinstance(result, SubmodelEvent)
        assert result.event_type == EventType.CREATED
        assert result.identifier == "urn:example:submodel:1"
        assert result.semantic_id == "urn:example:semantic:tech"
        assert result.entity == "submodel"
        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_publishes_without_semantic_id(self, event_bus: InMemoryEventBus) -> None:
        """publish_submodel_event works without semantic_id."""
        result = await publish_submodel_event(
            event_bus=event_bus,
            event_type=EventType.UPDATED,
            identifier="urn:example:submodel:1",
            identifier_b64="b64",
            doc_bytes=b"{}",
            etag="etag",
        )

        assert result.semantic_id is None


class TestPublishSubmodelDeleted:
    """Tests for publish_submodel_deleted function."""

    @pytest.mark.asyncio
    async def test_publishes_deleted_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_submodel_deleted publishes DELETED event correctly."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_submodel_deleted(
            event_bus=event_bus,
            identifier="urn:example:submodel:1",
            identifier_b64="dXJuOmV4YW1wbGU6c3VibW9kZWw6MQ",
            semantic_id="urn:example:semantic:1",
        )

        await event_bus.drain()

        assert isinstance(result, SubmodelEvent)
        assert result.event_type == EventType.DELETED
        assert result.doc_bytes is None
        assert result.etag is None
        assert result.semantic_id == "urn:example:semantic:1"
        assert len(events_received) == 1


class TestPublishSubmodelElementEvent:
    """Tests for publish_submodel_element_event function."""

    @pytest.mark.asyncio
    async def test_publishes_created_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_submodel_element_event publishes CREATED event correctly."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_submodel_element_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            submodel_identifier="urn:example:submodel:1",
            submodel_identifier_b64="b64_submodel",
            id_short_path="Property1",
            value_bytes=b'{"value": "test"}',
        )

        await event_bus.drain()

        assert isinstance(result, SubmodelElementEvent)
        assert result.event_type == EventType.CREATED
        assert result.submodel_identifier == "urn:example:submodel:1"
        assert result.id_short_path == "Property1"
        assert result.entity == "element"
        assert result.value_bytes == b'{"value": "test"}'
        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_publishes_nested_element_path(self, event_bus: InMemoryEventBus) -> None:
        """publish_submodel_element_event supports nested paths."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_submodel_element_event(
            event_bus=event_bus,
            event_type=EventType.UPDATED,
            submodel_identifier="urn:example:submodel:1",
            submodel_identifier_b64="b64",
            id_short_path="Collection1.NestedProperty",
            value_bytes=b"{}",
        )

        await event_bus.drain()

        assert result.id_short_path == "Collection1.NestedProperty"
        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_publishes_deleted_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_submodel_element_event can publish DELETED events."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_submodel_element_event(
            event_bus=event_bus,
            event_type=EventType.DELETED,
            submodel_identifier="urn:example:submodel:1",
            submodel_identifier_b64="b64",
            id_short_path="Property1",
        )

        await event_bus.drain()

        assert result.event_type == EventType.DELETED
        assert result.value_bytes is None
        assert len(events_received) == 1


class TestPublishConceptDescriptionEvent:
    """Tests for publish_concept_description_event function."""

    @pytest.mark.asyncio
    async def test_publishes_created_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_concept_description_event publishes CREATED event correctly."""
        events_received: list[AnyEvent] = []

        async def handler(e: AnyEvent) -> None:
            events_received.append(e)

        await event_bus.subscribe(handler)

        result = await publish_concept_description_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:cd:1",
            identifier_b64="dXJuOmV4YW1wbGU6Y2Q6MQ",
            doc_bytes=b'{"id": "urn:example:cd:1"}',
            etag="cd_etag",
        )

        await event_bus.drain()

        assert isinstance(result, ConceptDescriptionEvent)
        assert result.event_type == EventType.CREATED
        assert result.identifier == "urn:example:cd:1"
        assert result.entity == "concept_description"
        assert len(events_received) == 1

    @pytest.mark.asyncio
    async def test_publishes_deleted_event(self, event_bus: InMemoryEventBus) -> None:
        """publish_concept_description_event can publish DELETED events."""
        result = await publish_concept_description_event(
            event_bus=event_bus,
            event_type=EventType.DELETED,
            identifier="urn:example:cd:1",
            identifier_b64="b64",
        )

        assert result.event_type == EventType.DELETED
        assert result.doc_bytes is None
        assert result.etag is None


class TestEventTimestamp:
    """Tests for event timestamp behavior."""

    @pytest.mark.asyncio
    async def test_events_have_timestamps(self, event_bus: InMemoryEventBus) -> None:
        """All published events have timestamps."""
        aas_event = await publish_aas_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:aas:1",
            identifier_b64="b64",
            doc_bytes=b"{}",
            etag="etag",
        )
        submodel_event = await publish_submodel_event(
            event_bus=event_bus,
            event_type=EventType.CREATED,
            identifier="urn:example:submodel:1",
            identifier_b64="b64",
            doc_bytes=b"{}",
            etag="etag",
        )

        assert aas_event.timestamp is not None
        assert submodel_event.timestamp is not None
