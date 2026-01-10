"""Cache layer for Titan-AAS.

Provides Redis caching with the cache-aside pattern:
- Hot document cache stores doc_bytes for fast streaming reads
- Cache invalidation via events ensures consistency
- TTL-based expiration for memory management
- Distributed cache invalidation for horizontal scaling
"""

from titan.cache.invalidation import (
    CacheInvalidationBroadcaster,
    InvalidationMessage,
    InvalidationType,
    LocalCacheInvalidator,
    get_invalidation_broadcaster,
    start_cache_invalidation,
    stop_cache_invalidation,
)
from titan.cache.keys import CacheKeys
from titan.cache.redis import RedisCache, close_redis, get_redis

__all__ = [
    # Core cache
    "CacheKeys",
    "RedisCache",
    "get_redis",
    "close_redis",
    # Distributed invalidation
    "CacheInvalidationBroadcaster",
    "InvalidationMessage",
    "InvalidationType",
    "LocalCacheInvalidator",
    "get_invalidation_broadcaster",
    "start_cache_invalidation",
    "stop_cache_invalidation",
]
