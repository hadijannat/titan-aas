"""Observability module for Titan-AAS.

Provides tracing and metrics:
- OpenTelemetry tracing with OTLP export
- Prometheus metrics
- Request/response instrumentation
"""

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
    # Tracing
    "setup_tracing",
    "get_tracer",
    "TracingMiddleware",
    # Metrics
    "metrics_registry",
    "get_metrics",
    "MetricsMiddleware",
]
