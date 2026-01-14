"""Cache layer for Titan-AAS.

Provides Redis caching with the cache-aside pattern:
- Hot document cache stores doc_bytes for fast streaming reads
- Cache invalidation occurs on writes and TTL expiration
- TTL-based expiration for memory management
"""

from titan.cache.keys import CacheKeys
from titan.cache.redis import RedisCache, close_redis, get_redis

__all__ = [
    # Core cache
    "CacheKeys",
    "RedisCache",
    "get_redis",
    "close_redis",
]
