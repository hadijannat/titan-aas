"""Tenant isolation for database queries and cache keys.

Provides tenant-scoped access:
- TenantFilter: SQLAlchemy filter for tenant isolation
- TenantCacheKey: Tenant-prefixed cache key generation
- Row-Level Security (RLS) helpers

Example:
    from titan.tenancy.isolation import TenantFilter, TenantCacheKey

    # Filter queries by tenant
    query = select(Shell).where(TenantFilter.apply(Shell))

    # Generate tenant-scoped cache key
    key = TenantCacheKey.for_entity("shell", shell_id)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, TypeVar

from titan.tenancy.context import get_current_tenant, require_tenant

T = TypeVar("T")


@dataclass
class TenantFilter:
    """Filter for tenant-scoped database queries.

    Adds tenant_id filter to SQLAlchemy queries.
    """

    @staticmethod
    def apply(model: type[T], tenant_id: str | None = None) -> Any:
        """Apply tenant filter to a model.

        Args:
            model: SQLAlchemy model with tenant_id column
            tenant_id: Explicit tenant ID (uses current if not provided)

        Returns:
            SQLAlchemy filter expression
        """
        tid = tenant_id or get_current_tenant()
        return model.tenant_id == tid  # type: ignore[attr-defined]

    @staticmethod
    def apply_required(model: type[T]) -> Any:
        """Apply tenant filter, requiring a tenant to be set.

        Args:
            model: SQLAlchemy model with tenant_id column

        Returns:
            SQLAlchemy filter expression

        Raises:
            RuntimeError: If no tenant is set
        """
        tid = require_tenant()
        return model.tenant_id == tid  # type: ignore[attr-defined]


class TenantCacheKey:
    """Generate tenant-scoped cache keys.

    Prefixes cache keys with tenant ID to prevent cross-tenant cache pollution.
    """

    PREFIX = "tenant"
    SEPARATOR = ":"

    @classmethod
    def build(cls, *parts: str, tenant_id: str | None = None) -> str:
        """Build a tenant-scoped cache key.

        Args:
            *parts: Key parts to join
            tenant_id: Explicit tenant ID (uses current if not provided)

        Returns:
            Tenant-prefixed cache key
        """
        tid = tenant_id or get_current_tenant()
        all_parts = [cls.PREFIX, tid, *parts]
        return cls.SEPARATOR.join(all_parts)

    @classmethod
    def for_entity(
        cls,
        entity_type: str,
        entity_id: str,
        tenant_id: str | None = None,
    ) -> str:
        """Build a cache key for an entity.

        Args:
            entity_type: Entity type (shell, submodel, etc.)
            entity_id: Entity identifier
            tenant_id: Explicit tenant ID

        Returns:
            Cache key like "tenant:acme:shell:id123"
        """
        return cls.build(entity_type, entity_id, tenant_id=tenant_id)

    @classmethod
    def for_collection(
        cls,
        entity_type: str,
        suffix: str = "all",
        tenant_id: str | None = None,
    ) -> str:
        """Build a cache key for a collection.

        Args:
            entity_type: Entity type (shells, submodels, etc.)
            suffix: Collection suffix (all, list, etc.)
            tenant_id: Explicit tenant ID

        Returns:
            Cache key like "tenant:acme:shells:all"
        """
        return cls.build(entity_type, suffix, tenant_id=tenant_id)

    @classmethod
    def hash_key(cls, key: str, max_length: int = 64) -> str:
        """Hash a cache key if it's too long.

        Args:
            key: Original cache key
            max_length: Maximum key length

        Returns:
            Original key or hashed version if too long
        """
        if len(key) <= max_length:
            return key

        # Hash and include prefix for debugging
        hash_value = hashlib.sha256(key.encode()).hexdigest()[:16]
        prefix = key[: max_length - 17]  # Leave room for hash and separator
        return f"{prefix}{cls.SEPARATOR}{hash_value}"


class TenantIsolationError(Exception):
    """Raised when tenant isolation is violated."""

    pass


def validate_tenant_access(entity_tenant_id: str, operation: str = "access") -> None:
    """Validate that current tenant can access an entity.

    Args:
        entity_tenant_id: Tenant ID of the entity
        operation: Operation being performed

    Raises:
        TenantIsolationError: If access is denied
    """
    current_tenant = get_current_tenant()

    if entity_tenant_id != current_tenant:
        raise TenantIsolationError(
            f"Tenant '{current_tenant}' cannot {operation} entity "
            f"belonging to tenant '{entity_tenant_id}'"
        )


def ensure_tenant_field(data: dict[str, Any], field: str = "tenant_id") -> dict[str, Any]:
    """Ensure tenant field is set on data.

    Args:
        data: Data dictionary
        field: Tenant field name

    Returns:
        Data with tenant field set
    """
    if field not in data or data[field] is None:
        data[field] = get_current_tenant()
    return data


@dataclass
class RLSPolicy:
    """Row-Level Security policy definition.

    Represents a PostgreSQL RLS policy for tenant isolation.
    """

    table_name: str
    policy_name: str = "tenant_isolation"
    tenant_column: str = "tenant_id"
    session_variable: str = "app.tenant_id"

    def enable_rls_sql(self) -> str:
        """Generate SQL to enable RLS on table.

        Returns:
            SQL statement
        """
        return f"ALTER TABLE {self.table_name} ENABLE ROW LEVEL SECURITY;"

    def create_policy_sql(self) -> str:
        """Generate SQL to create the RLS policy.

        Returns:
            SQL statement
        """
        return f"""
CREATE POLICY {self.policy_name} ON {self.table_name}
    USING ({self.tenant_column} = current_setting('{self.session_variable}'))
    WITH CHECK ({self.tenant_column} = current_setting('{self.session_variable}'));
"""

    def drop_policy_sql(self) -> str:
        """Generate SQL to drop the RLS policy.

        Returns:
            SQL statement
        """
        return f"DROP POLICY IF EXISTS {self.policy_name} ON {self.table_name};"

    def set_tenant_sql(self, tenant_id: str) -> str:
        """Generate SQL to set the tenant for the session.

        Args:
            tenant_id: Tenant ID to set

        Returns:
            SQL statement
        """
        return f"SET {self.session_variable} = '{tenant_id}';"


# Pre-defined RLS policies for common tables
RLS_POLICIES = {
    "shells": RLSPolicy(table_name="shells"),
    "submodels": RLSPolicy(table_name="submodels"),
    "concept_descriptions": RLSPolicy(table_name="concept_descriptions"),
}


def get_rls_migration_sql() -> str:
    """Generate SQL for RLS migration.

    Returns:
        Complete SQL for enabling RLS on all tables
    """
    statements = []

    for policy in RLS_POLICIES.values():
        statements.append(policy.enable_rls_sql())
        statements.append(policy.create_policy_sql())

    return "\n".join(statements)
