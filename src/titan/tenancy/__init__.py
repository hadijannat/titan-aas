"""Multi-tenancy module for Titan-AAS.

Provides tenant isolation for SaaS deployment:
- TenantContext: Request-scoped tenant information
- TenantMiddleware: Extract tenant from requests
- TenantFilter: Database query isolation
- TenantCacheKey: Tenant-scoped cache keys

Example:
    from fastapi import FastAPI
    from titan.tenancy import TenantMiddleware, get_current_tenant

    app = FastAPI()
    app.add_middleware(TenantMiddleware)

    @app.get("/shells")
    async def list_shells():
        tenant = get_current_tenant()
        # Query automatically filtered by tenant
        ...
"""

from titan.tenancy.context import (
    DEFAULT_TENANT,
    AsyncTenantScope,
    TenantContext,
    TenantScope,
    clear_tenant,
    get_current_tenant,
    get_current_tenant_or_none,
    get_tenant_context,
    require_tenant,
    set_tenant,
    set_tenant_context,
)
from titan.tenancy.isolation import (
    RLS_POLICIES,
    RLSPolicy,
    TenantCacheKey,
    TenantFilter,
    TenantIsolationError,
    ensure_tenant_field,
    get_rls_migration_sql,
    validate_tenant_access,
)
from titan.tenancy.middleware import (
    TenantExtractionError,
    TenantMiddleware,
    get_tenant_from_request,
)

__all__ = [
    # Context
    "TenantContext",
    "TenantScope",
    "AsyncTenantScope",
    "DEFAULT_TENANT",
    "get_current_tenant",
    "get_current_tenant_or_none",
    "get_tenant_context",
    "set_tenant",
    "set_tenant_context",
    "clear_tenant",
    "require_tenant",
    # Middleware
    "TenantMiddleware",
    "TenantExtractionError",
    "get_tenant_from_request",
    # Isolation
    "TenantFilter",
    "TenantCacheKey",
    "TenantIsolationError",
    "validate_tenant_access",
    "ensure_tenant_field",
    "RLSPolicy",
    "RLS_POLICIES",
    "get_rls_migration_sql",
]
