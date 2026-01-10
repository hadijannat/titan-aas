"""Integration tests for rate limiting middleware."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from titan.api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware


@pytest.mark.asyncio
async def test_rate_limit_enforced(redis_client: Redis, monkeypatch: pytest.MonkeyPatch) -> None:
    """Requests beyond the configured window should return 429."""
    from fastapi import FastAPI

    async def get_test_redis() -> Redis:
        return redis_client

    import titan.cache as cache_module

    monkeypatch.setattr(cache_module, "get_redis", get_test_redis)

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(requests_per_window=2, window_seconds=60, bypass_prefixes=[]),
    )

    @app.get("/limited")
    async def limited() -> dict[str, str]:
        return {"ok": "true"}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp1 = await client.get("/limited")
        resp2 = await client.get("/limited")
        resp3 = await client.get("/limited")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp3.status_code == 429
    assert "X-RateLimit-Limit" in resp2.headers
    assert "X-RateLimit-Remaining" in resp2.headers
