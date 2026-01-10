"""Tenant extraction middleware for FastAPI.

Extracts tenant information from requests:
- X-Tenant-ID header
- JWT claims
- Subdomain

Example:
    from fastapi import FastAPI
    from titan.tenancy.middleware import TenantMiddleware

    app = FastAPI()
    app.add_middleware(TenantMiddleware)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from titan.tenancy.context import (
    TenantContext,
    clear_tenant,
    set_tenant_context,
)

logger = logging.getLogger(__name__)


class TenantExtractionError(Exception):
    """Raised when tenant cannot be extracted from request."""

    pass


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware that extracts tenant from incoming requests.

    Extraction order:
    1. X-Tenant-ID header
    2. JWT token claim
    3. Subdomain (e.g., acme.titan.example.com)

    The middleware sets the tenant context for the request scope.
    """

    def __init__(
        self,
        app: Any,
        header_name: str = "X-Tenant-ID",
        jwt_claim: str = "tenant_id",
        allow_subdomain: bool = False,
        require_tenant: bool = False,
        default_tenant: str | None = None,
        excluded_paths: list[str] | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: The ASGI application
            header_name: Header to check for tenant ID
            jwt_claim: JWT claim name for tenant ID
            allow_subdomain: Extract tenant from subdomain
            require_tenant: Require tenant on all requests
            default_tenant: Default tenant if none found
            excluded_paths: Paths to exclude from tenant check
        """
        super().__init__(app)
        self.header_name = header_name
        self.jwt_claim = jwt_claim
        self.allow_subdomain = allow_subdomain
        self.require_tenant = require_tenant
        self.default_tenant = default_tenant
        self.excluded_paths = excluded_paths or [
            "/health",
            "/ready",
            "/metrics",
            "/docs",
            "/openapi.json",
        ]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and extract tenant.

        Args:
            request: Incoming request
            call_next: Next handler in chain

        Returns:
            Response from the handler
        """
        # Skip tenant extraction for excluded paths
        if self._is_excluded(request.url.path):
            return await call_next(request)

        try:
            tenant_id = await self._extract_tenant(request)

            if tenant_id:
                ctx = TenantContext(
                    tenant_id=tenant_id,
                    metadata={"source": self._get_extraction_source(request)},
                )
                set_tenant_context(ctx)
                logger.debug(f"Set tenant context: {tenant_id}")
            elif self.require_tenant:
                return Response(
                    content='{"error": "Tenant ID required"}',
                    status_code=400,
                    media_type="application/json",
                )
            elif self.default_tenant:
                ctx = TenantContext(
                    tenant_id=self.default_tenant,
                    metadata={"source": "default"},
                )
                set_tenant_context(ctx)

            response = await call_next(request)
            return response

        except TenantExtractionError as e:
            logger.warning(f"Tenant extraction failed: {e}")
            return Response(
                content=f'{{"error": "Tenant extraction failed: {e}"}}',
                status_code=400,
                media_type="application/json",
            )
        finally:
            clear_tenant()

    def _is_excluded(self, path: str) -> bool:
        """Check if path is excluded from tenant check.

        Args:
            path: Request path

        Returns:
            True if excluded
        """
        return any(path.startswith(excluded) for excluded in self.excluded_paths)

    async def _extract_tenant(self, request: Request) -> str | None:
        """Extract tenant from request.

        Args:
            request: Incoming request

        Returns:
            Tenant ID or None
        """
        # Try header first
        tenant_id = self._extract_from_header(request)
        if tenant_id:
            return tenant_id

        # Try JWT claim
        tenant_id = self._extract_from_jwt(request)
        if tenant_id:
            return tenant_id

        # Try subdomain
        if self.allow_subdomain:
            tenant_id = self._extract_from_subdomain(request)
            if tenant_id:
                return tenant_id

        return None

    def _extract_from_header(self, request: Request) -> str | None:
        """Extract tenant from header.

        Args:
            request: Incoming request

        Returns:
            Tenant ID or None
        """
        return request.headers.get(self.header_name)

    def _extract_from_jwt(self, request: Request) -> str | None:
        """Extract tenant from JWT token.

        Args:
            request: Incoming request

        Returns:
            Tenant ID or None
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        # Get user from request state if already validated
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "claims"):
            return user.claims.get(self.jwt_claim)

        return None

    def _extract_from_subdomain(self, request: Request) -> str | None:
        """Extract tenant from subdomain.

        E.g., acme.titan.example.com -> acme

        Args:
            request: Incoming request

        Returns:
            Tenant ID or None
        """
        host = request.headers.get("Host", "")
        parts = host.split(".")

        # Need at least 3 parts: subdomain.domain.tld
        if len(parts) >= 3:
            subdomain = parts[0]
            # Skip common prefixes
            if subdomain not in ("www", "api", "app"):
                return subdomain

        return None

    def _get_extraction_source(self, request: Request) -> str:
        """Determine where tenant was extracted from.

        Args:
            request: Incoming request

        Returns:
            Source name (header, jwt, subdomain, or unknown)
        """
        if request.headers.get(self.header_name):
            return "header"

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return "jwt"

        if self.allow_subdomain:
            host = request.headers.get("Host", "")
            if len(host.split(".")) >= 3:
                return "subdomain"

        return "unknown"


def get_tenant_from_request(request: Request) -> str | None:
    """Helper function to get tenant from request directly.

    Args:
        request: FastAPI request object

    Returns:
        Tenant ID or None
    """
    # Check header
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return tenant_id

    # Check state (set by middleware)
    if hasattr(request.state, "tenant_id"):
        return request.state.tenant_id

    return None
