"""Observability module for Titan-AAS.

Provides tracing, metrics, and structured logging:
- OpenTelemetry tracing with OTLP export
- Prometheus metrics
- Request/response instrumentation
- JSON structured logging with correlation IDs
"""

from titan.observability.logging import (
    LogContext,
    configure_logging,
    correlation_id_var,
    get_logger,
    request_id_var,
)
from titan.observability.metrics import (
    MetricsMiddleware,
    get_metrics,
    metrics_registry,
)
from titan.observability.tracing import (
    TracingMiddleware,
    get_tracer,
    setup_tracing,
)

__all__ = [
    # Logging
    "configure_logging",
    "get_logger",
    "LogContext",
    "request_id_var",
    "correlation_id_var",
    # Tracing
    "setup_tracing",
    "get_tracer",
    "TracingMiddleware",
    # Metrics
    "metrics_registry",
    "get_metrics",
    "MetricsMiddleware",
]
