"""Tests for GraphQL subscriptions and subscription manager.

Tests the SubscriptionManager, event filtering, and subscription lifecycle.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest

from titan.events.schemas import (
    AasEvent,
    ConceptDescriptionEvent,
    EventType,
    SubmodelEvent,
)
from titan.graphql.subscription_manager import (
    Subscription,
    SubscriptionFilter,
    SubscriptionManager,
    get_subscription_manager,
    set_subscription_manager,
)
from titan.graphql.subscriptions import (
    _deserialize_concept_description,
    _deserialize_shell,
    _deserialize_submodel,
)


class TestSubscriptionFilter:
    """Test SubscriptionFilter matching logic."""

    def test_matches_entity_type(self) -> None:
        """Filter matches on entity type."""
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.CREATED],
        )

        aas_event = AasEvent(
            event_type=EventType.CREATED,
            identifier="urn:test:shell:1",
            identifier_b64="dXJuOnRlc3Q6c2hlbGw6MQ",
            doc_bytes=b"{}",
        )
        submodel_event = SubmodelEvent(
            event_type=EventType.CREATED,
            identifier="urn:test:submodel:1",
            identifier_b64="dXJuOnRlc3Q6c3VibW9kZWw6MQ",
            doc_bytes=b"{}",
        )

        assert filter.matches(aas_event) is True
        assert filter.matches(submodel_event) is False

    def test_matches_event_type(self) -> None:
        """Filter matches on event type."""
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.UPDATED],
        )

        created_event = AasEvent(
            event_type=EventType.CREATED,
            identifier="urn:test:shell:1",
            identifier_b64="dXJuOnRlc3Q6c2hlbGw6MQ",
            doc_bytes=b"{}",
        )
        updated_event = AasEvent(
            event_type=EventType.UPDATED,
            identifier="urn:test:shell:1",
            identifier_b64="dXJuOnRlc3Q6c2hlbGw6MQ",
            doc_bytes=b"{}",
        )

        assert filter.matches(created_event) is False
        assert filter.matches(updated_event) is True

    def test_matches_multiple_event_types(self) -> None:
        """Filter matches multiple event types."""
        filter = SubscriptionFilter(
            entity_type="submodel",
            event_types=[EventType.CREATED, EventType.UPDATED],
        )

        created = SubmodelEvent(
            event_type=EventType.CREATED,
            identifier="urn:test:sm:1",
            identifier_b64="b64",
            doc_bytes=b"{}",
        )
        updated = SubmodelEvent(
            event_type=EventType.UPDATED,
            identifier="urn:test:sm:1",
            identifier_b64="b64",
            doc_bytes=b"{}",
        )
        deleted = SubmodelEvent(
            event_type=EventType.DELETED,
            identifier="urn:test:sm:1",
            identifier_b64="b64",
        )

        assert filter.matches(created) is True
        assert filter.matches(updated) is True
        assert filter.matches(deleted) is False

    def test_matches_entity_id_filter(self) -> None:
        """Filter matches on specific entity ID."""
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.UPDATED],
            entity_id="urn:test:shell:1",
        )

        matching = AasEvent(
            event_type=EventType.UPDATED,
            identifier="urn:test:shell:1",
            identifier_b64="b64",
            doc_bytes=b"{}",
        )
        non_matching = AasEvent(
            event_type=EventType.UPDATED,
            identifier="urn:test:shell:2",
            identifier_b64="b64",
            doc_bytes=b"{}",
        )

        assert filter.matches(matching) is True
        assert filter.matches(non_matching) is False

    def test_matches_no_entity_id_filter(self) -> None:
        """Filter without entity ID matches all IDs."""
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.UPDATED],
            entity_id=None,
        )

        event1 = AasEvent(
            event_type=EventType.UPDATED,
            identifier="urn:test:shell:1",
            identifier_b64="b64",
            doc_bytes=b"{}",
        )
        event2 = AasEvent(
            event_type=EventType.UPDATED,
            identifier="urn:test:shell:2",
            identifier_b64="b64",
            doc_bytes=b"{}",
        )

        assert filter.matches(event1) is True
        assert filter.matches(event2) is True


class TestSubscriptionManager:
    """Test SubscriptionManager."""

    @pytest.fixture
    def mock_event_bus(self) -> MagicMock:
        """Create mock event bus."""
        bus = MagicMock()
        bus.subscribe = AsyncMock()
        return bus

    @pytest.fixture
    def manager(self, mock_event_bus: MagicMock) -> SubscriptionManager:
        """Create subscription manager with mock bus."""
        return SubscriptionManager(event_bus=mock_event_bus)

    async def test_start_subscribes_to_event_bus(
        self, manager: SubscriptionManager, mock_event_bus: MagicMock
    ) -> None:
        """Start subscribes to event bus."""
        await manager.start()

        mock_event_bus.subscribe.assert_called_once()
        assert manager._started is True

    async def test_start_idempotent(
        self, manager: SubscriptionManager, mock_event_bus: MagicMock
    ) -> None:
        """Multiple starts only subscribe once."""
        await manager.start()
        await manager.start()
        await manager.start()

        mock_event_bus.subscribe.assert_called_once()

    async def test_start_without_event_bus(self) -> None:
        """Start without event bus logs warning."""
        manager = SubscriptionManager(event_bus=None)
        await manager.start()

        # Should not raise, just log warning
        assert manager._started is False

    async def test_stop_clears_subscriptions(self, manager: SubscriptionManager) -> None:
        """Stop clears all subscriptions."""
        await manager.start()

        # Register a subscription
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.CREATED],
        )
        await manager._register(filter)
        assert manager.subscription_count == 1

        await manager.stop()

        assert manager.subscription_count == 0
        assert manager._started is False

    async def test_subscription_count(self, manager: SubscriptionManager) -> None:
        """Subscription count tracks active subscriptions."""
        filter1 = SubscriptionFilter(entity_type="aas", event_types=[EventType.CREATED])
        filter2 = SubscriptionFilter(entity_type="submodel", event_types=[EventType.UPDATED])

        assert manager.subscription_count == 0

        sub1 = await manager._register(filter1)
        assert manager.subscription_count == 1

        sub2 = await manager._register(filter2)
        assert manager.subscription_count == 2

        await manager._unregister(sub1.id)
        assert manager.subscription_count == 1

        await manager._unregister(sub2.id)
        assert manager.subscription_count == 0

    async def test_event_broadcast_to_matching_subscriptions(
        self, manager: SubscriptionManager
    ) -> None:
        """Events are broadcast to matching subscriptions."""
        await manager.start()

        # Create two subscriptions with different filters
        aas_filter = SubscriptionFilter(entity_type="aas", event_types=[EventType.CREATED])
        submodel_filter = SubscriptionFilter(
            entity_type="submodel", event_types=[EventType.CREATED]
        )

        aas_sub = await manager._register(aas_filter)
        submodel_sub = await manager._register(submodel_filter)

        # Publish AAS event
        aas_event = AasEvent(
            event_type=EventType.CREATED,
            identifier="urn:test:shell:1",
            identifier_b64="b64",
            doc_bytes=b'{"id": "test"}',
        )
        await manager._handle_event(aas_event)

        # AAS subscription should receive it
        assert aas_sub.queue.qsize() == 1
        # Submodel subscription should not
        assert submodel_sub.queue.qsize() == 0

        received = aas_sub.queue.get_nowait()
        assert received.identifier == "urn:test:shell:1"

    async def test_queue_overflow_drops_oldest(self, manager: SubscriptionManager) -> None:
        """When queue is full, oldest event is dropped."""
        # Create manager with small queue
        manager = SubscriptionManager(max_queue_size=2)
        await manager.start()

        filter = SubscriptionFilter(entity_type="aas", event_types=[EventType.CREATED])
        sub = await manager._register(filter)

        # Fill the queue
        for i in range(3):
            event = AasEvent(
                event_type=EventType.CREATED,
                identifier=f"urn:test:shell:{i}",
                identifier_b64="b64",
                doc_bytes=b"{}",
            )
            await manager._handle_event(event)

        # Queue should have size 2 (third event pushed out first)
        assert sub.queue.qsize() == 2

        # First event should be the second one (index 1)
        event = sub.queue.get_nowait()
        assert event.identifier == "urn:test:shell:1"


class TestSubscriptionMethods:
    """Test public subscription methods."""

    @pytest.fixture
    def manager(self) -> SubscriptionManager:
        """Create manager with mock event bus."""
        bus = MagicMock()
        bus.subscribe = AsyncMock()
        return SubscriptionManager(event_bus=bus)

    async def test_subscribe_shell_created_receives_events(
        self, manager: SubscriptionManager
    ) -> None:
        """shell_created subscription receives creation events."""
        await manager.start()

        # Start subscription in background
        events_received: list[AasEvent] = []

        async def collect_events() -> None:
            async for event in manager.subscribe_shell_created():
                events_received.append(event)
                if len(events_received) >= 2:
                    break

        task = asyncio.create_task(collect_events())

        # Give task time to start
        await asyncio.sleep(0.01)

        # Publish events
        for i in range(2):
            event = AasEvent(
                event_type=EventType.CREATED,
                identifier=f"urn:test:shell:{i}",
                identifier_b64="b64",
                doc_bytes=b"{}",
            )
            await manager._handle_event(event)

        # Wait for task with timeout
        await asyncio.wait_for(task, timeout=1.0)

        assert len(events_received) == 2
        assert events_received[0].identifier == "urn:test:shell:0"
        assert events_received[1].identifier == "urn:test:shell:1"

    async def test_subscribe_shell_updated_filters_by_id(
        self, manager: SubscriptionManager
    ) -> None:
        """shell_updated with ID only receives matching events."""
        await manager.start()

        events_received: list[AasEvent] = []
        target_id = "urn:test:shell:1"

        async def collect_events() -> None:
            async for event in manager.subscribe_shell_updated(entity_id=target_id):
                events_received.append(event)
                break

        task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)

        # Publish event for different shell - should not match
        await manager._handle_event(
            AasEvent(
                event_type=EventType.UPDATED,
                identifier="urn:test:shell:0",
                identifier_b64="b64",
                doc_bytes=b"{}",
            )
        )

        # Publish event for target shell - should match
        await manager._handle_event(
            AasEvent(
                event_type=EventType.UPDATED,
                identifier=target_id,
                identifier_b64="b64",
                doc_bytes=b"{}",
            )
        )

        await asyncio.wait_for(task, timeout=1.0)

        assert len(events_received) == 1
        assert events_received[0].identifier == target_id

    async def test_subscribe_submodel_deleted(self, manager: SubscriptionManager) -> None:
        """submodel_deleted subscription receives deletion events."""
        await manager.start()

        events_received: list[SubmodelEvent] = []

        async def collect_events() -> None:
            async for event in manager.subscribe_submodel_deleted():
                events_received.append(event)
                break

        task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)

        # Publish delete event
        await manager._handle_event(
            SubmodelEvent(
                event_type=EventType.DELETED,
                identifier="urn:test:submodel:1",
                identifier_b64="b64",
            )
        )

        await asyncio.wait_for(task, timeout=1.0)

        assert len(events_received) == 1
        assert events_received[0].identifier == "urn:test:submodel:1"

    async def test_subscribe_concept_description_updated(
        self, manager: SubscriptionManager
    ) -> None:
        """concept_description_updated subscription receives events."""
        await manager.start()

        events_received: list[ConceptDescriptionEvent] = []

        async def collect_events() -> None:
            async for event in manager.subscribe_concept_description_updated():
                events_received.append(event)
                break

        task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)

        # Publish update event
        await manager._handle_event(
            ConceptDescriptionEvent(
                event_type=EventType.UPDATED,
                identifier="urn:test:cd:1",
                identifier_b64="b64",
                doc_bytes=b"{}",
            )
        )

        await asyncio.wait_for(task, timeout=1.0)

        assert len(events_received) == 1
        assert events_received[0].identifier == "urn:test:cd:1"


class TestGlobalSubscriptionManager:
    """Test global subscription manager singleton."""

    def test_get_subscription_manager_creates_instance(self) -> None:
        """get_subscription_manager creates instance if none exists."""
        # Reset global state
        set_subscription_manager(None)  # type: ignore

        manager1 = get_subscription_manager()
        assert manager1 is not None

        manager2 = get_subscription_manager()
        assert manager1 is manager2

    def test_set_subscription_manager(self) -> None:
        """set_subscription_manager overrides global instance."""
        custom_manager = SubscriptionManager()
        set_subscription_manager(custom_manager)

        assert get_subscription_manager() is custom_manager


class TestSubscriptionManagerSetEventBus:
    """Test setting event bus after construction."""

    async def test_set_event_bus_after_init(self) -> None:
        """Event bus can be set after initialization."""
        manager = SubscriptionManager()
        assert manager._event_bus is None

        mock_bus = MagicMock()
        mock_bus.subscribe = AsyncMock()

        manager.set_event_bus(mock_bus)

        await manager.start()
        mock_bus.subscribe.assert_called_once()


class TestSubscription:
    """Test Subscription dataclass."""

    def test_subscription_has_unique_id(self) -> None:
        """Each subscription has unique ID."""
        queue1: asyncio.Queue = asyncio.Queue()
        queue2: asyncio.Queue = asyncio.Queue()
        filter = SubscriptionFilter(entity_type="aas", event_types=[EventType.CREATED])

        sub1 = Subscription(id="sub-1", filter=filter, queue=queue1)
        sub2 = Subscription(id="sub-2", filter=filter, queue=queue2)

        assert sub1.id != sub2.id

    def test_subscription_stores_filter(self) -> None:
        """Subscription stores its filter."""
        filter = SubscriptionFilter(
            entity_type="submodel",
            event_types=[EventType.UPDATED],
            entity_id="urn:test:sm:1",
        )
        queue: asyncio.Queue = asyncio.Queue()

        sub = Subscription(id="sub-1", filter=filter, queue=queue)

        assert sub.filter.entity_type == "submodel"
        assert sub.filter.entity_id == "urn:test:sm:1"


class TestDeserializeShell:
    """Test _deserialize_shell helper."""

    def test_deserialize_valid_shell(self) -> None:
        """Deserialize valid shell JSON."""
        shell_data = {
            "id": "urn:example:shell:1",
            "idShort": "TestShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": "urn:example:asset:1",
            },
        }
        doc_bytes = orjson.dumps(shell_data)

        result = _deserialize_shell(doc_bytes)

        assert result is not None
        assert result.id == "urn:example:shell:1"
        assert result.id_short == "TestShell"

    def test_deserialize_none_returns_none(self) -> None:
        """Deserialize None returns None."""
        result = _deserialize_shell(None)
        assert result is None

    def test_deserialize_invalid_json_returns_none(self) -> None:
        """Deserialize invalid JSON returns None."""
        result = _deserialize_shell(b"not valid json")
        assert result is None

    def test_deserialize_invalid_schema_returns_none(self) -> None:
        """Deserialize invalid schema returns None."""
        # Missing required fields
        invalid_data = {"notAShell": True}
        doc_bytes = orjson.dumps(invalid_data)

        result = _deserialize_shell(doc_bytes)
        assert result is None


class TestDeserializeSubmodel:
    """Test _deserialize_submodel helper."""

    def test_deserialize_valid_submodel(self) -> None:
        """Deserialize valid submodel JSON."""
        submodel_data = {
            "id": "urn:example:submodel:1",
            "idShort": "TestSubmodel",
            "submodelElements": [
                {
                    "modelType": "Property",
                    "idShort": "Temperature",
                    "valueType": "xs:double",
                    "value": "25.5",
                }
            ],
        }
        doc_bytes = orjson.dumps(submodel_data)

        result = _deserialize_submodel(doc_bytes)

        assert result is not None
        assert result.id == "urn:example:submodel:1"
        assert result.id_short == "TestSubmodel"
        assert len(result.submodel_elements or []) == 1

    def test_deserialize_none_returns_none(self) -> None:
        """Deserialize None returns None."""
        result = _deserialize_submodel(None)
        assert result is None

    def test_deserialize_invalid_json_returns_none(self) -> None:
        """Deserialize invalid JSON returns None."""
        result = _deserialize_submodel(b"not valid json")
        assert result is None


class TestDeserializeConceptDescription:
    """Test _deserialize_concept_description helper."""

    def test_deserialize_valid_cd(self) -> None:
        """Deserialize valid concept description JSON."""
        cd_data = {
            "id": "urn:example:cd:1",
            "idShort": "TestCD",
        }
        doc_bytes = orjson.dumps(cd_data)

        result = _deserialize_concept_description(doc_bytes)

        assert result is not None
        assert result.id == "urn:example:cd:1"

    def test_deserialize_none_returns_none(self) -> None:
        """Deserialize None returns None."""
        result = _deserialize_concept_description(None)
        assert result is None

    def test_deserialize_invalid_json_returns_none(self) -> None:
        """Deserialize invalid JSON returns None."""
        result = _deserialize_concept_description(b"not valid json")
        assert result is None
