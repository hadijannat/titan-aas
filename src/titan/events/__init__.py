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
from titan.events.publisher import (
    publish_aas_deleted,
    publish_aas_event,
    publish_concept_description_event,
    publish_submodel_deleted,
    publish_submodel_element_event,
    publish_submodel_event,
)
from titan.events.redis_bus import RedisStreamEventBus
from titan.events.runtime import create_event_bus, get_event_bus, start_event_bus, stop_event_bus
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
    "RedisStreamEventBus",
    "create_event_bus",
    "get_event_bus",
    "start_event_bus",
    "stop_event_bus",
    # Publishers
    "publish_aas_event",
    "publish_aas_deleted",
    "publish_submodel_event",
    "publish_submodel_deleted",
    "publish_submodel_element_event",
    "publish_concept_description_event",
    # Workers
    "SingleWriter",
    "MicroBatchWriter",
    "BatchWriterConfig",
]
