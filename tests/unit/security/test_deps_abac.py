"""Tests for ABAC enforcement in security dependencies."""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request

from titan.security import abac as abac_module
from titan.security.deps import require_permission
from titan.security.oidc import User
from titan.security.rbac import Permission


def _make_request(path_params: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "path": "/test",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "path_params": path_params or {},
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_abac_denies_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """ABAC deny result blocks access when enabled."""
    engine = abac_module.ABACEngine(
        policies=[
            abac_module.CustomPolicy(
                name="deny_all",
                evaluator=lambda ctx: abac_module.PolicyResult(
                    decision=abac_module.PolicyDecision.DENY,
                    policy_name="deny_all",
                    reason="blocked",
                ),
            )
        ],
        default_deny=True,
    )
    monkeypatch.setattr(
        "titan.security.deps._get_abac_engine",
        lambda: engine,
    )

    user = User(sub="user-1", roles=["reader"])
    dependency = require_permission(Permission.READ_AAS)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(_make_request(), user)

    assert exc_info.value.status_code == 403
    assert "ABAC denied" in exc_info.value.detail


@pytest.mark.asyncio
async def test_abac_allows_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """ABAC allow result permits access when enabled."""
    engine = abac_module.ABACEngine(
        policies=[
            abac_module.CustomPolicy(
                name="allow_all",
                evaluator=lambda ctx: abac_module.PolicyResult(
                    decision=abac_module.PolicyDecision.ALLOW,
                    policy_name="allow_all",
                ),
            )
        ],
        default_deny=True,
    )
    monkeypatch.setattr(
        "titan.security.deps._get_abac_engine",
        lambda: engine,
    )

    user = User(sub="user-1", roles=["reader"])
    dependency = require_permission(Permission.READ_AAS)

    assert await dependency(_make_request(), user) == user


@pytest.mark.asyncio
async def test_abac_skips_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admin users bypass ABAC evaluation."""
    engine = abac_module.ABACEngine(
        policies=[
            abac_module.CustomPolicy(
                name="deny_all",
                evaluator=lambda ctx: abac_module.PolicyResult(
                    decision=abac_module.PolicyDecision.DENY,
                    policy_name="deny_all",
                ),
            )
        ],
        default_deny=True,
    )
    monkeypatch.setattr(
        "titan.security.deps._get_abac_engine",
        lambda: engine,
    )

    admin = User(sub="admin", roles=["admin"])
    dependency = require_permission(Permission.READ_AAS)

    assert await dependency(_make_request(), admin) == admin
