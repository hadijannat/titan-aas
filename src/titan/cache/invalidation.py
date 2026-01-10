"""Distributed cache invalidation for horizontal scaling.

Uses Redis Pub/Sub to broadcast cache invalidation messages across all
Titan-AAS instances. When any instance invalidates a cache entry, all
other instances receive the message and invalidate their local copies.

This ensures cache consistency across a distributed deployment.

Example:
    # Initialize the invalidation broadcaster
    broadcaster = CacheInvalidationBroadcaster()
    await broadcaster.start()

    # When a cache entry needs to be invalidated
    await broadcaster.invalidate_aas("base64_encoded_id")

    # All instances (including this one) will invalidate the cache entry
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Awaitable, Callable, cast

import orjson

from titan.cache.redis import get_redis

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from redis.asyncio.client import PubSub

    from titan.cache.redis import RedisCache

logger = logging.getLogger(__name__)

# Pub/Sub channel name
INVALIDATION_CHANNEL = "titan:cache:invalidation"


class InvalidationType(str, Enum):
    """Type of cache invalidation."""

    AAS = "aas"
    SUBMODEL = "submodel"
    SUBMODEL_ELEMENT = "element"
    CONCEPT_DESCRIPTION = "cd"
    ALL = "all"


@dataclass
class InvalidationMessage:
    """Cache invalidation message."""

    type: InvalidationType
    identifier_b64: str
    id_short_path: str | None = None  # For element invalidations

    def to_bytes(self) -> bytes:
        """Serialize to JSON bytes."""
        return orjson.dumps(
            {
                "type": self.type.value,
                "identifier_b64": self.identifier_b64,
                "id_short_path": self.id_short_path,
            }
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "InvalidationMessage":
        """Deserialize from JSON bytes."""
        parsed = orjson.loads(data)
        return cls(
            type=InvalidationType(parsed["type"]),
            identifier_b64=parsed["identifier_b64"],
            id_short_path=parsed.get("id_short_path"),
        )


# Handler type for invalidation callbacks
InvalidationHandler = Callable[[InvalidationMessage], Awaitable[None]]


class CacheInvalidationBroadcaster:
    """Broadcasts and receives cache invalidation messages via Redis Pub/Sub.

    This class handles both publishing invalidation messages and subscribing
    to receive them. When started, it will:
    1. Subscribe to the invalidation channel
    2. Process incoming invalidation messages
    3. Call registered handlers for each message

    The broadcaster should be started during application startup and stopped
    during shutdown.
    """

    def __init__(self, channel: str = INVALIDATION_CHANNEL):
        self.channel = channel
        self._handlers: list[InvalidationHandler] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._pubsub: PubSub | None = None
        self._redis: Redis | None = None

    async def _get_redis(self) -> Redis:
        """Get Redis client."""
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    def add_handler(self, handler: InvalidationHandler) -> None:
        """Register a handler for invalidation messages."""
        self._handlers.append(handler)
        handler_name = getattr(handler, "__name__", handler.__class__.__name__)
        logger.info(f"Registered invalidation handler: {handler_name}")

    async def start(self) -> None:
        """Start listening for invalidation messages."""
        if self._running:
            return

        redis = await self._get_redis()
        self._pubsub = redis.pubsub()
        await self._pubsub.subscribe(self.channel)

        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info(f"Started cache invalidation broadcaster on channel {self.channel}")

    async def stop(self) -> None:
        """Stop listening for invalidation messages."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.unsubscribe(self.channel)
            await self._pubsub.close()
            self._pubsub = None

        logger.info("Stopped cache invalidation broadcaster")

    async def _listen_loop(self) -> None:
        """Main loop for receiving invalidation messages."""
        while self._running and self._pubsub:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message is None:
                    continue

                if message["type"] == "message":
                    await self._handle_message(message["data"])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in invalidation listener: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, data: bytes) -> None:
        """Handle an incoming invalidation message."""
        try:
            msg = InvalidationMessage.from_bytes(data)
            logger.debug(f"Received invalidation: {msg.type.value} {msg.identifier_b64}")

            for handler in self._handlers:
                try:
                    await handler(msg)
                except Exception as e:
                    logger.error(f"Invalidation handler failed: {e}")

        except Exception as e:
            logger.error(f"Failed to parse invalidation message: {e}")

    async def publish(self, message: InvalidationMessage) -> int:
        """Publish an invalidation message to all instances.

        Returns the number of subscribers that received the message.
        """
        redis = await self._get_redis()
        count = cast(int, await redis.publish(self.channel, message.to_bytes()))
        logger.debug(
            f"Published invalidation {message.type.value} {message.identifier_b64} "
            f"to {count} subscribers"
        )
        return count

    # Convenience methods for common invalidations

    async def invalidate_aas(self, identifier_b64: str) -> int:
        """Invalidate a cached AAS."""
        return await self.publish(
            InvalidationMessage(type=InvalidationType.AAS, identifier_b64=identifier_b64)
        )

    async def invalidate_submodel(self, identifier_b64: str) -> int:
        """Invalidate a cached Submodel and its elements."""
        return await self.publish(
            InvalidationMessage(type=InvalidationType.SUBMODEL, identifier_b64=identifier_b64)
        )

    async def invalidate_element(self, submodel_b64: str, id_short_path: str) -> int:
        """Invalidate a cached SubmodelElement value."""
        return await self.publish(
            InvalidationMessage(
                type=InvalidationType.SUBMODEL_ELEMENT,
                identifier_b64=submodel_b64,
                id_short_path=id_short_path,
            )
        )

    async def invalidate_concept_description(self, identifier_b64: str) -> int:
        """Invalidate a cached ConceptDescription."""
        return await self.publish(
            InvalidationMessage(
                type=InvalidationType.CONCEPT_DESCRIPTION,
                identifier_b64=identifier_b64,
            )
        )

    async def invalidate_all(self) -> int:
        """Invalidate all cached entries (nuclear option)."""
        return await self.publish(
            InvalidationMessage(type=InvalidationType.ALL, identifier_b64="*")
        )


class LocalCacheInvalidator:
    """Handles local cache invalidation in response to broadcast messages.

    This class is registered as a handler with the CacheInvalidationBroadcaster
    and performs the actual cache invalidation on the local Redis cache.
    """

    def __init__(self) -> None:
        self._cache: RedisCache | None = None

    async def _get_cache(self) -> "RedisCache":
        """Get or create the Redis cache instance."""
        if self._cache is None:
            from titan.cache.redis import RedisCache, get_redis

            redis = await get_redis()
            self._cache = RedisCache(redis)
        return self._cache

    async def handle_invalidation(self, message: InvalidationMessage) -> None:
        """Handle an invalidation message by clearing local cache entries."""
        cache = await self._get_cache()

        if message.type == InvalidationType.AAS:
            await cache.delete_aas(message.identifier_b64)
            logger.debug(f"Invalidated local AAS cache: {message.identifier_b64}")

        elif message.type == InvalidationType.SUBMODEL:
            await cache.delete_submodel(message.identifier_b64)
            await cache.invalidate_submodel_elements(message.identifier_b64)
            logger.debug(f"Invalidated local Submodel cache: {message.identifier_b64}")

        elif message.type == InvalidationType.SUBMODEL_ELEMENT:
            if message.id_short_path:
                await cache.delete_element_value(message.identifier_b64, message.id_short_path)
                logger.debug(
                    f"Invalidated local element cache: "
                    f"{message.identifier_b64}/{message.id_short_path}"
                )

        elif message.type == InvalidationType.CONCEPT_DESCRIPTION:
            # ConceptDescriptions use same pattern as AAS
            from titan.cache.keys import CacheKeys

            redis = await get_redis()
            key = CacheKeys.concept_description_bytes(message.identifier_b64)
            await redis.delete(key)
            logger.debug(f"Invalidated local CD cache: {message.identifier_b64}")

        elif message.type == InvalidationType.ALL:
            # Clear all titan cache keys
            redis = await get_redis()
            pattern = "titan:*"
            async for key in redis.scan_iter(match=pattern):
                await redis.delete(key)
            logger.info("Invalidated all local cache entries")


# Singleton instances for application use
_broadcaster: CacheInvalidationBroadcaster | None = None
_invalidator: LocalCacheInvalidator | None = None


async def get_invalidation_broadcaster() -> CacheInvalidationBroadcaster:
    """Get or create the cache invalidation broadcaster."""
    global _broadcaster, _invalidator

    if _broadcaster is None:
        _broadcaster = CacheInvalidationBroadcaster()
        _invalidator = LocalCacheInvalidator()
        _broadcaster.add_handler(_invalidator.handle_invalidation)

    return _broadcaster


async def start_cache_invalidation() -> None:
    """Start the cache invalidation system."""
    broadcaster = await get_invalidation_broadcaster()
    await broadcaster.start()


async def stop_cache_invalidation() -> None:
    """Stop the cache invalidation system."""
    global _broadcaster
    if _broadcaster:
        await _broadcaster.stop()
        _broadcaster = None
