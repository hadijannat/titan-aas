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
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

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

    # MQTT metrics
    mqtt_messages_published_total: Any = None
    mqtt_publish_errors_total: Any = None
    mqtt_messages_received_total: Any = None
    mqtt_processing_errors_total: Any = None
    mqtt_connection_state: Any = None

    # OPC-UA metrics
    opcua_reads_total: Any = None
    opcua_writes_total: Any = None
    opcua_read_errors_total: Any = None
    opcua_write_errors_total: Any = None
    opcua_connection_state: Any = None

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

            # MQTT metrics
            self.mqtt_messages_published_total = Counter(
                "titan_mqtt_messages_published_total",
                "Total MQTT messages published",
                ["topic_prefix"],
            )

            self.mqtt_publish_errors_total = Counter(
                "titan_mqtt_publish_errors_total",
                "Total MQTT publish errors",
                ["topic_prefix"],
            )

            self.mqtt_messages_received_total = Counter(
                "titan_mqtt_messages_received_total",
                "Total MQTT messages received",
                ["topic_pattern"],
            )

            self.mqtt_processing_errors_total = Counter(
                "titan_mqtt_processing_errors_total",
                "Total MQTT message processing errors",
                ["topic_pattern"],
            )

            self.mqtt_connection_state = Gauge(
                "titan_mqtt_connection_state",
                "MQTT connection state (0=disconnected, 1=connecting, 2=connected, "
                "3=reconnecting, 4=failed)",
                ["broker"],
            )

            # OPC-UA metrics
            self.opcua_reads_total = Counter(
                "titan_opcua_reads_total",
                "Total OPC-UA node reads",
                ["endpoint"],
            )

            self.opcua_writes_total = Counter(
                "titan_opcua_writes_total",
                "Total OPC-UA node writes",
                ["endpoint"],
            )

            self.opcua_read_errors_total = Counter(
                "titan_opcua_read_errors_total",
                "Total OPC-UA read errors",
                ["endpoint"],
            )

            self.opcua_write_errors_total = Counter(
                "titan_opcua_write_errors_total",
                "Total OPC-UA write errors",
                ["endpoint"],
            )

            self.opcua_connection_state = Gauge(
                "titan_opcua_connection_state",
                "OPC-UA connection state (0=disconnected, 1=connecting, 2=connected, "
                "3=reconnecting, 4=failed)",
                ["endpoint"],
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

    def labels(self, **kwargs: Any) -> NoOpMetric:
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

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.metrics = get_metrics()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
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


def record_mqtt_message_published(topic_prefix: str = "titan") -> None:
    """Record MQTT message publication.

    Args:
        topic_prefix: Topic prefix for the message (e.g., "titan")
    """
    metrics = get_metrics()
    if metrics.mqtt_messages_published_total:
        metrics.mqtt_messages_published_total.labels(topic_prefix=topic_prefix).inc()


def record_mqtt_publish_error(topic_prefix: str = "titan") -> None:
    """Record MQTT publish error.

    Args:
        topic_prefix: Topic prefix for the message
    """
    metrics = get_metrics()
    if metrics.mqtt_publish_errors_total:
        metrics.mqtt_publish_errors_total.labels(topic_prefix=topic_prefix).inc()


def record_mqtt_message_received(topic_pattern: str = "titan/#") -> None:
    """Record MQTT message received.

    Args:
        topic_pattern: Topic pattern for categorization
    """
    metrics = get_metrics()
    if metrics.mqtt_messages_received_total:
        metrics.mqtt_messages_received_total.labels(topic_pattern=topic_pattern).inc()


def record_mqtt_processing_error(topic_pattern: str = "titan/#") -> None:
    """Record MQTT message processing error.

    Args:
        topic_pattern: Topic pattern for categorization
    """
    metrics = get_metrics()
    if metrics.mqtt_processing_errors_total:
        metrics.mqtt_processing_errors_total.labels(topic_pattern=topic_pattern).inc()


def set_mqtt_connection_state(broker: str, state: int) -> None:
    """Set MQTT connection state.

    Args:
        broker: MQTT broker hostname
        state: Connection state (0=disconnected, 1=connecting, 2=connected,
               3=reconnecting, 4=failed)
    """
    metrics = get_metrics()
    if metrics.mqtt_connection_state:
        metrics.mqtt_connection_state.labels(broker=broker).set(state)


# -----------------------------------------------------------------------------
# OPC-UA Metrics Helper Functions
# -----------------------------------------------------------------------------


def record_opcua_read(endpoint: str) -> None:
    """Record OPC-UA node read.

    Args:
        endpoint: OPC-UA server endpoint
    """
    metrics = get_metrics()
    if metrics.opcua_reads_total:
        metrics.opcua_reads_total.labels(endpoint=endpoint).inc()


def record_opcua_write(endpoint: str) -> None:
    """Record OPC-UA node write.

    Args:
        endpoint: OPC-UA server endpoint
    """
    metrics = get_metrics()
    if metrics.opcua_writes_total:
        metrics.opcua_writes_total.labels(endpoint=endpoint).inc()


def record_opcua_read_error(endpoint: str) -> None:
    """Record OPC-UA read error.

    Args:
        endpoint: OPC-UA server endpoint
    """
    metrics = get_metrics()
    if metrics.opcua_read_errors_total:
        metrics.opcua_read_errors_total.labels(endpoint=endpoint).inc()


def record_opcua_write_error(endpoint: str) -> None:
    """Record OPC-UA write error.

    Args:
        endpoint: OPC-UA server endpoint
    """
    metrics = get_metrics()
    if metrics.opcua_write_errors_total:
        metrics.opcua_write_errors_total.labels(endpoint=endpoint).inc()


def set_opcua_connection_state(endpoint: str, state: int) -> None:
    """Set OPC-UA connection state.

    Args:
        endpoint: OPC-UA server endpoint
        state: Connection state (0=disconnected, 1=connecting, 2=connected,
               3=reconnecting, 4=failed)
    """
    metrics = get_metrics()
    if metrics.opcua_connection_state:
        metrics.opcua_connection_state.labels(endpoint=endpoint).set(state)
