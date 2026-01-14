"""Subscription manager for real-time GraphQL updates.

This module provides a manager that connects GraphQL subscriptions to the
event bus, allowing clients to receive real-time updates via WebSocket.

Architecture:
    Event Bus → SubscriptionManager → GraphQL Subscriptions → WebSocket Clients

The manager:
1. Subscribes to the event bus for all entity events
2. Maintains a registry of active subscriptions
3. Broadcasts events to matching subscriptions using asyncio.Queue
4. Handles subscription lifecycle (register, unregister, cleanup)

Example:
    manager = SubscriptionManager(event_bus)
    await manager.start()

    # In subscription resolver
    async for event in manager.subscribe_shell_updates("shell-id"):
        yield convert_to_graphql(event)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from titan.events.schemas import (
    AasEvent,
    AnyEvent,
    ConceptDescriptionEvent,
    EventType,
    SubmodelEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from titan.events.bus import EventBus

logger = logging.getLogger(__name__)


@dataclass
class SubscriptionFilter:
    """Filter criteria for a subscription.

    Attributes:
        entity_type: Type of entity to filter (aas, submodel, concept_description)
        event_types: Event types to include (created, updated, deleted)
        entity_id: Optional specific entity ID to filter
    """

    entity_type: str
    event_types: list[EventType]
    entity_id: str | None = None

    def matches(self, event: AnyEvent) -> bool:
        """Check if an event matches this filter.

        Args:
            event: The event to check

        Returns:
            True if the event matches the filter criteria
        """
        # Check entity type
        if event.entity != self.entity_type:
            return False

        # Check event type
        if event.event_type not in self.event_types:
            return False

        # Check entity ID if specified
        if self.entity_id is not None:
            event_id = getattr(event, "identifier", None)
            if event_id != self.entity_id:
                return False

        return True


@dataclass
class Subscription:
    """An active subscription registration.

    Attributes:
        id: Unique subscription identifier
        filter: Filter criteria for events
        queue: Queue for delivering events to the subscription
    """

    id: str
    filter: SubscriptionFilter
    queue: asyncio.Queue[AnyEvent | None]


class SubscriptionManager:
    """Manages GraphQL subscriptions connected to the event bus.

    The manager maintains a registry of active subscriptions and broadcasts
    events from the event bus to matching subscriptions.

    Attributes:
        event_bus: The event bus to subscribe to
        max_queue_size: Maximum number of events to buffer per subscription
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        max_queue_size: int = 100,
    ):
        """Initialize the subscription manager.

        Args:
            event_bus: Event bus to subscribe to (can be set later)
            max_queue_size: Maximum events to buffer per subscription
        """
        self._event_bus = event_bus
        self._max_queue_size = max_queue_size
        self._subscriptions: dict[str, Subscription] = {}
        self._lock = asyncio.Lock()
        self._started = False

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Set the event bus after initialization.

        Args:
            event_bus: The event bus to use
        """
        self._event_bus = event_bus

    async def start(self) -> None:
        """Start the subscription manager.

        Subscribes to the event bus to receive events.
        """
        if self._started:
            return

        if self._event_bus is None:
            logger.warning("SubscriptionManager started without event bus")
            return

        await self._event_bus.subscribe(self._handle_event)
        self._started = True
        logger.info("SubscriptionManager started")

    async def stop(self) -> None:
        """Stop the subscription manager.

        Closes all active subscription queues.
        """
        async with self._lock:
            # Close all subscription queues
            for sub in self._subscriptions.values():
                # Put None to signal end of stream
                try:
                    sub.queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

            self._subscriptions.clear()

        self._started = False
        logger.info("SubscriptionManager stopped")

    async def _handle_event(self, event: AnyEvent) -> None:
        """Handle an event from the event bus.

        Broadcasts the event to all matching subscriptions.

        Args:
            event: The event to handle
        """
        async with self._lock:
            subscriptions = list(self._subscriptions.values())

        # Broadcast to matching subscriptions
        for sub in subscriptions:
            if sub.filter.matches(event):
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop oldest event if queue is full
                    try:
                        sub.queue.get_nowait()
                        sub.queue.put_nowait(event)
                    except asyncio.QueueEmpty:
                        pass
                    logger.warning(
                        "Subscription %s queue full, dropped oldest event",
                        sub.id,
                    )

    async def _register(self, filter: SubscriptionFilter) -> Subscription:
        """Register a new subscription.

        Args:
            filter: Filter criteria for the subscription

        Returns:
            The new subscription
        """
        sub_id = str(uuid4())
        queue: asyncio.Queue[AnyEvent | None] = asyncio.Queue(maxsize=self._max_queue_size)
        subscription = Subscription(id=sub_id, filter=filter, queue=queue)

        async with self._lock:
            self._subscriptions[sub_id] = subscription

        logger.debug(
            "Registered subscription %s for %s events",
            sub_id,
            filter.entity_type,
        )
        return subscription

    async def _unregister(self, sub_id: str) -> None:
        """Unregister a subscription.

        Args:
            sub_id: The subscription ID to unregister
        """
        async with self._lock:
            if sub_id in self._subscriptions:
                del self._subscriptions[sub_id]
                logger.debug("Unregistered subscription %s", sub_id)

    async def _iter_events(self, subscription: Subscription) -> AsyncIterator[AnyEvent]:
        """Iterate over events for a subscription.

        Args:
            subscription: The subscription to iterate

        Yields:
            Events matching the subscription filter
        """
        try:
            while True:
                event = await subscription.queue.get()
                if event is None:
                    # Subscription closed
                    break
                yield event
        finally:
            await self._unregister(subscription.id)

    # Public subscription methods

    async def subscribe_shell_created(self) -> AsyncIterator[AasEvent]:
        """Subscribe to shell creation events.

        Yields:
            AasEvent for each shell created
        """
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.CREATED],
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, AasEvent):
                yield event

    async def subscribe_shell_updated(
        self, entity_id: str | None = None
    ) -> AsyncIterator[AasEvent]:
        """Subscribe to shell update events.

        Args:
            entity_id: Optional shell ID to filter updates

        Yields:
            AasEvent for each shell updated
        """
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.UPDATED],
            entity_id=entity_id,
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, AasEvent):
                yield event

    async def subscribe_shell_deleted(self) -> AsyncIterator[AasEvent]:
        """Subscribe to shell deletion events.

        Yields:
            AasEvent for each shell deleted
        """
        filter = SubscriptionFilter(
            entity_type="aas",
            event_types=[EventType.DELETED],
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, AasEvent):
                yield event

    async def subscribe_submodel_created(self) -> AsyncIterator[SubmodelEvent]:
        """Subscribe to submodel creation events.

        Yields:
            SubmodelEvent for each submodel created
        """
        filter = SubscriptionFilter(
            entity_type="submodel",
            event_types=[EventType.CREATED],
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, SubmodelEvent):
                yield event

    async def subscribe_submodel_updated(
        self, entity_id: str | None = None
    ) -> AsyncIterator[SubmodelEvent]:
        """Subscribe to submodel update events.

        Args:
            entity_id: Optional submodel ID to filter updates

        Yields:
            SubmodelEvent for each submodel updated
        """
        filter = SubscriptionFilter(
            entity_type="submodel",
            event_types=[EventType.UPDATED],
            entity_id=entity_id,
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, SubmodelEvent):
                yield event

    async def subscribe_submodel_deleted(self) -> AsyncIterator[SubmodelEvent]:
        """Subscribe to submodel deletion events.

        Yields:
            SubmodelEvent for each submodel deleted
        """
        filter = SubscriptionFilter(
            entity_type="submodel",
            event_types=[EventType.DELETED],
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, SubmodelEvent):
                yield event

    async def subscribe_concept_description_created(
        self,
    ) -> AsyncIterator[ConceptDescriptionEvent]:
        """Subscribe to concept description creation events.

        Yields:
            ConceptDescriptionEvent for each created
        """
        filter = SubscriptionFilter(
            entity_type="concept_description",
            event_types=[EventType.CREATED],
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, ConceptDescriptionEvent):
                yield event

    async def subscribe_concept_description_updated(
        self, entity_id: str | None = None
    ) -> AsyncIterator[ConceptDescriptionEvent]:
        """Subscribe to concept description update events.

        Args:
            entity_id: Optional ID to filter updates

        Yields:
            ConceptDescriptionEvent for each updated
        """
        filter = SubscriptionFilter(
            entity_type="concept_description",
            event_types=[EventType.UPDATED],
            entity_id=entity_id,
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, ConceptDescriptionEvent):
                yield event

    async def subscribe_concept_description_deleted(
        self,
    ) -> AsyncIterator[ConceptDescriptionEvent]:
        """Subscribe to concept description deletion events.

        Yields:
            ConceptDescriptionEvent for each deleted
        """
        filter = SubscriptionFilter(
            entity_type="concept_description",
            event_types=[EventType.DELETED],
        )
        subscription = await self._register(filter)

        async for event in self._iter_events(subscription):
            if isinstance(event, ConceptDescriptionEvent):
                yield event

    @property
    def subscription_count(self) -> int:
        """Get the number of active subscriptions."""
        return len(self._subscriptions)


# Global subscription manager instance
_subscription_manager: SubscriptionManager | None = None


def get_subscription_manager() -> SubscriptionManager:
    """Get the global subscription manager instance.

    Returns:
        The global SubscriptionManager
    """
    global _subscription_manager
    if _subscription_manager is None:
        _subscription_manager = SubscriptionManager()
    return _subscription_manager


def set_subscription_manager(manager: SubscriptionManager) -> None:
    """Set the global subscription manager instance.

    Args:
        manager: The SubscriptionManager to use globally
    """
    global _subscription_manager
    _subscription_manager = manager
