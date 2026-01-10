"""Tenant context management using ContextVar.

Provides request-scoped tenant isolation:
- TenantContext: Dataclass with tenant information
- tenant_context: ContextVar for async-safe tenant access
- get_current_tenant: Get current tenant ID
- set_tenant: Set tenant context for current scope

Example:
    from titan.tenancy.context import get_current_tenant, set_tenant

    # Set tenant for current request
    set_tenant("acme-corp")

    # Get current tenant anywhere in the call stack
    tenant_id = get_current_tenant()
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class TenantContext:
    """Tenant context for the current request.

    Attributes:
        tenant_id: Unique tenant identifier
        tenant_name: Human-readable tenant name
        metadata: Additional tenant metadata
        created_at: When this context was created
    """

    tenant_id: str
    tenant_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


# Default tenant for when no tenant is set
DEFAULT_TENANT = "default"

# ContextVar for async-safe tenant access
_tenant_context: ContextVar[TenantContext | None] = ContextVar(
    "tenant_context",
    default=None,
)


def get_tenant_context() -> TenantContext | None:
    """Get the current tenant context.

    Returns:
        TenantContext if set, None otherwise
    """
    return _tenant_context.get()


def get_current_tenant() -> str:
    """Get the current tenant ID.

    Returns:
        Tenant ID or default tenant if not set
    """
    ctx = _tenant_context.get()
    if ctx is None:
        return DEFAULT_TENANT
    return ctx.tenant_id


def get_current_tenant_or_none() -> str | None:
    """Get the current tenant ID or None if not set.

    Returns:
        Tenant ID or None
    """
    ctx = _tenant_context.get()
    if ctx is None:
        return None
    return ctx.tenant_id


def set_tenant(
    tenant_id: str,
    tenant_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TenantContext:
    """Set the tenant context for the current scope.

    Args:
        tenant_id: Unique tenant identifier
        tenant_name: Optional human-readable name
        metadata: Optional additional metadata

    Returns:
        The created TenantContext
    """
    ctx = TenantContext(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        metadata=metadata or {},
    )
    _tenant_context.set(ctx)
    return ctx


def set_tenant_context(ctx: TenantContext) -> None:
    """Set the tenant context directly.

    Args:
        ctx: TenantContext to set
    """
    _tenant_context.set(ctx)


def clear_tenant() -> None:
    """Clear the current tenant context."""
    _tenant_context.set(None)


def require_tenant() -> str:
    """Get the current tenant ID, raising if not set.

    Returns:
        The current tenant ID

    Raises:
        RuntimeError: If no tenant is set
    """
    ctx = _tenant_context.get()
    if ctx is None:
        raise RuntimeError("No tenant context set. Ensure TenantMiddleware is active.")
    return ctx.tenant_id


class TenantScope:
    """Context manager for temporarily setting a tenant.

    Example:
        with TenantScope("acme-corp"):
            # All operations here use acme-corp tenant
            shells = await repo.list_all()
    """

    def __init__(
        self,
        tenant_id: str,
        tenant_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize tenant scope.

        Args:
            tenant_id: Tenant identifier
            tenant_name: Optional tenant name
            metadata: Optional metadata
        """
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.metadata = metadata
        self._previous_context: TenantContext | None = None
        self._token: Any = None

    def __enter__(self) -> TenantContext:
        """Enter the tenant scope."""
        self._previous_context = _tenant_context.get()
        ctx = TenantContext(
            tenant_id=self.tenant_id,
            tenant_name=self.tenant_name,
            metadata=self.metadata or {},
        )
        self._token = _tenant_context.set(ctx)
        return ctx

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the tenant scope and restore previous context."""
        if self._previous_context is not None:
            _tenant_context.set(self._previous_context)
        else:
            _tenant_context.set(None)


class AsyncTenantScope:
    """Async context manager for temporarily setting a tenant.

    Example:
        async with AsyncTenantScope("acme-corp"):
            shells = await repo.list_all()
    """

    def __init__(
        self,
        tenant_id: str,
        tenant_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize async tenant scope."""
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.metadata = metadata
        self._previous_context: TenantContext | None = None

    async def __aenter__(self) -> TenantContext:
        """Enter the tenant scope."""
        self._previous_context = _tenant_context.get()
        ctx = TenantContext(
            tenant_id=self.tenant_id,
            tenant_name=self.tenant_name,
            metadata=self.metadata or {},
        )
        _tenant_context.set(ctx)
        return ctx

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the tenant scope and restore previous context."""
        if self._previous_context is not None:
            _tenant_context.set(self._previous_context)
        else:
            _tenant_context.set(None)
