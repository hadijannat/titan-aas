"""Cache layer for Titan-AAS.

Provides Redis caching with the cache-aside pattern:
- Hot document cache stores doc_bytes for fast streaming reads
- Cache invalidation via events ensures consistency
- TTL-based expiration for memory management
"""

from titan.cache.keys import CacheKeys
from titan.cache.redis import RedisCache, get_redis, close_redis

__all__ = [
    "CacheKeys",
    "RedisCache",
    "get_redis",
    "close_redis",
]
