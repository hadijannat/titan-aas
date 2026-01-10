"""Security headers middleware for Titan-AAS.

Adds security headers to all responses per OWASP recommendations:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Referrer-Policy: strict-origin-when-cross-origin
- Strict-Transport-Security (HSTS) - optional
- Content-Security-Policy (CSP) - optional
- Permissions-Policy - optional
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses.

    Args:
        app: The ASGI application
        enable_hsts: Whether to add HSTS header (should only be enabled with HTTPS)
        hsts_max_age: Max-age for HSTS in seconds (default: 1 year)
        hsts_include_subdomains: Include subdomains in HSTS
        hsts_preload: Add preload directive to HSTS
        csp_policy: Content-Security-Policy value (None to disable)
        permissions_policy: Permissions-Policy value (None to disable)
        x_frame_options: X-Frame-Options value (default: DENY)
        referrer_policy: Referrer-Policy value
    """

    def __init__(
        self,
        app,
        enable_hsts: bool = False,
        hsts_max_age: int = 31536000,  # 1 year
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = False,
        csp_policy: str | None = None,
        permissions_policy: str | None = None,
        x_frame_options: str = "DENY",
        referrer_policy: str = "strict-origin-when-cross-origin",
    ):
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
        self.csp_policy = csp_policy
        self.permissions_policy = permissions_policy
        self.x_frame_options = x_frame_options
        self.referrer_policy = referrer_policy

        # Pre-compute HSTS header value
        if self.enable_hsts:
            hsts_parts = [f"max-age={self.hsts_max_age}"]
            if self.hsts_include_subdomains:
                hsts_parts.append("includeSubDomains")
            if self.hsts_preload:
                hsts_parts.append("preload")
            self._hsts_value = "; ".join(hsts_parts)
        else:
            self._hsts_value = None

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Add security headers to the response."""
        response = await call_next(request)

        # Always add these headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = self.x_frame_options
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = self.referrer_policy

        # Optional HSTS (only enable with HTTPS)
        if self._hsts_value:
            response.headers["Strict-Transport-Security"] = self._hsts_value

        # Optional Content-Security-Policy
        if self.csp_policy:
            response.headers["Content-Security-Policy"] = self.csp_policy

        # Optional Permissions-Policy
        if self.permissions_policy:
            response.headers["Permissions-Policy"] = self.permissions_policy

        return response


# Default CSP for API-only applications
DEFAULT_API_CSP = "default-src 'none'; frame-ancestors 'none'"

# Permissive CSP for Swagger UI (allows inline scripts/styles for docs)
SWAGGER_UI_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "frame-ancestors 'none'"
)
