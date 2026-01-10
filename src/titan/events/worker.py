"""Single Writer worker for Titan-AAS.

Consumes events to update cache and broadcast downstream.

Note: Persistence is handled by repositories before events are published.
The writer is responsible for cache consistency and event propagation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable

from titan.events.schemas import (
    AasEvent,
    AnyEvent,
    EventType,
    SubmodelElementEvent,
    SubmodelEvent,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from titan.cache.redis import RedisCache
    from titan.events.bus import EventBus


logger = logging.getLogger(__name__)

# Type for optional broadcast callback
BroadcastCallback = Callable[[AnyEvent], Awaitable[None]]


class SingleWriter:
    """Single writer for consistent event processing.

    Processes events sequentially to ensure:
    - Database writes are ordered
    - Cache is always consistent with DB
    - Broadcasts happen after successful persistence
    """

    def __init__(
        self,
        bus: EventBus,
        cache: RedisCache,
        session_factory: Callable[[], AsyncSession],
        broadcast_callback: BroadcastCallback | None = None,
    ):
        self.bus = bus
        self.cache = cache
        self.session_factory = session_factory
        self.broadcast_callback = broadcast_callback
        self._running = False

    async def start(self) -> None:
        """Start the single writer."""
        if self._running:
            return

        self._running = True

        # Subscribe to the event bus
        await self.bus.subscribe(self._handle_event)

        # Start the bus
        await self.bus.start()

        logger.info("SingleWriter started")

    async def stop(self) -> None:
        """Stop the single writer."""
        self._running = False
        await self.bus.stop()
        logger.info("SingleWriter stopped")

    async def _handle_event(self, event: AnyEvent) -> None:
        """Handle a single event.

        This is the core processing logic that:
        1. Persists the change to the database
        2. Updates the cache
        3. Broadcasts the event
        """
        try:
            if isinstance(event, AasEvent):
                await self._handle_aas_event(event)
            elif isinstance(event, SubmodelEvent):
                await self._handle_submodel_event(event)
            elif isinstance(event, SubmodelElementEvent):
                await self._handle_element_event(event)
            else:
                logger.warning(f"Unknown event type: {type(event)}")
                return

            # Broadcast after successful processing
            if self.broadcast_callback:
                await self.broadcast_callback(event)

        except Exception as e:
            logger.error(f"Error processing event {event.event_id}: {e}")
            raise

    async def _handle_aas_event(self, event: AasEvent) -> None:
        """Handle AAS create/update/delete event."""
        if event.event_type == EventType.CREATED:
            # Cache the new AAS
            if event.doc_bytes and event.etag:
                await self.cache.set_aas(
                    event.identifier_b64,
                    event.doc_bytes,
                    event.etag,
                )
            logger.debug(f"AAS created: {event.identifier}")

        elif event.event_type == EventType.UPDATED:
            # Update cache with new bytes
            if event.doc_bytes and event.etag:
                await self.cache.set_aas(
                    event.identifier_b64,
                    event.doc_bytes,
                    event.etag,
                )
            logger.debug(f"AAS updated: {event.identifier}")

        elif event.event_type == EventType.DELETED:
            # Invalidate cache
            await self.cache.delete_aas(event.identifier_b64)
            logger.debug(f"AAS deleted: {event.identifier}")

    async def _handle_submodel_event(self, event: SubmodelEvent) -> None:
        """Handle Submodel create/update/delete event."""
        if event.event_type == EventType.CREATED:
            if event.doc_bytes and event.etag:
                await self.cache.set_submodel(
                    event.identifier_b64,
                    event.doc_bytes,
                    event.etag,
                )
            logger.debug(f"Submodel created: {event.identifier}")

        elif event.event_type == EventType.UPDATED:
            if event.doc_bytes and event.etag:
                await self.cache.set_submodel(
                    event.identifier_b64,
                    event.doc_bytes,
                    event.etag,
                )
            # Invalidate element values when submodel changes
            await self.cache.invalidate_submodel_elements(event.identifier_b64)
            logger.debug(f"Submodel updated: {event.identifier}")

        elif event.event_type == EventType.DELETED:
            await self.cache.delete_submodel(event.identifier_b64)
            await self.cache.invalidate_submodel_elements(event.identifier_b64)
            logger.debug(f"Submodel deleted: {event.identifier}")

    async def _handle_element_event(self, event: SubmodelElementEvent) -> None:
        """Handle SubmodelElement $value update event."""
        if event.event_type == EventType.UPDATED:
            if event.value_bytes:
                await self.cache.set_element_value(
                    event.submodel_identifier_b64,
                    event.id_short_path,
                    event.value_bytes,
                )
            logger.debug(f"Element updated: {event.id_short_path}")

        elif event.event_type == EventType.DELETED:
            await self.cache.delete_element_value(
                event.submodel_identifier_b64,
                event.id_short_path,
            )
            logger.debug(f"Element deleted: {event.id_short_path}")
