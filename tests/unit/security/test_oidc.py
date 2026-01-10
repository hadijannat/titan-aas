from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError
from jose.exceptions import ExpiredSignatureError

from titan.security.oidc import InvalidTokenError, OIDCConfig, TokenValidator


@pytest.mark.asyncio
async def test_validate_token_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    config = OIDCConfig(issuer="https://issuer", audience="titan")
    validator = TokenValidator(config)

    async def fake_get_jwks(self: TokenValidator) -> dict[str, object]:
        return {"keys": []}

    def fake_decode(*_args: object, **_kwargs: object) -> object:
        raise ExpiredSignatureError("expired")

    monkeypatch.setattr(TokenValidator, "_get_jwks", fake_get_jwks)
    monkeypatch.setattr("titan.security.oidc.jwt.decode", fake_decode)

    with pytest.raises(InvalidTokenError, match="expired"):
        await validator.validate_token("token")


@pytest.mark.asyncio
async def test_validate_token_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    config = OIDCConfig(issuer="https://issuer", audience="titan")
    validator = TokenValidator(config)

    async def fake_get_jwks(self: TokenValidator) -> dict[str, object]:
        return {"keys": []}

    def fake_decode(*_args: object, **_kwargs: object) -> object:
        raise JWTError("bad signature")

    monkeypatch.setattr(TokenValidator, "_get_jwks", fake_get_jwks)
    monkeypatch.setattr("titan.security.oidc.jwt.decode", fake_decode)

    with pytest.raises(InvalidTokenError, match="Invalid token"):
        await validator.validate_token("token")


def test_extract_roles_from_claims() -> None:
    config = OIDCConfig(
        issuer="https://issuer",
        audience="titan",
        roles_claim="roles",
        client_id="titan",
    )
    validator = TokenValidator(config)
    payload = {
        "roles": ["reader", "writer"],
        "realm_access": {"roles": ["admin"]},
        "resource_access": {"titan": {"roles": ["titan:write"]}},
    }

    roles = validator._extract_roles(payload)
    assert set(roles) == {"reader", "writer", "admin", "titan:write"}


@pytest.mark.asyncio
async def test_get_jwks_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    config = OIDCConfig(issuer="https://issuer", audience="titan", jwks_cache_seconds=3600)
    validator = TokenValidator(config)
    calls: dict[str, int] = {"count": 0}

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class FakeClient:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> FakeResponse:
            calls["count"] += 1
            return FakeResponse(self._payload)

    monkeypatch.setattr(
        "titan.security.oidc.httpx.AsyncClient",
        lambda: FakeClient({"keys": ["k1"]}),
    )

    first = await validator._get_jwks()
    second = await validator._get_jwks()

    assert first == {"keys": ["k1"]}
    assert second == {"keys": ["k1"]}
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_get_jwks_fallback_to_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    config = OIDCConfig(issuer="https://issuer", audience="titan", jwks_cache_seconds=1)
    validator = TokenValidator(config)
    validator._jwks = {"keys": ["cached"]}
    validator._jwks_fetched_at = datetime.now(timezone.utc) - timedelta(seconds=120)

    class FailingClient:
        async def __aenter__(self) -> "FailingClient":
            return self

        async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("network down")

    monkeypatch.setattr("titan.security.oidc.httpx.AsyncClient", lambda: FailingClient())

    jwks = await validator._get_jwks()
    assert jwks == {"keys": ["cached"]}
