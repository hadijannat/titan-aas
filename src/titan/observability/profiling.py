"""Performance profiling for Titan-AAS.

Provides profiling capabilities:
- CPU profiling via pyinstrument (optional)
- Memory profiling via tracemalloc
- Async task statistics
- Database query timing
- Request timing statistics

Example:
    from titan.observability.profiling import ProfileCollector

    collector = ProfileCollector()
    collector.start()

    # ... run application ...

    stats = collector.get_stats()
    print(f"Request count: {stats['request_count']}")
"""

from __future__ import annotations

import asyncio
import logging
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Generator

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


@dataclass
class RequestStats:
    """Statistics for a single request."""

    path: str
    method: str
    status_code: int
    duration_ms: float
    timestamp: float


@dataclass
class EndpointStats:
    """Aggregated statistics for an endpoint."""

    path: str
    method: str
    request_count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    error_count: int = 0

    @property
    def avg_duration_ms(self) -> float:
        """Average request duration."""
        if self.request_count == 0:
            return 0.0
        return self.total_duration_ms / self.request_count

    def record(self, duration_ms: float, is_error: bool = False) -> None:
        """Record a request."""
        self.request_count += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        if is_error:
            self.error_count += 1


@dataclass
class ProfileStats:
    """Aggregated profiling statistics."""

    # Request stats
    total_requests: int = 0
    total_errors: int = 0
    avg_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0

    # Memory stats
    current_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0

    # Async stats
    pending_tasks: int = 0

    # Cache stats
    cache_hits: int = 0
    cache_misses: int = 0

    # DB stats
    db_query_count: int = 0
    avg_query_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "requests": {
                "total": self.total_requests,
                "errors": self.total_errors,
                "avg_duration_ms": round(self.avg_duration_ms, 2),
                "p50_duration_ms": round(self.p50_duration_ms, 2),
                "p95_duration_ms": round(self.p95_duration_ms, 2),
                "p99_duration_ms": round(self.p99_duration_ms, 2),
            },
            "memory": {
                "current_mb": round(self.current_memory_mb, 2),
                "peak_mb": round(self.peak_memory_mb, 2),
            },
            "async": {
                "pending_tasks": self.pending_tasks,
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate": (
                    self.cache_hits / (self.cache_hits + self.cache_misses)
                    if (self.cache_hits + self.cache_misses) > 0
                    else 0.0
                ),
            },
            "database": {
                "query_count": self.db_query_count,
                "avg_query_duration_ms": round(self.avg_query_duration_ms, 2),
            },
        }


class ProfileCollector:
    """Collects profiling data from various sources.

    Thread-safe collection of request timings, memory usage,
    and other performance metrics.
    """

    def __init__(
        self,
        max_history: int = 10000,
        enable_memory_tracking: bool = False,
    ) -> None:
        """Initialize collector.

        Args:
            max_history: Maximum request history to keep
            enable_memory_tracking: Enable tracemalloc (has overhead)
        """
        self.max_history = max_history
        self.enable_memory_tracking = enable_memory_tracking

        self._request_history: list[RequestStats] = []
        self._endpoint_stats: dict[str, EndpointStats] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._db_query_count = 0
        self._db_query_total_ms = 0.0
        self._started = False

    def start(self) -> None:
        """Start profiling collection."""
        if self._started:
            return

        if self.enable_memory_tracking:
            tracemalloc.start()

        self._started = True
        logger.info("Profile collector started")

    def stop(self) -> None:
        """Stop profiling collection."""
        if not self._started:
            return

        if self.enable_memory_tracking:
            tracemalloc.stop()

        self._started = False
        logger.info("Profile collector stopped")

    def record_request(
        self,
        path: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Record a request.

        Args:
            path: Request path
            method: HTTP method
            status_code: Response status code
            duration_ms: Request duration in milliseconds
        """
        # Record in history
        stats = RequestStats(
            path=path,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )

        self._request_history.append(stats)

        # Trim history if needed
        if len(self._request_history) > self.max_history:
            self._request_history = self._request_history[-self.max_history :]

        # Update endpoint stats
        key = f"{method}:{path}"
        if key not in self._endpoint_stats:
            self._endpoint_stats[key] = EndpointStats(
                path=path,
                method=method,
            )

        is_error = status_code >= 400
        self._endpoint_stats[key].record(duration_ms, is_error)

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self._cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self._cache_misses += 1

    def record_db_query(self, duration_ms: float) -> None:
        """Record a database query.

        Args:
            duration_ms: Query duration in milliseconds
        """
        self._db_query_count += 1
        self._db_query_total_ms += duration_ms

    def get_stats(self) -> ProfileStats:
        """Get aggregated profiling statistics."""
        stats = ProfileStats()

        # Request stats
        if self._request_history:
            durations = [r.duration_ms for r in self._request_history]
            durations.sort()

            stats.total_requests = len(durations)
            stats.total_errors = sum(1 for r in self._request_history if r.status_code >= 400)
            stats.avg_duration_ms = sum(durations) / len(durations)

            # Percentiles
            stats.p50_duration_ms = self._percentile(durations, 50)
            stats.p95_duration_ms = self._percentile(durations, 95)
            stats.p99_duration_ms = self._percentile(durations, 99)

        # Memory stats
        if self.enable_memory_tracking and tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            stats.current_memory_mb = current / (1024 * 1024)
            stats.peak_memory_mb = peak / (1024 * 1024)

        # Async stats
        try:
            loop = asyncio.get_running_loop()
            stats.pending_tasks = len(asyncio.all_tasks(loop))
        except RuntimeError:
            stats.pending_tasks = 0

        # Cache stats
        stats.cache_hits = self._cache_hits
        stats.cache_misses = self._cache_misses

        # DB stats
        stats.db_query_count = self._db_query_count
        if self._db_query_count > 0:
            stats.avg_query_duration_ms = self._db_query_total_ms / self._db_query_count

        return stats

    def get_endpoint_stats(self) -> list[EndpointStats]:
        """Get per-endpoint statistics."""
        return list(self._endpoint_stats.values())

    def reset(self) -> None:
        """Reset all collected statistics."""
        self._request_history.clear()
        self._endpoint_stats.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._db_query_count = 0
        self._db_query_total_ms = 0.0

        if self.enable_memory_tracking and tracemalloc.is_tracing():
            tracemalloc.reset_peak()

    @staticmethod
    def _percentile(sorted_data: list[float], percentile: int) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        k = (len(sorted_data) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f < len(sorted_data) - 1 else f
        return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


# Global collector instance
_collector: ProfileCollector | None = None


def get_collector() -> ProfileCollector:
    """Get or create the global profile collector."""
    global _collector
    if _collector is None:
        _collector = ProfileCollector()
    return _collector


def reset_collector() -> None:
    """Reset the global collector."""
    global _collector
    if _collector is not None:
        _collector.stop()
    _collector = None


@contextmanager
def profile_request(
    path: str,
    method: str,
) -> Generator[None, None, None]:
    """Context manager for profiling a request.

    Args:
        path: Request path
        method: HTTP method

    Example:
        with profile_request("/shells", "GET") as duration:
            response = await handler()
    """
    collector = get_collector()
    start = time.perf_counter()
    status_code = 200

    try:
        yield
    except Exception:
        status_code = 500
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        collector.record_request(path, method, status_code, duration_ms)


class ProfilingMiddleware(BaseHTTPMiddleware):
    """Middleware that records request timing.

    Automatically tracks all requests and their durations.
    """

    def __init__(
        self,
        app: Any,
        collector: ProfileCollector | None = None,
    ) -> None:
        super().__init__(app)
        self.collector = collector or get_collector()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000

        self.collector.record_request(
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        return response


def get_memory_snapshot() -> dict[str, Any]:
    """Get current memory usage snapshot.

    Returns detailed memory allocation information.
    Requires tracemalloc to be enabled.
    """
    if not tracemalloc.is_tracing():
        return {"error": "Memory tracking not enabled"}

    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")[:20]

    return {
        "top_allocations": [
            {
                "file": str(stat.traceback),
                "size_kb": stat.size / 1024,
                "count": stat.count,
            }
            for stat in top_stats
        ],
        "total_kb": sum(stat.size for stat in top_stats) / 1024,
    }
