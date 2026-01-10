"""Tests for security headers middleware.

Tests OWASP-recommended security headers:
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Referrer-Policy
- Strict-Transport-Security (optional)
- Content-Security-Policy (optional)
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from titan.api.middleware.security_headers import (
    DEFAULT_API_CSP,
    SWAGGER_UI_CSP,
    SecurityHeadersMiddleware,
)


@pytest.fixture
def app() -> FastAPI:
    """Create a basic FastAPI app for testing."""
    app = FastAPI()

    @app.get("/test")
    def test_endpoint():
        return {"message": "ok"}

    return app


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    def test_default_headers_added(self, app: FastAPI) -> None:
        """Default security headers are added to all responses."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)

        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_hsts_disabled_by_default(self, app: FastAPI) -> None:
        """HSTS is not added when disabled (default)."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)

        response = client.get("/test")

        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_enabled(self, app: FastAPI) -> None:
        """HSTS header is added when enabled."""
        app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)
        client = TestClient(app)

        response = client.get("/test")

        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_hsts_custom_max_age(self, app: FastAPI) -> None:
        """HSTS max-age can be customized."""
        app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True, hsts_max_age=86400)
        client = TestClient(app)

        response = client.get("/test")

        assert "max-age=86400" in response.headers["Strict-Transport-Security"]

    def test_hsts_without_subdomains(self, app: FastAPI) -> None:
        """HSTS can exclude subdomains."""
        app.add_middleware(
            SecurityHeadersMiddleware, enable_hsts=True, hsts_include_subdomains=False
        )
        client = TestClient(app)

        response = client.get("/test")

        hsts = response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" not in hsts

    def test_hsts_with_preload(self, app: FastAPI) -> None:
        """HSTS can include preload directive."""
        app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True, hsts_preload=True)
        client = TestClient(app)

        response = client.get("/test")

        hsts = response.headers["Strict-Transport-Security"]
        assert "preload" in hsts

    def test_csp_not_added_by_default(self, app: FastAPI) -> None:
        """CSP is not added when not configured."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)

        response = client.get("/test")

        assert "Content-Security-Policy" not in response.headers

    def test_csp_custom_policy(self, app: FastAPI) -> None:
        """Custom CSP policy is added."""
        csp = "default-src 'self'"
        app.add_middleware(SecurityHeadersMiddleware, csp_policy=csp)
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["Content-Security-Policy"] == csp

    def test_permissions_policy(self, app: FastAPI) -> None:
        """Permissions-Policy is added when configured."""
        policy = "geolocation=(), microphone=()"
        app.add_middleware(SecurityHeadersMiddleware, permissions_policy=policy)
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["Permissions-Policy"] == policy

    def test_custom_x_frame_options(self, app: FastAPI) -> None:
        """X-Frame-Options can be customized."""
        app.add_middleware(SecurityHeadersMiddleware, x_frame_options="SAMEORIGIN")
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    def test_custom_referrer_policy(self, app: FastAPI) -> None:
        """Referrer-Policy can be customized."""
        app.add_middleware(SecurityHeadersMiddleware, referrer_policy="no-referrer")
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["Referrer-Policy"] == "no-referrer"


class TestCSPPresets:
    """Tests for CSP preset values."""

    def test_default_api_csp(self) -> None:
        """Default API CSP is restrictive."""
        assert "default-src 'none'" in DEFAULT_API_CSP
        assert "frame-ancestors 'none'" in DEFAULT_API_CSP

    def test_swagger_ui_csp_allows_scripts(self) -> None:
        """Swagger UI CSP allows necessary scripts."""
        assert "script-src" in SWAGGER_UI_CSP
        assert "cdn.jsdelivr.net" in SWAGGER_UI_CSP


class TestHeadersOn404:
    """Test that security headers are added even on error responses."""

    def test_headers_on_404(self, app: FastAPI) -> None:
        """Security headers are added to 404 responses."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)

        response = client.get("/nonexistent")

        assert response.status_code == 404
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


class TestMultipleMiddleware:
    """Test security headers with other middleware."""

    def test_headers_preserved_with_other_middleware(self, app: FastAPI) -> None:
        """Security headers work alongside other middleware."""
        from starlette.middleware.gzip import GZipMiddleware

        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(GZipMiddleware)
        client = TestClient(app)

        response = client.get("/test")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
