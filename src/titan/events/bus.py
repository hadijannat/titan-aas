"""Event bus implementation for Titan-AAS.

Provides pub/sub for entity change events:
- InMemoryEventBus: for single-instance deployments
- RedisStreamEventBus: for multi-instance with Redis Streams

The bus is consumed by the SingleWriter worker.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from titan.events.schemas import AnyEvent

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


EventHandler = Callable[[AnyEvent], Awaitable[None]]


class EventBus(ABC):
    """Abstract event bus interface."""

    @abstractmethod
    async def publish(self, event: AnyEvent) -> None:
        """Publish an event to the bus."""
        pass

    @abstractmethod
    async def subscribe(self, handler: EventHandler) -> None:
        """Subscribe a handler to receive events."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the event bus."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the event bus."""
        pass


class InMemoryEventBus(EventBus):
    """In-memory event bus using asyncio.Queue.

    Suitable for single-instance deployments. Events are processed
    in FIFO order by the SingleWriter.

    For horizontal scaling, use RedisStreamEventBus instead.
    """

    def __init__(self, max_size: int = 10000):
        self._queue: asyncio.Queue[AnyEvent] = asyncio.Queue(maxsize=max_size)
        self._handlers: list[EventHandler] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def publish(self, event: AnyEvent) -> None:
        """Publish an event to the queue.

        Non-blocking if queue has space, blocks if queue is full.
        """
        await self._queue.put(event)

    async def subscribe(self, handler: EventHandler) -> None:
        """Subscribe a handler to receive events."""
        self._handlers.append(handler)

    async def start(self) -> None:
        """Start processing events."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Stop processing events."""
        self._running = False

        if self._task:
            # Wait for current event to finish, then cancel
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self) -> None:
        """Main event processing loop."""
        while self._running:
            try:
                # Wait for event with timeout to allow graceful shutdown
                event = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )

                # Process event through all handlers
                for handler in self._handlers:
                    try:
                        await handler(event)
                    except Exception:
                        # Log error but continue processing
                        logger.exception("Error in event handler")

                self._queue.task_done()

            except TimeoutError:
                # No event, check if we should continue
                continue
            except asyncio.CancelledError:
                break

    @property
    def pending_count(self) -> int:
        """Number of events waiting to be processed."""
        return self._queue.qsize()

    async def drain(self) -> None:
        """Wait for all pending events to be processed."""
        await self._queue.join()
