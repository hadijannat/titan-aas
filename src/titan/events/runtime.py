"""Runtime wiring for the Titan-AAS event bus."""

from __future__ import annotations

import logging

from titan.config import settings
from titan.events.bus import EventBus, InMemoryEventBus
from titan.events.redis_bus import RedisStreamEventBus

logger = logging.getLogger(__name__)

_event_bus: EventBus | None = None


def create_event_bus() -> EventBus:
    """Create an event bus based on configuration."""
    backend = settings.event_bus_backend.lower()

    if backend in {"memory", "inmemory", "in_memory"}:
        return InMemoryEventBus()

    if backend in {"redis", "redis_stream", "redis-stream", "streams"}:
        return RedisStreamEventBus(
            stream_name=settings.event_bus_stream_name,
            consumer_group=settings.event_bus_consumer_group,
            consumer_id=settings.event_bus_consumer_id,
        )

    raise ValueError(
        "Unsupported event_bus_backend. Supported values: memory, redis, redis_stream."
    )


def get_event_bus() -> EventBus:
    """Get the singleton event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = create_event_bus()
    return _event_bus


async def start_event_bus() -> EventBus:
    """Start the configured event bus."""
    bus = get_event_bus()
    await bus.start()
    logger.info("Event bus started (%s)", type(bus).__name__)
    return bus


async def stop_event_bus() -> None:
    """Stop the configured event bus."""
    global _event_bus
    if _event_bus is None:
        return
    await _event_bus.stop()
    logger.info("Event bus stopped (%s)", type(_event_bus).__name__)
    _event_bus = None
