"""Redis cache implementation for Titan-AAS.

Provides async Redis operations for caching canonical bytes.
Uses redis-py async client for connection pooling.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, cast

import redis.asyncio as redis

from titan.cache.keys import CacheKeys
from titan.config import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis

# Module-level connection pool
_redis_client: Redis | None = None

# Default TTL (1 hour)
DEFAULT_TTL = 3600


async def get_redis() -> Redis:
    """Get or create the Redis client.

    Uses connection pooling for efficient connection management.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,  # We're storing bytes
        )
    return _redis_client


async def close_redis() -> None:
    """Close Redis connections."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


class RedisCache:
    """Cache operations for AAS entities.

    Provides typed methods for caching canonical bytes with TTL.
    """

    def __init__(self, client: Redis, ttl: int = DEFAULT_TTL):
        self.client = client
        self.ttl = ttl

    # -------------------------------------------------------------------------
    # Generic cache pair operations (reduce boilerplate)
    # -------------------------------------------------------------------------

    async def _get_pair(self, key_bytes: str, key_etag: str) -> tuple[bytes, str] | None:
        """Get cached bytes and ETag pair using pipeline.

        Args:
            key_bytes: Redis key for document bytes
            key_etag: Redis key for ETag

        Returns:
            Tuple of (doc_bytes, etag) or None if not cached.
        """
        async with self.client.pipeline() as pipe:
            pipe.get(key_bytes)
            pipe.get(key_etag)
            results = await pipe.execute()

        doc_bytes, etag = results
        if doc_bytes is None or etag is None:
            return None

        return (doc_bytes, etag.decode() if isinstance(etag, bytes) else etag)

    async def _set_pair(self, key_bytes: str, key_etag: str, doc_bytes: bytes, etag: str) -> None:
        """Set cached bytes and ETag pair using pipeline.

        Args:
            key_bytes: Redis key for document bytes
            key_etag: Redis key for ETag
            doc_bytes: Document bytes to cache
            etag: ETag string to cache
        """
        async with self.client.pipeline() as pipe:
            pipe.setex(key_bytes, self.ttl, doc_bytes)
            pipe.setex(key_etag, self.ttl, etag)
            await pipe.execute()

    # -------------------------------------------------------------------------
    # AAS caching
    # -------------------------------------------------------------------------

    async def get_aas(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Get cached AAS bytes and ETag.

        Returns:
            Tuple of (doc_bytes, etag) or None if not cached.
        """
        return await self._get_pair(
            CacheKeys.aas_bytes(identifier_b64),
            CacheKeys.aas_etag(identifier_b64),
        )

    async def set_aas(self, identifier_b64: str, doc_bytes: bytes, etag: str) -> None:
        """Cache AAS bytes and ETag."""
        await self._set_pair(
            CacheKeys.aas_bytes(identifier_b64),
            CacheKeys.aas_etag(identifier_b64),
            doc_bytes,
            etag,
        )

    async def delete_aas(self, identifier_b64: str) -> None:
        """Delete cached AAS."""
        key_bytes = CacheKeys.aas_bytes(identifier_b64)
        key_etag = CacheKeys.aas_etag(identifier_b64)
        await self.client.delete(key_bytes, key_etag)

    # -------------------------------------------------------------------------
    # Submodel caching
    # -------------------------------------------------------------------------

    async def get_submodel(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Get cached Submodel bytes and ETag."""
        return await self._get_pair(
            CacheKeys.submodel_bytes(identifier_b64),
            CacheKeys.submodel_etag(identifier_b64),
        )

    async def set_submodel(self, identifier_b64: str, doc_bytes: bytes, etag: str) -> None:
        """Cache Submodel bytes and ETag."""
        await self._set_pair(
            CacheKeys.submodel_bytes(identifier_b64),
            CacheKeys.submodel_etag(identifier_b64),
            doc_bytes,
            etag,
        )

    async def delete_submodel(self, identifier_b64: str) -> None:
        """Delete cached Submodel."""
        key_bytes = CacheKeys.submodel_bytes(identifier_b64)
        key_etag = CacheKeys.submodel_etag(identifier_b64)
        await self.client.delete(key_bytes, key_etag)

    # -------------------------------------------------------------------------
    # ConceptDescription caching
    # -------------------------------------------------------------------------

    async def get_concept_description(self, identifier_b64: str) -> tuple[bytes, str] | None:
        """Get cached ConceptDescription bytes and ETag."""
        return await self._get_pair(
            CacheKeys.concept_description_bytes(identifier_b64),
            CacheKeys.concept_description_etag(identifier_b64),
        )

    async def set_concept_description(
        self, identifier_b64: str, doc_bytes: bytes, etag: str
    ) -> None:
        """Cache ConceptDescription bytes and ETag."""
        await self._set_pair(
            CacheKeys.concept_description_bytes(identifier_b64),
            CacheKeys.concept_description_etag(identifier_b64),
            doc_bytes,
            etag,
        )

    async def delete_concept_description(self, identifier_b64: str) -> None:
        """Delete cached ConceptDescription."""
        key_bytes = CacheKeys.concept_description_bytes(identifier_b64)
        key_etag = CacheKeys.concept_description_etag(identifier_b64)
        await self.client.delete(key_bytes, key_etag)

    # -------------------------------------------------------------------------
    # SubmodelElement $value caching
    # -------------------------------------------------------------------------

    async def get_element_value(self, submodel_b64: str, id_short_path: str) -> bytes | None:
        """Get cached SubmodelElement $value.

        This is for the hot path of $value reads.
        """
        key = CacheKeys.submodel_element_value(submodel_b64, id_short_path)
        return cast(bytes | None, await self.client.get(key))

    async def set_element_value(
        self,
        submodel_b64: str,
        id_short_path: str,
        value_bytes: bytes,
        ttl: int | None = None,
    ) -> None:
        """Cache SubmodelElement $value.

        Uses shorter TTL for $value as these change more frequently.
        """
        key = CacheKeys.submodel_element_value(submodel_b64, id_short_path)
        await self.client.setex(key, ttl or 300, value_bytes)  # 5 min default

    async def delete_element_value(self, submodel_b64: str, id_short_path: str) -> None:
        """Delete cached SubmodelElement $value."""
        key = CacheKeys.submodel_element_value(submodel_b64, id_short_path)
        await self.client.delete(key)

    # -------------------------------------------------------------------------
    # Bulk operations
    # -------------------------------------------------------------------------

    async def invalidate_submodel_elements(self, submodel_b64: str) -> int:
        """Invalidate all cached elements for a Submodel.

        Called when a Submodel is updated to ensure cache consistency.
        Returns the number of keys deleted.
        """
        pattern = f"{CacheKeys.PREFIX}:sm:{submodel_b64}:elem:*"
        deleted = 0

        # Use SCAN to avoid blocking on large keyspaces
        async for key in self.client.scan_iter(match=pattern):
            await self.client.delete(key)
            deleted += 1

        return deleted

    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            await cast(Awaitable[bool], self.client.ping())
            return True
        except Exception:
            return False
