"""Dashboard cache endpoints - Redis layer visualization and control.

Provides visibility into:
- Memory usage and eviction stats
- Cache hit/miss ratios
- Key browsing and inspection
- Pattern-based cache invalidation
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from titan.cache import get_redis
from titan.cache.keys import CacheKeys
from titan.security.deps import require_permission
from titan.security.rbac import Permission

if TYPE_CHECKING:
    from redis.asyncio import Redis

router = APIRouter(prefix="/cache", tags=["Dashboard - Cache"])

_PATTERN_PREFIX = f"{CacheKeys.PREFIX}:"
_MAX_PATTERN_LENGTH = 256


def _validate_pattern(pattern: str) -> str:
    """Validate and normalize cache key patterns.

    Only Titan namespace patterns are allowed to avoid accidental deletion
    of non-Titan keys.
    """
    cleaned = pattern.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Pattern must not be empty")
    if len(cleaned) > _MAX_PATTERN_LENGTH:
        raise HTTPException(status_code=400, detail="Pattern is too long")
    if not cleaned.startswith(_PATTERN_PREFIX):
        raise HTTPException(
            status_code=400,
            detail=f"Pattern must start with '{_PATTERN_PREFIX}'",
        )
    return cleaned


class MemoryStats(BaseModel):
    """Redis memory statistics."""

    used_memory: str
    used_memory_peak: str
    used_memory_rss: str | None = None
    maxmemory: str | None = None
    maxmemory_policy: str | None = None


class KeyspaceStats(BaseModel):
    """Redis keyspace statistics."""

    total_keys: int
    expires: int
    avg_ttl: float | None = None


class HitRatioStats(BaseModel):
    """Cache hit/miss ratio statistics."""

    hits: int
    misses: int
    hit_ratio: float


class CacheStats(BaseModel):
    """Complete cache statistics."""

    timestamp: datetime
    memory: MemoryStats
    keyspace: KeyspaceStats
    hit_ratio: HitRatioStats
    connected_clients: int
    uptime_seconds: int


class CacheKey(BaseModel):
    """Information about a cached key."""

    key: str
    type: str
    ttl: int  # -1 = no expiry, -2 = key doesn't exist
    size_bytes: int | None = None


class InvalidationResult(BaseModel):
    """Result of a cache invalidation operation."""

    pattern: str
    deleted_count: int
    timestamp: datetime


@router.get(
    "/stats",
    response_model=CacheStats,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_cache_stats() -> CacheStats:
    """Get comprehensive Redis cache statistics.

    Returns:
    - Memory usage (used, peak, RSS, max)
    - Keyspace stats (total keys, expires, avg TTL)
    - Hit/miss ratio
    - Connected clients count
    """
    redis: Redis = await get_redis()

    # Get memory info
    memory_info = await redis.info("memory")
    memory = MemoryStats(
        used_memory=memory_info.get("used_memory_human", "0B"),
        used_memory_peak=memory_info.get("used_memory_peak_human", "0B"),
        used_memory_rss=memory_info.get("used_memory_rss_human"),
        maxmemory=memory_info.get("maxmemory_human"),
        maxmemory_policy=memory_info.get("maxmemory_policy"),
    )

    # Get keyspace info
    keyspace_info = await redis.info("keyspace")
    db_info = keyspace_info.get("db0", {})
    if isinstance(db_info, dict):
        total_keys = db_info.get("keys", 0)
        expires = db_info.get("expires", 0)
        avg_ttl = db_info.get("avg_ttl")
    else:
        total_keys = 0
        expires = 0
        avg_ttl = None

    keyspace = KeyspaceStats(
        total_keys=total_keys,
        expires=expires,
        avg_ttl=avg_ttl,
    )

    # Get hit/miss stats
    stats_info = await redis.info("stats")
    hits = stats_info.get("keyspace_hits", 0)
    misses = stats_info.get("keyspace_misses", 0)
    total = hits + misses
    hit_ratio = round(hits / total, 4) if total > 0 else 0.0

    hit_ratio_stats = HitRatioStats(
        hits=hits,
        misses=misses,
        hit_ratio=hit_ratio,
    )

    # Get client info
    clients_info = await redis.info("clients")
    connected_clients = clients_info.get("connected_clients", 0)

    # Get server info for uptime
    server_info = await redis.info("server")
    uptime = server_info.get("uptime_in_seconds", 0)

    return CacheStats(
        timestamp=datetime.utcnow(),
        memory=memory,
        keyspace=keyspace,
        hit_ratio=hit_ratio_stats,
        connected_clients=connected_clients,
        uptime_seconds=uptime,
    )


@router.get(
    "/hit-ratio",
    response_model=HitRatioStats,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_hit_ratio() -> HitRatioStats:
    """Get cache hit/miss ratio.

    Returns current hit ratio as a percentage.
    """
    redis: Redis = await get_redis()
    stats_info = await redis.info("stats")
    hits = stats_info.get("keyspace_hits", 0)
    misses = stats_info.get("keyspace_misses", 0)
    total = hits + misses
    hit_ratio = round(hits / total, 4) if total > 0 else 0.0

    return HitRatioStats(
        hits=hits,
        misses=misses,
        hit_ratio=hit_ratio,
    )


@router.get(
    "/keys",
    response_model=list[CacheKey],
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def list_cache_keys(
    pattern: str = Query(default="titan:*", description="Key pattern to match"),
    limit: int = Query(default=100, le=1000, description="Maximum keys to return"),
) -> list[CacheKey]:
    """List cache keys matching a pattern.

    Uses SCAN to avoid blocking on large keyspaces.
    Returns key name, type, and TTL for each match.
    """
    redis: Redis = await get_redis()
    pattern = _validate_pattern(pattern)
    keys: list[CacheKey] = []

    async for key in redis.scan_iter(match=pattern, count=100):
        if len(keys) >= limit:
            break

        key_str = key.decode() if isinstance(key, bytes) else key
        key_type = await redis.type(key)
        type_str = key_type.decode() if isinstance(key_type, bytes) else key_type
        ttl = await redis.ttl(key)

        # Try to get size for string keys
        size_bytes = None
        if type_str == "string":
            try:
                size_bytes = await redis.strlen(key)
            except Exception:
                pass

        keys.append(
            CacheKey(
                key=key_str,
                type=type_str,
                ttl=ttl,
                size_bytes=size_bytes,
            )
        )

    return keys


@router.get(
    "/keys/{key_name:path}",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_cache_key_value(
    key_name: str,
) -> dict[str, Any]:
    """Get the value of a specific cache key.

    Returns the key value and metadata.
    Only works for string-type keys.
    """
    redis: Redis = await get_redis()

    key_type = await redis.type(key_name)
    type_str = key_type.decode() if isinstance(key_type, bytes) else key_type

    if type_str == "none":
        return {"error": "Key not found", "key": key_name}

    ttl = await redis.ttl(key_name)

    if type_str == "string":
        value = await redis.get(key_name)
        if isinstance(value, bytes):
            # Try to decode as UTF-8, otherwise show length
            try:
                decoded = value.decode("utf-8")
                # Truncate long values
                if len(decoded) > 10000:
                    decoded = decoded[:10000] + "... (truncated)"
                return {
                    "key": key_name,
                    "type": type_str,
                    "ttl": ttl,
                    "value": decoded,
                    "size_bytes": len(value),
                }
            except UnicodeDecodeError:
                return {
                    "key": key_name,
                    "type": type_str,
                    "ttl": ttl,
                    "value": f"<binary data: {len(value)} bytes>",
                    "size_bytes": len(value),
                }

    return {
        "key": key_name,
        "type": type_str,
        "ttl": ttl,
        "message": f"Cannot display value for type '{type_str}'",
    }


@router.delete(
    "/invalidate",
    response_model=InvalidationResult,
    dependencies=[Depends(require_permission(Permission.DELETE_AAS))],
)
async def invalidate_cache(
    pattern: str = Query(..., description="Key pattern to invalidate (e.g., 'titan:aas:*')"),
) -> InvalidationResult:
    """Invalidate cache keys matching a pattern.

    Uses SCAN to find matching keys and DEL to remove them.
    Returns the count of deleted keys.

    WARNING: This is a destructive operation.
    """
    redis: Redis = await get_redis()
    pattern = _validate_pattern(pattern)
    deleted = 0

    async for key in redis.scan_iter(match=pattern, count=100):
        await redis.delete(key)
        deleted += 1

    return InvalidationResult(
        pattern=pattern,
        deleted_count=deleted,
        timestamp=datetime.utcnow(),
    )


@router.delete(
    "/flush",
    response_model=InvalidationResult,
    dependencies=[Depends(require_permission(Permission.DELETE_AAS))],
)
async def flush_titan_cache() -> InvalidationResult:
    """Flush all Titan-AAS cache keys.

    Deletes all keys with the 'titan:' prefix.
    WARNING: This will clear all cached entities.
    """
    return await invalidate_cache(pattern="titan:*")
