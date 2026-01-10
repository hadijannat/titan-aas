from __future__ import annotations

from datetime import datetime, timezone

import pytest

from titan.security.oidc import OIDCConfig, TokenValidator


def test_extract_roles_from_multiple_claims() -> None:
    config = OIDCConfig(
        issuer="https://issuer.example",
        audience="aud",
        roles_claim="roles",
        client_id="client-app",
    )
    validator = TokenValidator(config)

    payload = {
        "roles": ["reader", "writer"],
        "realm_access": {"roles": ["admin"]},
        "resource_access": {"client-app": {"roles": ["client-role"]}},
    }

    roles = validator._extract_roles(payload)

    assert "reader" in roles
    assert "writer" in roles
    assert "admin" in roles
    assert "client-role" in roles


@pytest.mark.asyncio
async def test_validate_token_returns_user(monkeypatch: pytest.MonkeyPatch) -> None:
    config = OIDCConfig(
        issuer="https://issuer.example",
        audience="aud",
        roles_claim="roles",
    )
    validator = TokenValidator(config)

    payload = {
        "sub": "user-123",
        "email": "user@example.com",
        "preferred_username": "user1",
        "roles": ["reader"],
    }

    async def fake_get_jwks() -> dict:
        return {"keys": []}

    def fake_decode(*args, **kwargs):  # noqa: ANN001
        return payload

    monkeypatch.setattr(validator, "_get_jwks", fake_get_jwks)
    monkeypatch.setattr("titan.security.oidc.jwt.decode", fake_decode)

    user = await validator.validate_token("token")

    assert user.sub == "user-123"
    assert user.email == "user@example.com"
    assert user.name == "user1"
    assert "reader" in user.roles


@pytest.mark.asyncio
async def test_jwks_cache_skips_http(monkeypatch: pytest.MonkeyPatch) -> None:
    config = OIDCConfig(
        issuer="https://issuer.example",
        audience="aud",
    )
    validator = TokenValidator(config)

    validator._jwks = {"keys": [{"kty": "RSA"}]}
    validator._jwks_fetched_at = datetime.now(timezone.utc)

    class ExplodingClient:
        async def __aenter__(self):
            raise AssertionError("HTTP client should not be called for cached JWKS")

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("titan.security.oidc.httpx.AsyncClient", ExplodingClient)

    jwks = await validator._get_jwks()
    assert jwks == {"keys": [{"kty": "RSA"}]}
