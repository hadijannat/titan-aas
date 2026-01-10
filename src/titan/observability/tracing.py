"""OpenTelemetry tracing for Titan-AAS.

Provides distributed tracing with OTLP export:
- Automatic request/response tracing
- Database query tracing
- Redis operation tracing
- Custom span creation

Usage:
    from titan.observability.tracing import get_tracer

    tracer = get_tracer(__name__)

    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("key", "value")
        ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from titan.config import settings

if TYPE_CHECKING:
    from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Global tracer provider
_tracer_provider: Any = None
_initialized = False


def setup_tracing() -> None:
    """Initialize OpenTelemetry tracing.

    Configures:
    - OTLP exporter (if endpoint configured)
    - Console exporter (for development)
    - Automatic instrumentation for FastAPI, SQLAlchemy, Redis
    """
    global _tracer_provider, _initialized

    if _initialized:
        return

    if not settings.enable_tracing:
        logger.info("Tracing is disabled")
        _initialized = True
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Create resource with service info
        resource = Resource.create(
            {
                "service.name": settings.app_name,
                "service.instance.id": settings.instance_id,
                "deployment.environment": settings.env,
            }
        )

        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)

        # Add OTLP exporter if endpoint configured
        if settings.otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                otlp_exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
                _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"OTLP tracing enabled: {settings.otlp_endpoint}")
            except ImportError:
                logger.warning(
                    "opentelemetry-exporter-otlp-proto-grpc not installed, "
                    "OTLP export disabled"
                )
        else:
            # Development: use console exporter
            if settings.env == "dev":
                try:
                    from opentelemetry.sdk.trace.export import (
                        ConsoleSpanExporter,
                        SimpleSpanProcessor,
                    )

                    console_exporter = ConsoleSpanExporter()
                    _tracer_provider.add_span_processor(
                        SimpleSpanProcessor(console_exporter)
                    )
                    logger.info("Console tracing enabled (dev mode)")
                except ImportError:
                    pass

        # Set global tracer provider
        trace.set_tracer_provider(_tracer_provider)

        # Auto-instrument common libraries
        _setup_auto_instrumentation()

        _initialized = True
        logger.info("OpenTelemetry tracing initialized")

    except ImportError as e:
        logger.warning(f"OpenTelemetry not available: {e}")
        _initialized = True


def _setup_auto_instrumentation() -> None:
    """Set up automatic instrumentation for common libraries."""
    # Instrument SQLAlchemy
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
        logger.debug("SQLAlchemy instrumentation enabled")
    except ImportError:
        pass

    # Instrument Redis
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.debug("Redis instrumentation enabled")
    except ImportError:
        pass

    # Instrument httpx (for OIDC validation)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logger.debug("httpx instrumentation enabled")
    except ImportError:
        pass


def get_tracer(name: str) -> Any:
    """Get a tracer for the given module name.

    Args:
        name: Module name (typically __name__)

    Returns:
        OpenTelemetry tracer or NoOpTracer if tracing disabled
    """
    if not settings.enable_tracing:
        return NoOpTracer()

    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return NoOpTracer()


class NoOpTracer:
    """No-op tracer for when OpenTelemetry is not available."""

    def start_as_current_span(
        self, name: str, **kwargs: Any
    ) -> "NoOpSpanContextManager":
        """Return a no-op span context manager."""
        return NoOpSpanContextManager()

    def start_span(self, name: str, **kwargs: Any) -> "NoOpSpan":
        """Return a no-op span."""
        return NoOpSpan()


class NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op."""
        pass

    def set_status(self, status: Any) -> None:
        """No-op."""
        pass

    def record_exception(self, exception: Exception) -> None:
        """No-op."""
        pass

    def end(self) -> None:
        """No-op."""
        pass


class NoOpSpanContextManager:
    """No-op span context manager."""

    def __enter__(self) -> NoOpSpan:
        return NoOpSpan()

    def __exit__(self, *args: Any) -> None:
        pass


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware for HTTP request tracing.

    Adds spans for each HTTP request with:
    - HTTP method and path
    - Status code
    - Request/response timing
    - Error information
    """

    def __init__(self, app: "ASGIApp") -> None:
        super().__init__(app)
        self.tracer = get_tracer("titan.api")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        """Trace HTTP requests."""
        # Skip tracing for health and metrics endpoints
        if request.url.path in ("/health", "/ready", "/metrics"):
            return await call_next(request)

        span_name = f"{request.method} {request.url.path}"

        with self.tracer.start_as_current_span(span_name) as span:
            # Set request attributes
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.route", request.url.path)
            span.set_attribute("http.scheme", request.url.scheme)

            if request.client:
                span.set_attribute("http.client_ip", request.client.host)

            # Get user info from request state if available
            user = getattr(request.state, "user", None)
            if user:
                span.set_attribute("user.id", user.sub)
                if user.email:
                    span.set_attribute("user.email", user.email)

            try:
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)

                # Set status based on response code
                if response.status_code >= 500:
                    try:
                        from opentelemetry.trace import StatusCode

                        span.set_status(StatusCode.ERROR)
                    except ImportError:
                        pass
                elif response.status_code >= 400:
                    span.set_attribute("http.error", True)

                return response

            except Exception as e:
                span.record_exception(e)
                try:
                    from opentelemetry.trace import StatusCode

                    span.set_status(StatusCode.ERROR, str(e))
                except ImportError:
                    pass
                raise


def shutdown_tracing() -> None:
    """Shutdown tracing and flush remaining spans."""
    global _tracer_provider, _initialized

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown complete")
        except Exception as e:
            logger.warning(f"Error shutting down tracing: {e}")

    _tracer_provider = None
    _initialized = False
