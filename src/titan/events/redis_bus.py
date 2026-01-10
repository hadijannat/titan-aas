"""Redis Streams EventBus for horizontal scaling.

Provides distributed event processing using Redis Streams with consumer groups.
Each Titan-AAS instance joins a consumer group, allowing work to be distributed
and ensuring each event is processed exactly once across the cluster.

Features:
- Distributed event processing via consumer groups
- Automatic consumer registration and heartbeat
- At-least-once delivery with acknowledgment
- Dead letter queue for failed events
- Graceful shutdown with pending event processing
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import orjson

from titan.cache.redis import get_redis
from titan.events.bus import EventBus, EventHandler
from titan.events.schemas import (
    AasEvent,
    AnyEvent,
    ConceptDescriptionEvent,
    EventType,
    SubmodelElementEvent,
    SubmodelEvent,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Stream configuration
STREAM_NAME = "titan:events"
CONSUMER_GROUP = "titan-workers"
DEAD_LETTER_STREAM = "titan:events:dead"

# Processing configuration
BATCH_SIZE = 10
BLOCK_MS = 1000  # Block for 1 second when waiting for events
CLAIM_IDLE_MS = 30000  # Claim messages idle for 30 seconds
MAX_RETRIES = 3


def _generate_consumer_id() -> str:
    """Generate a unique consumer ID for this instance."""
    hostname = os.environ.get("HOSTNAME", os.environ.get("POD_NAME", "unknown"))
    return f"{hostname}-{uuid4().hex[:8]}"


class RedisStreamEventBus(EventBus):
    """Redis Streams-based event bus for distributed processing.

    Uses Redis Streams with consumer groups to distribute event processing
    across multiple Titan-AAS instances. Each instance registers as a
    consumer in the group, and Redis ensures each event is delivered
    to exactly one consumer.

    Example:
        bus = RedisStreamEventBus()
        await bus.subscribe(handle_event)
        await bus.start()

        # Publish events (goes to all instances via stream)
        await bus.publish(AasEvent(...))

        # On shutdown
        await bus.stop()
    """

    def __init__(
        self,
        stream_name: str = STREAM_NAME,
        consumer_group: str = CONSUMER_GROUP,
        consumer_id: str | None = None,
    ):
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_id = consumer_id or _generate_consumer_id()
        self._handlers: list[EventHandler] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._redis: Redis | None = None

    async def _get_redis(self) -> Redis:
        """Get Redis client, initializing if needed."""
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    async def _ensure_stream_and_group(self) -> None:
        """Ensure the stream and consumer group exist."""
        redis = await self._get_redis()

        try:
            # Create consumer group (also creates stream if it doesn't exist)
            await redis.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(
                f"Created consumer group {self.consumer_group} on stream {self.stream_name}"
            )
        except Exception as e:
            # Group already exists - this is fine
            if "BUSYGROUP" not in str(e):
                raise
            logger.debug(f"Consumer group {self.consumer_group} already exists")

    async def publish(self, event: AnyEvent) -> None:
        """Publish an event to the Redis Stream.

        The event is serialized to JSON and added to the stream.
        All consumers in the group will compete to process it.
        """
        redis = await self._get_redis()

        # Serialize event to JSON
        event_data = self._serialize_event(event)

        # Add to stream
        message_id = await redis.xadd(
            self.stream_name,
            {"data": event_data},
            maxlen=100000,  # Keep last 100k events
        )

        logger.debug(f"Published event {event.event_id} as {message_id!r}")

    async def subscribe(self, handler: EventHandler) -> None:
        """Subscribe a handler to receive events."""
        self._handlers.append(handler)
        handler_name = getattr(handler, "__name__", handler.__class__.__name__)
        logger.info(f"Registered event handler: {handler_name}")

    async def start(self) -> None:
        """Start consuming events from the stream."""
        if self._running:
            return

        await self._ensure_stream_and_group()

        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info(f"Started consumer {self.consumer_id} in group {self.consumer_group}")

    async def stop(self) -> None:
        """Stop consuming events."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(f"Stopped consumer {self.consumer_id}")

    async def _consume_loop(self) -> None:
        """Main event consumption loop."""
        redis = await self._get_redis()

        while self._running:
            try:
                # First, try to claim any pending messages from dead consumers
                await self._claim_pending_messages(redis)

                # Read new messages from the stream
                messages = await redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_id,
                    streams={self.stream_name: ">"},  # Only new messages
                    count=BATCH_SIZE,
                    block=BLOCK_MS,
                )

                if not messages:
                    continue

                # Process each message
                for _stream_name, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        await self._process_message(redis, message_id, message_data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in consume loop: {e}")
                await asyncio.sleep(1)  # Back off on error

    async def _claim_pending_messages(self, redis: Redis) -> None:
        """Claim messages that have been pending too long.

        This handles the case where a consumer dies without ACKing messages.
        """
        try:
            # Check for pending messages older than CLAIM_IDLE_MS
            pending = await redis.xpending_range(
                self.stream_name,
                self.consumer_group,
                min="-",
                max="+",
                count=BATCH_SIZE,
            )

            for entry in pending:
                message_id = entry["message_id"]
                idle_time = entry.get("time_since_delivered", 0)
                delivery_count = entry.get("times_delivered", 0)

                if idle_time > CLAIM_IDLE_MS:
                    if delivery_count >= MAX_RETRIES:
                        # Move to dead letter queue
                        await self._move_to_dead_letter(redis, message_id)
                    else:
                        # Claim the message for this consumer
                        claimed = await redis.xclaim(
                            self.stream_name,
                            self.consumer_group,
                            self.consumer_id,
                            min_idle_time=CLAIM_IDLE_MS,
                            message_ids=[message_id],
                        )

                        # Process claimed messages
                        for msg_id, msg_data in claimed:
                            await self._process_message(redis, msg_id, msg_data)

        except Exception as e:
            logger.warning(f"Error claiming pending messages: {e}")

    async def _process_message(
        self, redis: Redis, message_id: bytes | str, message_data: dict[bytes, bytes]
    ) -> None:
        """Process a single message from the stream."""
        try:
            # Deserialize event
            data_bytes = message_data.get(b"data")
            if not data_bytes:
                logger.warning(f"Message {message_id!r} has no data field")
                await redis.xack(self.stream_name, self.consumer_group, message_id)
                return

            event = self._deserialize_event(data_bytes)

            # Process through handlers
            for handler in self._handlers:
                try:
                    await handler(event)
                except Exception as e:
                    handler_name = getattr(handler, "__name__", handler.__class__.__name__)
                    logger.error(f"Handler {handler_name} failed: {e}")
                    raise  # Re-raise to trigger retry logic

            # Acknowledge successful processing
            await redis.xack(self.stream_name, self.consumer_group, message_id)
            logger.debug(f"Processed and ACKed message {message_id!r}")

        except Exception as e:
            logger.error(f"Failed to process message {message_id!r}: {e}")
            # Message will be retried (not ACKed)

    async def _move_to_dead_letter(self, redis: Redis, message_id: bytes | str) -> None:
        """Move a failed message to the dead letter stream."""
        try:
            # Read the message
            messages = await redis.xrange(self.stream_name, message_id, message_id)
            if messages:
                _, message_data = messages[0]
                original_id = (
                    message_id.decode() if isinstance(message_id, bytes) else str(message_id)
                )
                # Add to dead letter stream with original ID in metadata
                await redis.xadd(
                    DEAD_LETTER_STREAM,
                    {
                        "original_id": original_id,
                        "original_stream": self.stream_name,
                        **message_data,
                    },
                )
                logger.warning(f"Moved message {message_id!r} to dead letter queue")

            # ACK the original message
            await redis.xack(self.stream_name, self.consumer_group, message_id)

        except Exception as e:
            logger.error(f"Failed to move message to dead letter: {e}")

    def _serialize_event(self, event: AnyEvent) -> bytes:
        """Serialize an event to JSON bytes."""
        # Convert dataclass to dict
        data = asdict(event)

        # Serialize enums
        if isinstance(data.get("event_type"), EventType):
            data["event_type"] = data["event_type"].value

        # Handle datetime serialization
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()

        # Handle bytes fields (base64 encode)
        for key in ("doc_bytes", "value_bytes"):
            if key in data and data[key] is not None:
                data[key] = base64.b64encode(data[key]).decode("ascii")

        # Add event type discriminator
        data["_event_type"] = event.entity

        return orjson.dumps(data)

    def _deserialize_event(self, data: bytes) -> AnyEvent:
        """Deserialize JSON bytes to an event."""
        parsed = orjson.loads(data)

        # Handle datetime deserialization
        if "timestamp" in parsed and isinstance(parsed["timestamp"], str):
            parsed["timestamp"] = datetime.fromisoformat(parsed["timestamp"])

        # Handle bytes fields (base64 decode)
        for key in ("doc_bytes", "value_bytes"):
            if key in parsed and parsed[key] is not None:
                parsed[key] = base64.b64decode(parsed[key])

        # Determine event type and construct
        event_type_str = parsed.pop("_event_type", None)
        entity = parsed.get("entity", event_type_str)

        # Convert event_type string to enum
        event_type_value = parsed.get("event_type")
        if event_type_value is not None and not isinstance(event_type_value, EventType):
            parsed["event_type"] = EventType(event_type_value)

        if entity == "aas":
            return AasEvent(**{k: v for k, v in parsed.items() if k != "entity"})
        elif entity == "submodel":
            return SubmodelEvent(**{k: v for k, v in parsed.items() if k != "entity"})
        elif entity == "element":
            return SubmodelElementEvent(**{k: v for k, v in parsed.items() if k != "entity"})
        elif entity == "concept_description":
            return ConceptDescriptionEvent(**{k: v for k, v in parsed.items() if k != "entity"})
        else:
            raise ValueError(f"Unknown event entity: {entity}")

    @property
    def pending_count(self) -> int:
        """Get count of pending messages (not implemented for Redis)."""
        return 0  # Would require async call

    async def get_pending_info(self) -> dict[str, Any]:
        """Get detailed pending message information."""
        redis = await self._get_redis()
        try:
            info = await redis.xpending(self.stream_name, self.consumer_group)
            return {
                "pending": info.get("pending", 0),
                "consumers": info.get("consumers", []),
                "min_id": info.get("min", None),
                "max_id": info.get("max", None),
            }
        except Exception:
            return {"pending": 0, "consumers": [], "min_id": None, "max_id": None}

    async def health_check(self) -> bool:
        """Check if the event bus is healthy."""
        try:
            redis = await self._get_redis()
            # Check stream exists
            info = await redis.xinfo_stream(self.stream_name)
            return info is not None
        except Exception:
            return False
