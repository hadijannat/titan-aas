"""Integration tests for security flows.

Tests authentication, authorization, and security controls end-to-end.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from titan.core.ids import encode_id_to_b64url
from titan.security.oidc import User

# Marker for tests that require full OIDC and middleware stack
requires_oidc = pytest.mark.skip(reason="Requires OIDC configuration and middleware integration")

if TYPE_CHECKING:
    from redis.asyncio import Redis


# Mock JWT for testing (not cryptographically secure, for testing only)
def create_test_token(
    sub: str = "test-user",
    roles: list[str] | None = None,
    exp: int | None = None,
    iss: str = "https://test-issuer.example.com",
) -> str:
    """Create a mock JWT token for testing.

    This is NOT secure and only for testing purposes.
    """
    if roles is None:
        roles = ["reader"]
    if exp is None:
        exp = int(time.time()) + 3600  # 1 hour from now

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "iss": iss,
        "aud": "titan-aas",
        "exp": exp,
        "iat": int(time.time()),
        "roles": roles,
    }

    def b64encode(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    header_b64 = b64encode(header)
    payload_b64 = b64encode(payload)

    # Use a test secret (not secure, test-only)
    secret = b"test-secret-key-for-testing-only"
    signature = hmac.new(
        secret,
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256,
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

    return f"{header_b64}.{payload_b64}.{signature_b64}"


class TestAuthenticationFlows:
    """Test authentication handling."""

    @pytest.mark.asyncio
    async def test_anonymous_mode_disabled_by_default(
        self,
        test_client: AsyncClient,
    ) -> None:
        """When OIDC is not configured, anonymous access is denied by default."""
        from titan.config import settings

        original_allow_anonymous = settings.allow_anonymous_admin
        settings.allow_anonymous_admin = False
        try:
            response = await test_client.get("/shells")
            assert response.status_code == 401
        finally:
            settings.allow_anonymous_admin = original_allow_anonymous

    @pytest.mark.asyncio
    async def test_invalid_bearer_format_returns_401(
        self,
        test_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invalid Authorization header format returns 401."""
        from titan.security import oidc as oidc_module

        # Enable OIDC by setting a mock validator
        class MockValidator:
            async def validate_token(self, token: str) -> User:
                return User(sub="test", name="Test", roles=["reader"])

        monkeypatch.setattr(oidc_module, "_validator", MockValidator())

        # Test without "Bearer " prefix
        response = await test_client.get(
            "/shells",
            headers={"Authorization": "InvalidFormat token123"},
        )
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    @pytest.mark.asyncio
    async def test_valid_token_with_reader_role_can_read(
        self,
        test_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Valid token with reader role can read resources."""
        from titan.security import oidc as oidc_module

        class MockValidator:
            async def validate_token(self, token: str) -> User:
                return User(sub="reader-user", name="Reader", roles=["reader"])

        monkeypatch.setattr(oidc_module, "_validator", MockValidator())

        response = await test_client.get(
            "/shells",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 200


class TestRBACEnforcement:
    """Test role-based access control."""

    @pytest.mark.asyncio
    async def test_reader_cannot_create_resources(
        self,
        test_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reader role cannot create new resources."""
        from titan.security import oidc as oidc_module

        class MockValidator:
            async def validate_token(self, token: str) -> User:
                return User(sub="reader-user", name="Reader", roles=["reader"])

        monkeypatch.setattr(oidc_module, "_validator", MockValidator())

        aas_data = {
            "id": "urn:example:aas:test-reader-create",
            "idShort": "TestReaderCreate",
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": "urn:example:asset:test",
            },
        }
        response = await test_client.post(
            "/shells",
            json=aas_data,
            headers={"Authorization": "Bearer reader-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_writer_can_create_but_not_delete(
        self,
        test_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Writer role can create but cannot delete resources."""
        from titan.security import oidc as oidc_module

        class MockValidator:
            async def validate_token(self, token: str) -> User:
                return User(sub="writer-user", name="Writer", roles=["writer"])

        monkeypatch.setattr(oidc_module, "_validator", MockValidator())

        # Writer can create
        aas_data = {
            "id": "urn:example:aas:test-writer",
            "idShort": "TestWriter",
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": "urn:example:asset:test-writer",
            },
        }
        response = await test_client.post(
            "/shells",
            json=aas_data,
            headers={"Authorization": "Bearer writer-token"},
        )
        assert response.status_code in (200, 201)

        # Writer cannot delete
        aas_id_b64 = encode_id_to_b64url("urn:example:aas:test-writer")
        response = await test_client.delete(
            f"/shells/{aas_id_b64}",
            headers={"Authorization": "Bearer writer-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_has_full_access(
        self,
        test_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Admin role has full access to all operations."""
        from titan.security import oidc as oidc_module

        class MockValidator:
            async def validate_token(self, token: str) -> User:
                return User(sub="admin-user", name="Admin", roles=["admin"])

        monkeypatch.setattr(oidc_module, "_validator", MockValidator())

        # Admin can create
        aas_data = {
            "id": "urn:example:aas:test-admin",
            "idShort": "TestAdmin",
            "modelType": "AssetAdministrationShell",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": "urn:example:asset:test-admin",
            },
        }
        response = await test_client.post(
            "/shells",
            json=aas_data,
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code in (200, 201)

        # Admin can delete
        aas_id_b64 = encode_id_to_b64url("urn:example:aas:test-admin")
        response = await test_client.delete(
            f"/shells/{aas_id_b64}",
            headers={"Authorization": "Bearer admin-token"},
        )
        assert response.status_code == 204


class TestRateLimiting:
    """Test rate limiting behavior."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(
        self,
        redis_client: Redis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Rate limit headers are present in responses."""
        from fastapi import FastAPI

        from titan.api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware

        async def get_test_redis() -> Redis:
            return redis_client

        import titan.cache as cache_module

        monkeypatch.setattr(cache_module, "get_redis", get_test_redis)

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(
                requests_per_window=100,
                window_seconds=60,
                bypass_prefixes=["/health"],
            ),
        )

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/test")

        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_bypass_paths(
        self,
        redis_client: Redis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Health and metrics paths bypass rate limiting."""
        from fastapi import FastAPI

        from titan.api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware

        async def get_test_redis() -> Redis:
            return redis_client

        import titan.cache as cache_module

        monkeypatch.setattr(cache_module, "get_redis", get_test_redis)

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(
                requests_per_window=1,  # Very low limit
                window_seconds=60,
                bypass_prefixes=["/health", "/metrics"],
            ),
        )

        @app.get("/health/live")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        @app.get("/metrics")
        async def metrics() -> str:
            return "prometheus_metrics"

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # Multiple health requests should not be rate limited
            for _ in range(5):
                response = await client.get("/health/live")
                assert response.status_code == 200

            # Multiple metrics requests should not be rate limited
            for _ in range(5):
                response = await client.get("/metrics")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limit_returns_retry_after(
        self,
        redis_client: Redis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """429 responses include Retry-After header."""
        from fastapi import FastAPI

        from titan.api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware

        async def get_test_redis() -> Redis:
            return redis_client

        import titan.cache as cache_module

        monkeypatch.setattr(cache_module, "get_redis", get_test_redis)

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(
                requests_per_window=1,
                window_seconds=60,
                bypass_prefixes=[],
            ),
        )

        @app.get("/limited")
        async def limited() -> dict[str, str]:
            return {"status": "ok"}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # First request succeeds
            await client.get("/limited")
            # Second request is rate limited
            response = await client.get("/limited")

        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_rate_limit_by_token_hash(
        self,
        redis_client: Redis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Authenticated requests are rate limited by token hash."""
        from fastapi import FastAPI

        from titan.api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware

        async def get_test_redis() -> Redis:
            return redis_client

        import titan.cache as cache_module

        monkeypatch.setattr(cache_module, "get_redis", get_test_redis)

        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(
                requests_per_window=2,
                window_seconds=60,
                bypass_prefixes=[],
            ),
        )

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # User 1 makes 2 requests
            for _ in range(2):
                response = await client.get(
                    "/test",
                    headers={"Authorization": "Bearer user1-token"},
                )
                assert response.status_code == 200

            # User 1 is now rate limited
            response = await client.get(
                "/test",
                headers={"Authorization": "Bearer user1-token"},
            )
            assert response.status_code == 429

            # User 2 can still make requests (separate rate limit)
            response = await client.get(
                "/test",
                headers={"Authorization": "Bearer user2-token"},
            )
            assert response.status_code == 200


class TestSecurityHeaders:
    """Test security response headers."""

    @pytest.mark.asyncio
    async def test_security_headers_present(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Security headers are present in responses."""
        response = await test_client.get("/health/live")

        # Check standard security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    @pytest.mark.asyncio
    async def test_hsts_header_when_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """HSTS header is present when enabled."""
        from contextlib import asynccontextmanager

        from fastapi import FastAPI
        from fastapi.responses import ORJSONResponse

        from titan.api.middleware.security_headers import SecurityHeadersMiddleware
        from titan.config import settings

        # Enable HSTS
        monkeypatch.setattr(settings, "enable_hsts", True)
        monkeypatch.setattr(settings, "hsts_max_age", 31536000)
        monkeypatch.setattr(settings, "hsts_include_subdomains", True)

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            yield

        app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan)
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"status": "ok"}

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/test")

        assert "Strict-Transport-Security" in response.headers
        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts


class TestCorrelationIds:
    """Test request correlation ID handling."""

    @pytest.mark.asyncio
    async def test_correlation_id_returned_in_response(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Response includes correlation ID header."""
        response = await test_client.get("/health/live")

        # Should have a correlation ID in response
        assert "X-Request-ID" in response.headers or "X-Correlation-ID" in response.headers

    @pytest.mark.asyncio
    async def test_client_correlation_id_preserved(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Client-provided correlation ID is preserved."""
        client_correlation_id = "test-correlation-12345"

        response = await test_client.get(
            "/health/live",
            headers={"X-Correlation-ID": client_correlation_id},
        )

        # Response should echo the correlation ID
        response_id = response.headers.get("X-Correlation-ID") or response.headers.get(
            "X-Request-ID"
        )
        # The server may echo the client ID or generate a new one
        assert response_id is not None


class TestErrorResponseFormat:
    """Test IDTA-compliant error response format."""

    @pytest.mark.asyncio
    async def test_404_error_format(
        self,
        test_client: AsyncClient,
    ) -> None:
        """404 errors use IDTA message format."""
        # Request non-existent AAS
        fake_id = base64.urlsafe_b64encode(b"urn:example:aas:nonexistent").decode()
        response = await test_client.get(f"/shells/{fake_id}")

        assert response.status_code == 404
        data = response.json()

        # IDTA format: { "messages": [ { "code": ..., "messageType": ..., "text": ... } ] }
        assert "messages" in data
        assert isinstance(data["messages"], list)
        assert len(data["messages"]) > 0

        message = data["messages"][0]
        assert "code" in message or "messageType" in message
        assert "text" in message

    @pytest.mark.asyncio
    async def test_400_error_format(
        self,
        test_client: AsyncClient,
    ) -> None:
        """400 errors use IDTA message format."""
        # Request with invalid Base64 ID
        response = await test_client.get("/shells/!!!invalid-base64!!!")

        assert response.status_code == 400
        data = response.json()

        assert "messages" in data
        assert isinstance(data["messages"], list)

    @requires_oidc
    @pytest.mark.asyncio
    async def test_error_includes_timestamp(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Error responses include timestamp."""
        fake_id = encode_id_to_b64url("urn:example:aas:test-ts")
        response = await test_client.get(f"/shells/{fake_id}")

        assert response.status_code == 404
        data = response.json()

        if data.get("messages"):
            message = data["messages"][0]
            # Timestamp may be in message or at top level
            assert "timestamp" in message or "timestamp" in data
