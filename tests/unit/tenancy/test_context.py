"""Tests for tenant context management."""

import pytest

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


class TestTenantContext:
    """Tests for TenantContext dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """TenantContext can be created with just tenant_id."""
        ctx = TenantContext(tenant_id="acme")

        assert ctx.tenant_id == "acme"
        assert ctx.tenant_name is None
        assert ctx.metadata == {}
        assert ctx.created_at is not None

    def test_creation_with_all_fields(self) -> None:
        """TenantContext can be created with all fields."""
        ctx = TenantContext(
            tenant_id="acme",
            tenant_name="Acme Corp",
            metadata={"plan": "enterprise"},
        )

        assert ctx.tenant_id == "acme"
        assert ctx.tenant_name == "Acme Corp"
        assert ctx.metadata == {"plan": "enterprise"}

    def test_to_dict(self) -> None:
        """TenantContext converts to dictionary."""
        ctx = TenantContext(
            tenant_id="acme",
            tenant_name="Acme Corp",
            metadata={"plan": "enterprise"},
        )

        data = ctx.to_dict()

        assert data["tenant_id"] == "acme"
        assert data["tenant_name"] == "Acme Corp"
        assert data["metadata"] == {"plan": "enterprise"}
        assert "created_at" in data


class TestGetCurrentTenant:
    """Tests for get_current_tenant function."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_returns_default_when_not_set(self) -> None:
        """Returns default tenant when none set."""
        tenant = get_current_tenant()

        assert tenant == DEFAULT_TENANT

    def test_returns_set_tenant(self) -> None:
        """Returns the set tenant ID."""
        set_tenant("acme")

        tenant = get_current_tenant()

        assert tenant == "acme"


class TestGetCurrentTenantOrNone:
    """Tests for get_current_tenant_or_none function."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_returns_none_when_not_set(self) -> None:
        """Returns None when no tenant set."""
        tenant = get_current_tenant_or_none()

        assert tenant is None

    def test_returns_set_tenant(self) -> None:
        """Returns the set tenant ID."""
        set_tenant("acme")

        tenant = get_current_tenant_or_none()

        assert tenant == "acme"


class TestSetTenant:
    """Tests for set_tenant function."""

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_sets_tenant_id(self) -> None:
        """set_tenant sets the tenant ID."""
        set_tenant("acme")

        assert get_current_tenant() == "acme"

    def test_sets_tenant_name(self) -> None:
        """set_tenant sets the tenant name."""
        set_tenant("acme", tenant_name="Acme Corp")

        ctx = get_tenant_context()
        assert ctx is not None
        assert ctx.tenant_name == "Acme Corp"

    def test_sets_metadata(self) -> None:
        """set_tenant sets metadata."""
        set_tenant("acme", metadata={"plan": "enterprise"})

        ctx = get_tenant_context()
        assert ctx is not None
        assert ctx.metadata == {"plan": "enterprise"}

    def test_returns_context(self) -> None:
        """set_tenant returns the created context."""
        ctx = set_tenant("acme")

        assert isinstance(ctx, TenantContext)
        assert ctx.tenant_id == "acme"


class TestSetTenantContext:
    """Tests for set_tenant_context function."""

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_sets_context_directly(self) -> None:
        """set_tenant_context sets the context."""
        ctx = TenantContext(tenant_id="acme", tenant_name="Acme Corp")

        set_tenant_context(ctx)

        retrieved = get_tenant_context()
        assert retrieved is ctx


class TestClearTenant:
    """Tests for clear_tenant function."""

    def test_clears_tenant(self) -> None:
        """clear_tenant removes the tenant context."""
        set_tenant("acme")

        clear_tenant()

        assert get_current_tenant_or_none() is None


class TestRequireTenant:
    """Tests for require_tenant function."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_raises_when_not_set(self) -> None:
        """require_tenant raises when no tenant set."""
        with pytest.raises(RuntimeError, match="No tenant context set"):
            require_tenant()

    def test_returns_tenant_when_set(self) -> None:
        """require_tenant returns tenant ID when set."""
        set_tenant("acme")

        tenant = require_tenant()

        assert tenant == "acme"


class TestTenantScope:
    """Tests for TenantScope context manager."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    def test_sets_tenant_in_scope(self) -> None:
        """TenantScope sets tenant within block."""
        with TenantScope("acme"):
            assert get_current_tenant() == "acme"

    def test_restores_previous_tenant(self) -> None:
        """TenantScope restores previous tenant after block."""
        set_tenant("original")

        with TenantScope("acme"):
            assert get_current_tenant() == "acme"

        assert get_current_tenant() == "original"

    def test_clears_tenant_after_scope_if_none_before(self) -> None:
        """TenantScope clears tenant after block if none was set."""
        with TenantScope("acme"):
            assert get_current_tenant() == "acme"

        assert get_current_tenant_or_none() is None

    def test_returns_context(self) -> None:
        """TenantScope returns context on enter."""
        with TenantScope("acme", tenant_name="Acme Corp") as ctx:
            assert ctx.tenant_id == "acme"
            assert ctx.tenant_name == "Acme Corp"

    def test_nested_scopes(self) -> None:
        """Nested TenantScopes work correctly."""
        with TenantScope("outer"):
            assert get_current_tenant() == "outer"

            with TenantScope("inner"):
                assert get_current_tenant() == "inner"

            assert get_current_tenant() == "outer"


class TestAsyncTenantScope:
    """Tests for AsyncTenantScope context manager."""

    def setup_method(self) -> None:
        """Clear tenant before each test."""
        clear_tenant()

    def teardown_method(self) -> None:
        """Clear tenant after each test."""
        clear_tenant()

    @pytest.mark.asyncio
    async def test_sets_tenant_in_scope(self) -> None:
        """AsyncTenantScope sets tenant within block."""
        async with AsyncTenantScope("acme"):
            assert get_current_tenant() == "acme"

    @pytest.mark.asyncio
    async def test_restores_previous_tenant(self) -> None:
        """AsyncTenantScope restores previous tenant after block."""
        set_tenant("original")

        async with AsyncTenantScope("acme"):
            assert get_current_tenant() == "acme"

        assert get_current_tenant() == "original"

    @pytest.mark.asyncio
    async def test_clears_tenant_after_scope_if_none_before(self) -> None:
        """AsyncTenantScope clears tenant after block if none was set."""
        async with AsyncTenantScope("acme"):
            assert get_current_tenant() == "acme"

        assert get_current_tenant_or_none() is None

    @pytest.mark.asyncio
    async def test_returns_context(self) -> None:
        """AsyncTenantScope returns context on enter."""
        async with AsyncTenantScope("acme", tenant_name="Acme Corp") as ctx:
            assert ctx.tenant_id == "acme"
            assert ctx.tenant_name == "Acme Corp"

    @pytest.mark.asyncio
    async def test_nested_scopes(self) -> None:
        """Nested AsyncTenantScopes work correctly."""
        async with AsyncTenantScope("outer"):
            assert get_current_tenant() == "outer"

            async with AsyncTenantScope("inner"):
                assert get_current_tenant() == "inner"

            assert get_current_tenant() == "outer"
