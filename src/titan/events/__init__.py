"""Event system for Titan-AAS.

Implements the Single Writer pattern:
- All writes produce events to an event bus
- A single worker processes events sequentially
- Worker handles: DB persistence, cache update, broadcast

This ensures:
- Consistent ordering of writes
- No race conditions in cache invalidation
- Deterministic event processing

For high-throughput scenarios, use MicroBatchWriter:
- Immediate Redis updates (sub-millisecond read latency)
- Batched PostgreSQL writes (reduced IOPS)
- Handles 5,000+ writes/sec
"""

from titan.events.batch_writer import BatchWriterConfig, MicroBatchWriter
from titan.events.bus import EventBus, InMemoryEventBus
from titan.events.schemas import (
    AasEvent,
    AnyEvent,
    EventType,
    SubmodelElementEvent,
    SubmodelEvent,
)
from titan.events.worker import SingleWriter

__all__ = [
    # Event types
    "EventType",
    "AasEvent",
    "SubmodelEvent",
    "SubmodelElementEvent",
    "AnyEvent",
    # Bus
    "EventBus",
    "InMemoryEventBus",
    # Workers
    "SingleWriter",
    "MicroBatchWriter",
    "BatchWriterConfig",
]
