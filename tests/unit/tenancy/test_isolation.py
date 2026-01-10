"""Tests for tenant isolation utilities."""

import pytest

from titan.tenancy.context import clear_tenant, set_tenant
from titan.tenancy.isolation import (
    RLS_POLICIES,
    RLSPolicy,
    TenantCacheKey,
    TenantIsolationError,
    ensure_tenant_field,
    get_rls_migration_sql,
    validate_tenant_access,
)


class TestTenantCacheKey:
    """Tests for TenantCacheKey class."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_build_with_current_tenant(self) -> None:
        """build uses current tenant when not specified."""
        set_tenant("acme")

        key = TenantCacheKey.build("shell", "123")

        assert key == "tenant:acme:shell:123"

    def test_build_with_explicit_tenant(self) -> None:
        """build uses explicit tenant when provided."""
        set_tenant("acme")

        key = TenantCacheKey.build("shell", "123", tenant_id="beta")

        assert key == "tenant:beta:shell:123"

    def test_build_with_default_tenant(self) -> None:
        """build uses default tenant when none set."""
        key = TenantCacheKey.build("shell", "123")

        assert key == "tenant:default:shell:123"

    def test_for_entity(self) -> None:
        """for_entity creates entity key."""
        set_tenant("acme")

        key = TenantCacheKey.for_entity("shell", "urn:example:aas:1")

        assert key == "tenant:acme:shell:urn:example:aas:1"

    def test_for_collection(self) -> None:
        """for_collection creates collection key."""
        set_tenant("acme")

        key = TenantCacheKey.for_collection("shells", "all")

        assert key == "tenant:acme:shells:all"

    def test_hash_key_short_key(self) -> None:
        """hash_key returns original key if short enough."""
        short_key = "tenant:acme:shell:123"

        result = TenantCacheKey.hash_key(short_key, max_length=64)

        assert result == short_key

    def test_hash_key_long_key(self) -> None:
        """hash_key hashes long keys."""
        long_key = "tenant:acme:shell:" + "x" * 100

        result = TenantCacheKey.hash_key(long_key, max_length=64)

        assert len(result) <= 64
        assert result.startswith("tenant:acme:")


class TestValidateTenantAccess:
    """Tests for validate_tenant_access function."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_allows_access_to_own_entity(self) -> None:
        """Allows access when tenant matches."""
        set_tenant("acme")

        # Should not raise
        validate_tenant_access("acme", "access")

    def test_denies_access_to_other_entity(self) -> None:
        """Denies access when tenant doesn't match."""
        set_tenant("acme")

        with pytest.raises(TenantIsolationError) as exc:
            validate_tenant_access("beta", "access")

        assert "acme" in str(exc.value)
        assert "beta" in str(exc.value)

    def test_includes_operation_in_error(self) -> None:
        """Error message includes operation."""
        set_tenant("acme")

        with pytest.raises(TenantIsolationError) as exc:
            validate_tenant_access("beta", "delete")

        assert "delete" in str(exc.value)


class TestEnsureTenantField:
    """Tests for ensure_tenant_field function."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_adds_tenant_if_missing(self) -> None:
        """Adds tenant_id if not present."""
        set_tenant("acme")
        data = {"name": "Test"}

        result = ensure_tenant_field(data)

        assert result["tenant_id"] == "acme"
        assert result["name"] == "Test"

    def test_preserves_existing_tenant(self) -> None:
        """Preserves tenant_id if already set."""
        set_tenant("acme")
        data = {"name": "Test", "tenant_id": "existing"}

        result = ensure_tenant_field(data)

        assert result["tenant_id"] == "existing"

    def test_replaces_none_tenant(self) -> None:
        """Replaces None tenant_id."""
        set_tenant("acme")
        data = {"name": "Test", "tenant_id": None}

        result = ensure_tenant_field(data)

        assert result["tenant_id"] == "acme"

    def test_custom_field_name(self) -> None:
        """Works with custom field name."""
        set_tenant("acme")
        data = {"name": "Test"}

        result = ensure_tenant_field(data, field="organization_id")

        assert result["organization_id"] == "acme"


class TestRLSPolicy:
    """Tests for RLSPolicy class."""

    def test_creation(self) -> None:
        """RLSPolicy can be created."""
        policy = RLSPolicy(table_name="shells")

        assert policy.table_name == "shells"
        assert policy.policy_name == "tenant_isolation"
        assert policy.tenant_column == "tenant_id"

    def test_enable_rls_sql(self) -> None:
        """enable_rls_sql generates correct SQL."""
        policy = RLSPolicy(table_name="shells")

        sql = policy.enable_rls_sql()

        assert "ALTER TABLE shells ENABLE ROW LEVEL SECURITY" in sql

    def test_create_policy_sql(self) -> None:
        """create_policy_sql generates correct SQL."""
        policy = RLSPolicy(table_name="shells")

        sql = policy.create_policy_sql()

        assert "CREATE POLICY tenant_isolation ON shells" in sql
        assert "tenant_id = current_setting" in sql

    def test_drop_policy_sql(self) -> None:
        """drop_policy_sql generates correct SQL."""
        policy = RLSPolicy(table_name="shells")

        sql = policy.drop_policy_sql()

        assert "DROP POLICY IF EXISTS tenant_isolation ON shells" in sql

    def test_set_tenant_sql(self) -> None:
        """set_tenant_sql generates correct SQL."""
        policy = RLSPolicy(table_name="shells")

        sql = policy.set_tenant_sql("acme")

        assert "SET app.tenant_id = 'acme'" in sql

    def test_custom_policy_name(self) -> None:
        """Custom policy name is used."""
        policy = RLSPolicy(table_name="shells", policy_name="custom_policy")

        sql = policy.create_policy_sql()

        assert "CREATE POLICY custom_policy ON shells" in sql


class TestRLSPolicies:
    """Tests for pre-defined RLS policies."""

    def test_shells_policy_exists(self) -> None:
        """shells policy is pre-defined."""
        assert "shells" in RLS_POLICIES
        assert RLS_POLICIES["shells"].table_name == "shells"

    def test_submodels_policy_exists(self) -> None:
        """submodels policy is pre-defined."""
        assert "submodels" in RLS_POLICIES
        assert RLS_POLICIES["submodels"].table_name == "submodels"

    def test_concept_descriptions_policy_exists(self) -> None:
        """concept_descriptions policy is pre-defined."""
        assert "concept_descriptions" in RLS_POLICIES
        assert RLS_POLICIES["concept_descriptions"].table_name == "concept_descriptions"


class TestGetRLSMigrationSQL:
    """Tests for get_rls_migration_sql function."""

    def test_generates_sql_for_all_tables(self) -> None:
        """Generates SQL for all tables."""
        sql = get_rls_migration_sql()

        assert "ALTER TABLE shells ENABLE ROW LEVEL SECURITY" in sql
        assert "ALTER TABLE submodels ENABLE ROW LEVEL SECURITY" in sql
        assert "CREATE POLICY tenant_isolation ON shells" in sql
        assert "CREATE POLICY tenant_isolation ON submodels" in sql

    def test_sql_is_not_empty(self) -> None:
        """Generated SQL is not empty."""
        sql = get_rls_migration_sql()

        assert len(sql) > 100
