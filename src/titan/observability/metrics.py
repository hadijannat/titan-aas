"""Prometheus metrics for Titan-AAS.

Provides metrics collection and exposure:
- HTTP request metrics (latency, count, errors)
- Database metrics (query time, connections)
- Cache metrics (hits, misses, latency)
- Business metrics (AAS count, submodel count)

Usage:
    from titan.observability.metrics import get_metrics

    metrics = get_metrics()
    metrics.http_requests_total.labels(method="GET", path="/shells", status=200).inc()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from titan.config import settings

if TYPE_CHECKING:
    from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


@dataclass
class MetricsRegistry:
    """Registry for Prometheus metrics."""

    # HTTP metrics
    http_requests_total: Any = None
    http_request_duration_seconds: Any = None
    http_requests_in_progress: Any = None

    # Database metrics
    db_query_duration_seconds: Any = None
    db_connections_active: Any = None

    # Cache metrics
    cache_hits_total: Any = None
    cache_misses_total: Any = None
    cache_operation_duration_seconds: Any = None

    # Business metrics
    aas_total: Any = None
    submodels_total: Any = None
    events_published_total: Any = None

    # Internal state
    _initialized: bool = field(default=False, repr=False)
    _registry: Any = field(default=None, repr=False)

    def initialize(self) -> None:
        """Initialize Prometheus metrics."""
        if self._initialized:
            return

        if not settings.enable_metrics:
            logger.info("Metrics are disabled")
            self._initialized = True
            return

        try:
            from prometheus_client import (
                REGISTRY,
                Counter,
                Gauge,
                Histogram,
            )

            self._registry = REGISTRY

            # HTTP metrics
            self.http_requests_total = Counter(
                "titan_http_requests_total",
                "Total HTTP requests",
                ["method", "path", "status"],
            )

            self.http_request_duration_seconds = Histogram(
                "titan_http_request_duration_seconds",
                "HTTP request latency in seconds",
                ["method", "path"],
                buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
            )

            self.http_requests_in_progress = Gauge(
                "titan_http_requests_in_progress",
                "HTTP requests currently in progress",
                ["method"],
            )

            # Database metrics
            self.db_query_duration_seconds = Histogram(
                "titan_db_query_duration_seconds",
                "Database query latency in seconds",
                ["operation", "table"],
                buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            )

            self.db_connections_active = Gauge(
                "titan_db_connections_active",
                "Active database connections",
            )

            # Cache metrics
            self.cache_hits_total = Counter(
                "titan_cache_hits_total",
                "Cache hits",
                ["cache_type"],
            )

            self.cache_misses_total = Counter(
                "titan_cache_misses_total",
                "Cache misses",
                ["cache_type"],
            )

            self.cache_operation_duration_seconds = Histogram(
                "titan_cache_operation_duration_seconds",
                "Cache operation latency in seconds",
                ["operation", "cache_type"],
                buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05),
            )

            # Business metrics
            self.aas_total = Gauge(
                "titan_aas_total",
                "Total Asset Administration Shells",
            )

            self.submodels_total = Gauge(
                "titan_submodels_total",
                "Total Submodels",
            )

            self.events_published_total = Counter(
                "titan_events_published_total",
                "Total events published",
                ["event_type", "entity_type"],
            )

            self._initialized = True
            logger.info("Prometheus metrics initialized")

        except ImportError:
            logger.warning("prometheus_client not installed, metrics disabled")
            self._initialized = True

    def generate_latest(self) -> bytes:
        """Generate Prometheus metrics in exposition format."""
        if not settings.enable_metrics or self._registry is None:
            return b"# Metrics disabled\n"

        try:
            from prometheus_client import generate_latest

            return generate_latest(self._registry)
        except ImportError:
            return b"# prometheus_client not installed\n"


# Global metrics registry
metrics_registry = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    """Get the global metrics registry.

    Initializes metrics on first access.
    """
    if not metrics_registry._initialized:
        metrics_registry.initialize()
    return metrics_registry


class NoOpMetric:
    """No-op metric for when metrics are disabled."""

    def labels(self, **kwargs: Any) -> "NoOpMetric":
        """Return self for chaining."""
        return self

    def inc(self, amount: float = 1) -> None:
        """No-op."""
        pass

    def dec(self, amount: float = 1) -> None:
        """No-op."""
        pass

    def set(self, value: float) -> None:
        """No-op."""
        pass

    def observe(self, value: float) -> None:
        """No-op."""
        pass


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for HTTP request metrics.

    Records:
    - Request count by method, path, status
    - Request duration histogram
    - Requests in progress gauge
    """

    def __init__(self, app: "ASGIApp") -> None:
        super().__init__(app)
        self.metrics = get_metrics()

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Record metrics for HTTP requests."""
        # Skip metrics for health and metrics endpoints
        if request.url.path in ("/health", "/ready", "/metrics"):
            return await call_next(request)

        method = request.method
        path = self._normalize_path(request.url.path)

        # Track in-progress requests
        if self.metrics.http_requests_in_progress:
            self.metrics.http_requests_in_progress.labels(method=method).inc()

        start_time = time.perf_counter()
        status_code = 500  # Default in case of exception

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start_time

            # Record request count
            if self.metrics.http_requests_total:
                self.metrics.http_requests_total.labels(
                    method=method,
                    path=path,
                    status=status_code,
                ).inc()

            # Record duration
            if self.metrics.http_request_duration_seconds:
                self.metrics.http_request_duration_seconds.labels(
                    method=method,
                    path=path,
                ).observe(duration)

            # Decrease in-progress
            if self.metrics.http_requests_in_progress:
                self.metrics.http_requests_in_progress.labels(method=method).dec()

    def _normalize_path(self, path: str) -> str:
        """Normalize path by replacing IDs with placeholders.

        This prevents high cardinality in metrics.

        Examples:
            /shells/abc123 -> /shells/{id}
            /submodels/xyz/submodel-elements/foo -> /submodels/{id}/submodel-elements/{path}
        """
        parts = path.strip("/").split("/")
        normalized = []

        # Path patterns with their expected structure
        # We replace the identifier segments with placeholders
        i = 0
        while i < len(parts):
            part = parts[i]

            if part in ("shells", "submodels"):
                normalized.append(part)
                # Next part is likely an identifier
                if i + 1 < len(parts) and parts[i + 1] not in (
                    "shells",
                    "submodels",
                    "submodel-elements",
                    "shell-descriptors",
                    "submodel-descriptors",
                ):
                    normalized.append("{id}")
                    i += 1
            elif part == "submodel-elements":
                normalized.append(part)
                # Remaining parts are the idShortPath
                if i + 1 < len(parts):
                    normalized.append("{path}")
                    break
            elif part in (
                "shell-descriptors",
                "submodel-descriptors",
                "lookup",
                "events",
            ):
                normalized.append(part)
            else:
                # Other paths, keep as-is for known endpoints
                normalized.append(part)

            i += 1

        return "/" + "/".join(normalized) if normalized else path


def record_db_query(operation: str, table: str, duration: float) -> None:
    """Record database query metrics.

    Args:
        operation: Query operation (select, insert, update, delete)
        table: Table name
        duration: Query duration in seconds
    """
    metrics = get_metrics()
    if metrics.db_query_duration_seconds:
        metrics.db_query_duration_seconds.labels(
            operation=operation,
            table=table,
        ).observe(duration)


def record_cache_hit(cache_type: str = "redis") -> None:
    """Record cache hit."""
    metrics = get_metrics()
    if metrics.cache_hits_total:
        metrics.cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str = "redis") -> None:
    """Record cache miss."""
    metrics = get_metrics()
    if metrics.cache_misses_total:
        metrics.cache_misses_total.labels(cache_type=cache_type).inc()


def record_cache_operation(operation: str, duration: float, cache_type: str = "redis") -> None:
    """Record cache operation duration.

    Args:
        operation: Cache operation (get, set, delete)
        duration: Operation duration in seconds
        cache_type: Type of cache (redis, memory)
    """
    metrics = get_metrics()
    if metrics.cache_operation_duration_seconds:
        metrics.cache_operation_duration_seconds.labels(
            operation=operation,
            cache_type=cache_type,
        ).observe(duration)


def record_event_published(event_type: str, entity_type: str) -> None:
    """Record event publication.

    Args:
        event_type: Type of event (created, updated, deleted)
        entity_type: Type of entity (aas, submodel)
    """
    metrics = get_metrics()
    if metrics.events_published_total:
        metrics.events_published_total.labels(
            event_type=event_type,
            entity_type=entity_type,
        ).inc()
