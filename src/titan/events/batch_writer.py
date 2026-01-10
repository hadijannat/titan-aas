"""Micro-batching writer for high-throughput scenarios.

Updates Redis immediately and batches downstream persistence hooks.
Persistence of the primary documents is expected to happen before publishing
events; batched flushes are intended for auxiliary sinks (audit logs, analytics).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
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


@dataclass
class BatchWriterConfig:
    """Configuration for the batch writer."""

    # Maximum items before forced flush
    batch_size: int = 1000

    # Maximum time between flushes (milliseconds)
    flush_interval_ms: int = 500

    # Maximum retries for failed batches
    max_retries: int = 3

    # Enable metrics collection
    enable_metrics: bool = True


@dataclass
class BatchMetrics:
    """Metrics for batch writer performance."""

    events_received: int = 0
    events_flushed: int = 0
    batches_flushed: int = 0
    flush_errors: int = 0
    avg_batch_size: float = 0.0
    avg_flush_latency_ms: float = 0.0
    last_flush_time: float = 0.0

    # Internal tracking
    _batch_sizes: list[int] = field(default_factory=list)
    _flush_latencies: list[float] = field(default_factory=list)

    def record_flush(self, batch_size: int, latency_ms: float) -> None:
        """Record a successful flush."""
        self.events_flushed += batch_size
        self.batches_flushed += 1
        self.last_flush_time = time.time()

        # Rolling average (keep last 100)
        self._batch_sizes.append(batch_size)
        self._flush_latencies.append(latency_ms)
        if len(self._batch_sizes) > 100:
            self._batch_sizes.pop(0)
            self._flush_latencies.pop(0)

        self.avg_batch_size = sum(self._batch_sizes) / len(self._batch_sizes)
        self.avg_flush_latency_ms = sum(self._flush_latencies) / len(self._flush_latencies)


# Type for optional broadcast callback
BroadcastCallback = Callable[[AnyEvent], Awaitable[None]]


class MicroBatchWriter:
    """Micro-batching writer for high-throughput event processing.

    Key features:
    - Immediate Redis updates (sub-millisecond read latency)
    - Batched PostgreSQL writes (reduced IOPS)
    - Configurable batch size and flush interval
    - Graceful shutdown with buffer drain
    """

    def __init__(
        self,
        bus: "EventBus",
        cache: "RedisCache",
        session_factory: Callable[[], "AsyncSession"],
        broadcast_callback: BroadcastCallback | None = None,
        config: BatchWriterConfig | None = None,
    ):
        self.bus = bus
        self.cache = cache
        self.session_factory = session_factory
        self.broadcast_callback = broadcast_callback
        self.config = config or BatchWriterConfig()

        # Event buffer
        self._buffer: deque[AnyEvent] = deque()
        self._buffer_lock = asyncio.Lock()

        # State
        self._running = False
        self._flush_task: asyncio.Task[None] | None = None

        # Metrics
        self.metrics = BatchMetrics()

    async def start(self) -> None:
        """Start the micro-batch writer."""
        if self._running:
            return

        self._running = True

        # Subscribe to the event bus
        await self.bus.subscribe(self._handle_event)

        # Start the bus
        await self.bus.start()

        # Start the periodic flush task
        self._flush_task = asyncio.create_task(self._periodic_flush())

        logger.info(
            f"MicroBatchWriter started (batch_size={self.config.batch_size}, "
            f"flush_interval={self.config.flush_interval_ms}ms)"
        )

    async def stop(self) -> None:
        """Stop the micro-batch writer and drain buffer."""
        self._running = False

        # Cancel periodic flush
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Drain remaining buffer
        if self._buffer:
            logger.info(f"Draining {len(self._buffer)} remaining events")
            await self._flush_buffer()

        await self.bus.stop()
        logger.info("MicroBatchWriter stopped")

    async def _handle_event(self, event: AnyEvent) -> None:
        """Handle incoming event: update Redis immediately, buffer for DB."""
        self.metrics.events_received += 1

        try:
            # STEP 1: Update Redis IMMEDIATELY (Real-time View)
            await self._update_cache(event)

            # STEP 2: Broadcast immediately (WebSocket, MQTT)
            if self.broadcast_callback:
                await self.broadcast_callback(event)

            # STEP 3: Buffer for PostgreSQL batch write
            async with self._buffer_lock:
                self._buffer.append(event)

                # Check if buffer is full
                if len(self._buffer) >= self.config.batch_size:
                    await self._flush_buffer()

        except Exception as e:
            logger.error(f"Error handling event {event.event_id}: {e}")
            raise

    async def _update_cache(self, event: AnyEvent) -> None:
        """Update Redis cache immediately (hot path)."""
        if isinstance(event, AasEvent):
            if event.event_type == EventType.DELETED:
                await self.cache.delete_aas(event.identifier_b64)
            elif event.doc_bytes and event.etag:
                await self.cache.set_aas(
                    event.identifier_b64,
                    event.doc_bytes,
                    event.etag,
                )

        elif isinstance(event, SubmodelEvent):
            if event.event_type == EventType.DELETED:
                await self.cache.delete_submodel(event.identifier_b64)
                await self.cache.invalidate_submodel_elements(event.identifier_b64)
            elif event.doc_bytes and event.etag:
                await self.cache.set_submodel(
                    event.identifier_b64,
                    event.doc_bytes,
                    event.etag,
                )
                # Invalidate element values when submodel changes
                if event.event_type == EventType.UPDATED:
                    await self.cache.invalidate_submodel_elements(event.identifier_b64)

        elif isinstance(event, SubmodelElementEvent):
            if event.event_type == EventType.DELETED:
                await self.cache.delete_element_value(
                    event.submodel_identifier_b64,
                    event.id_short_path,
                )
            elif event.value_bytes:
                await self.cache.set_element_value(
                    event.submodel_identifier_b64,
                    event.id_short_path,
                    event.value_bytes,
                )

    async def _periodic_flush(self) -> None:
        """Periodically flush buffer based on time interval."""
        interval_sec = self.config.flush_interval_ms / 1000.0

        while self._running:
            try:
                await asyncio.sleep(interval_sec)

                async with self._buffer_lock:
                    if self._buffer:
                        await self._flush_buffer()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")
                self.metrics.flush_errors += 1

    async def _flush_buffer(self) -> None:
        """Flush buffered events to PostgreSQL.

        This method assumes the buffer lock is held.
        """
        if not self._buffer:
            return

        batch_size = len(self._buffer)
        events = list(self._buffer)
        self._buffer.clear()

        start_time = time.perf_counter()

        try:
            # Get a database session
            async with self.session_factory() as session:
                async with session.begin():
                    for event in events:
                        await self._persist_event(session, event)

            # Record metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.metrics.record_flush(batch_size, latency_ms)

            logger.debug(
                f"Flushed {batch_size} events in {latency_ms:.2f}ms "
                f"(avg batch: {self.metrics.avg_batch_size:.1f})"
            )

        except Exception as e:
            logger.error(f"Error flushing batch of {batch_size} events: {e}")
            self.metrics.flush_errors += 1

            # Re-queue failed events for retry (at front of buffer)
            for event in reversed(events):
                self._buffer.appendleft(event)

            raise

    async def _persist_event(self, session: "AsyncSession", event: AnyEvent) -> None:
        """Persist a single event to the database.

        Note: The actual persistence is already done by the repository
        before the event is published. This method handles any additional
        DB operations needed (like updating timestamps, logging, etc.)

        In a full implementation, this would write to an event log table
        for audit and replay purposes.
        """
        # For now, events are already persisted before being published
        # This method is a hook for additional persistence logic:
        # - Event log/audit table
        # - Analytics aggregations
        # - Cross-table consistency checks

        pass  # Events already persisted by repository

    def get_metrics(self) -> dict[str, float | int]:
        """Get current metrics as a dictionary."""
        return {
            "events_received": self.metrics.events_received,
            "events_flushed": self.metrics.events_flushed,
            "batches_flushed": self.metrics.batches_flushed,
            "flush_errors": self.metrics.flush_errors,
            "avg_batch_size": round(self.metrics.avg_batch_size, 2),
            "avg_flush_latency_ms": round(self.metrics.avg_flush_latency_ms, 2),
            "buffer_size": len(self._buffer),
            "last_flush_time": self.metrics.last_flush_time,
        }
