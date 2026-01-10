"""API router for profiling endpoints.

Provides debug endpoints for:
- CPU profiling statistics
- Memory usage snapshots
- Request timing statistics
- Async task counts
- Database query statistics

These endpoints are intended for development/debugging only.
Do not expose in production without authentication.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from titan.observability.profiling import (
    get_collector,
    get_memory_snapshot,
)

router = APIRouter(prefix="/debug/profile", tags=["Debug"])


class ProfileStatsResponse(BaseModel):
    """Profiling statistics response."""

    requests: dict[str, Any]
    memory: dict[str, Any]
    async_: dict[str, Any]
    cache: dict[str, Any]
    database: dict[str, Any]

    class Config:
        populate_by_name = True

    @classmethod
    def from_stats(cls, stats: dict[str, Any]) -> ProfileStatsResponse:
        """Create from stats dict."""
        return cls(
            requests=stats.get("requests", {}),
            memory=stats.get("memory", {}),
            async_=stats.get("async", {}),
            cache=stats.get("cache", {}),
            database=stats.get("database", {}),
        )


class EndpointStatsResponse(BaseModel):
    """Per-endpoint statistics response."""

    path: str
    method: str
    request_count: int
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    error_count: int
    error_rate: float


class EndpointListResponse(BaseModel):
    """List of endpoint statistics."""

    endpoints: list[EndpointStatsResponse]
    count: int


class MemorySnapshotResponse(BaseModel):
    """Memory snapshot response."""

    top_allocations: list[dict[str, Any]]
    total_kb: float


@router.get("/stats", response_model=ProfileStatsResponse)
async def get_profile_stats() -> ProfileStatsResponse:
    """Get aggregated profiling statistics.

    Returns request timing, memory usage, cache hit rates,
    and database query statistics.
    """
    collector = get_collector()
    stats = collector.get_stats()
    return ProfileStatsResponse.from_stats(stats.to_dict())


@router.get("/endpoints", response_model=EndpointListResponse)
async def get_endpoint_stats(
    sort_by: str = Query(
        "request_count",
        description="Sort by: request_count, avg_duration_ms, error_count",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum endpoints to return"),
) -> EndpointListResponse:
    """Get per-endpoint statistics.

    Shows request counts, timing, and error rates for each endpoint.
    """
    collector = get_collector()
    endpoint_stats = collector.get_endpoint_stats()

    # Convert to response format
    endpoints = []
    for stat in endpoint_stats:
        error_rate = stat.error_count / stat.request_count if stat.request_count > 0 else 0.0
        endpoints.append(
            EndpointStatsResponse(
                path=stat.path,
                method=stat.method,
                request_count=stat.request_count,
                avg_duration_ms=round(stat.avg_duration_ms, 2),
                min_duration_ms=(
                    round(stat.min_duration_ms, 2) if stat.min_duration_ms != float("inf") else 0.0
                ),
                max_duration_ms=round(stat.max_duration_ms, 2),
                error_count=stat.error_count,
                error_rate=round(error_rate, 4),
            )
        )

    # Sort
    if sort_by == "avg_duration_ms":
        endpoints.sort(key=lambda e: e.avg_duration_ms, reverse=True)
    elif sort_by == "error_count":
        endpoints.sort(key=lambda e: e.error_count, reverse=True)
    else:
        endpoints.sort(key=lambda e: e.request_count, reverse=True)

    return EndpointListResponse(
        endpoints=endpoints[:limit],
        count=len(endpoints),
    )


@router.get("/memory")
async def get_memory_stats() -> dict[str, Any]:
    """Get memory usage snapshot.

    Returns top memory allocations if memory tracking is enabled.
    Enable with: collector.enable_memory_tracking = True
    """
    return get_memory_snapshot()


@router.post("/reset")
async def reset_stats() -> dict[str, str]:
    """Reset all profiling statistics.

    Clears request history, endpoint stats, and counters.
    """
    collector = get_collector()
    collector.reset()
    return {"status": "reset"}


@router.get("/async")
async def get_async_stats() -> dict[str, Any]:
    """Get async task statistics.

    Returns information about pending async tasks.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        tasks = asyncio.all_tasks(loop)

        task_info = []
        for task in list(tasks)[:50]:  # Limit to 50
            task_info.append(
                {
                    "name": task.get_name(),
                    "done": task.done(),
                    "cancelled": task.cancelled(),
                }
            )

        return {
            "total_tasks": len(tasks),
            "tasks": task_info,
        }
    except RuntimeError:
        return {"error": "No running event loop"}
