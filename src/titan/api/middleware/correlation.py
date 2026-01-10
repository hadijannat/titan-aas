"""Correlation context middleware for request tracing.

Propagates correlation IDs and request context to logging and tracing systems.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from titan.observability.logging import (
    correlation_id_var,
    request_id_var,
)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware for propagating correlation context.

    Extracts or generates correlation IDs and propagates them to:
    - Request state (for use in handlers)
    - Context variables (for logging)
    - Response headers (for client correlation)

    Headers:
    - x-request-id: Unique ID for this request
    - x-correlation-id: ID for tracking across services (passed through)
    - x-b3-traceid: OpenTelemetry/Zipkin trace ID (passed through)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Extract and propagate correlation context."""
        # Extract or generate request ID
        request_id = (
            request.headers.get("x-request-id")
            or request.headers.get("x-amzn-requestid")  # AWS ALB
            or str(uuid.uuid4())
        )

        # Extract or inherit correlation ID
        correlation_id = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-correlationid")  # Alternate format
            or request_id  # Fall back to request ID
        )

        # Set context variables for logging
        request_token = request_id_var.set(request_id)
        correlation_token = correlation_id_var.set(correlation_id)

        try:
            # Store in request state for handlers
            request.state.request_id = request_id
            request.state.correlation_id = correlation_id

            # Process request
            response = await call_next(request)

            # Add correlation headers to response
            response.headers["x-request-id"] = request_id
            response.headers["x-correlation-id"] = correlation_id

            # Add trace ID if OpenTelemetry is active
            try:
                from opentelemetry import trace

                span = trace.get_current_span()
                span_context = span.get_span_context()
                if span_context.is_valid:
                    response.headers["x-trace-id"] = format(span_context.trace_id, "032x")
            except ImportError:
                pass

            return response

        finally:
            # Reset context variables
            request_id_var.reset(request_token)
            correlation_id_var.reset(correlation_token)


async def correlation_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Functional middleware for correlation context.

    Alternative to CorrelationMiddleware for simpler integration.
    """
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    correlation_id = request.headers.get("x-correlation-id") or request_id

    # Set context variables
    request_token = request_id_var.set(request_id)
    correlation_token = correlation_id_var.set(correlation_id)

    try:
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        response = await call_next(request)

        response.headers["x-request-id"] = request_id
        response.headers["x-correlation-id"] = correlation_id

        return response
    finally:
        request_id_var.reset(request_token)
        correlation_id_var.reset(correlation_token)
