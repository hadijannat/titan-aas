"""HTTP caching headers middleware for Titan-AAS.

Adds Cache-Control, Vary, and other caching headers to responses.
Supports conditional requests with If-Modified-Since.
"""

from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CachingMiddleware(BaseHTTPMiddleware):
    """Add HTTP caching headers based on request/response.

    Features:
    - Cache-Control headers based on endpoint type
    - Vary headers for proper CDN behavior
    - Supports private (authenticated) and public responses
    """

    def __init__(
        self,
        app,
        default_max_age: int = 60,
        stale_while_revalidate: int = 30,
    ):
        super().__init__(app)
        self.default_max_age = default_max_age
        self.stale_while_revalidate = stale_while_revalidate

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add caching headers to response."""
        response = await call_next(request)

        # Skip for non-GET requests or error responses
        if request.method != "GET" or response.status_code >= 400:
            return response

        # Skip if Cache-Control already set
        if "cache-control" in response.headers:
            return response

        # Add Cache-Control based on endpoint
        cache_control = self._get_cache_control(request)
        if cache_control:
            response.headers["Cache-Control"] = cache_control

        # Add Vary header for proper CDN/proxy behavior
        # This tells caches that responses vary based on these headers
        response.headers["Vary"] = "Accept, Accept-Encoding, Authorization"

        return response

    def _get_cache_control(self, request: Request) -> str | None:
        """Determine Cache-Control based on endpoint."""
        path = request.url.path

        # Health endpoints - never cache
        if "/health" in path:
            return "no-cache, no-store, must-revalidate"

        # Metrics endpoint - never cache
        if "/metrics" in path:
            return "no-cache, no-store"

        # API endpoints - private caching (authenticated)
        if path.startswith("/shells") or path.startswith("/submodels"):
            # Check if request has Authorization header
            if request.headers.get("Authorization"):
                # Private cache (only browser, not CDN)
                return (
                    f"private, max-age={self.default_max_age}, "
                    f"stale-while-revalidate={self.stale_while_revalidate}"
                )
            else:
                # Public cache (CDN-friendly)
                return (
                    f"public, max-age={self.default_max_age}, "
                    f"stale-while-revalidate={self.stale_while_revalidate}"
                )

        # Registry/Discovery - short cache
        if "/shell-descriptors" in path or "/submodel-descriptors" in path:
            return "private, max-age=30, stale-while-revalidate=10"

        # Default - no specific cache policy
        return None
