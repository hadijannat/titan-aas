"""Tests for Attribute-Based Access Control.

Tests ABAC policies, engine, and common policy types.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from titan.security.abac import (
    ABACEngine,
    ABACPolicy,
    Action,
    AllowOwnerPolicy,
    CustomPolicy,
    IPAllowlistPolicy,
    PolicyContext,
    PolicyDecision,
    PolicyResult,
    ResourceType,
    TenantIsolationPolicy,
    TimeBasedPolicy,
    create_default_engine,
)


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = MagicMock()
    user.sub = "user-123"
    user.roles = ["reader"]
    user.tenant_id = "tenant-abc"
    user.is_admin = False
    return user


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for testing."""
    user = MagicMock()
    user.sub = "admin-456"
    user.roles = ["admin"]
    user.tenant_id = "tenant-abc"
    user.is_admin = True
    return user


class TestPolicyContext:
    """Tests for PolicyContext."""

    def test_default_values(self, mock_user):
        """Context has sensible defaults."""
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
        )

        assert ctx.action == Action.READ
        assert ctx.resource_id is None
        assert ctx.client_ip is None
        assert isinstance(ctx.request_time, datetime)

    def test_full_context(self, mock_user):
        """Context can be fully populated."""
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.SUBMODEL,
            resource_id="urn:example:submodel:001",
            resource_owner="user-123",
            resource_tenant="tenant-abc",
            resource_attributes={"semanticId": "https://example.org/submodel"},
            action=Action.UPDATE,
            client_ip="192.168.1.100",
            environment={"request_id": "req-001"},
        )

        assert ctx.resource_id == "urn:example:submodel:001"
        assert ctx.resource_owner == "user-123"
        assert ctx.action == Action.UPDATE
        assert ctx.client_ip == "192.168.1.100"


class TestAllowOwnerPolicy:
    """Tests for AllowOwnerPolicy."""

    def test_owner_allowed(self, mock_user):
        """Owner of resource is allowed access."""
        policy = AllowOwnerPolicy()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_owner="user-123",  # Same as user.sub
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.ALLOW
        assert "owner" in result.reason.lower()

    def test_non_owner_not_applicable(self, mock_user):
        """Non-owner gets NOT_APPLICABLE (not denied by this policy)."""
        policy = AllowOwnerPolicy()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_owner="other-user",  # Different from user.sub
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE

    def test_no_owner_not_applicable(self, mock_user):
        """No owner specified returns NOT_APPLICABLE."""
        policy = AllowOwnerPolicy()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_owner=None,
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE


class TestTenantIsolationPolicy:
    """Tests for TenantIsolationPolicy."""

    def test_same_tenant_not_applicable(self, mock_user):
        """Same tenant returns NOT_APPLICABLE (allows other policies to decide)."""
        policy = TenantIsolationPolicy()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_tenant="tenant-abc",  # Same as user.tenant_id
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE

    def test_different_tenant_denied(self, mock_user):
        """Different tenant is denied."""
        policy = TenantIsolationPolicy()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_tenant="tenant-xyz",  # Different from user.tenant_id
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY
        assert "mismatch" in result.reason.lower()

    def test_no_tenant_not_applicable(self, mock_user):
        """No tenant context returns NOT_APPLICABLE."""
        policy = TenantIsolationPolicy()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_tenant=None,
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE

    def test_user_without_tenant_denied(self, mock_user):
        """User without tenant assignment is denied when resource has tenant."""
        mock_user.tenant_id = None
        policy = TenantIsolationPolicy()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_tenant="tenant-abc",
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY


class TestTimeBasedPolicy:
    """Tests for TimeBasedPolicy."""

    def test_within_allowed_hours(self, mock_user):
        """Access within allowed hours returns NOT_APPLICABLE."""
        policy = TimeBasedPolicy(allowed_hours=(9, 17))  # 9am-5pm
        # Create a time within allowed hours
        request_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)  # Noon

        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            request_time=request_time,
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE

    def test_outside_allowed_hours(self, mock_user):
        """Access outside allowed hours is denied."""
        policy = TimeBasedPolicy(allowed_hours=(9, 17))  # 9am-5pm
        # Create a time outside allowed hours
        request_time = datetime(2024, 1, 15, 23, 0, 0, tzinfo=timezone.utc)  # 11pm

        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            request_time=request_time,
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY

    def test_day_restriction(self, mock_user):
        """Access on disallowed day is denied."""
        # Only allow weekdays (Mon-Fri = 0-4)
        policy = TimeBasedPolicy(allowed_days=[0, 1, 2, 3, 4])
        # Saturday (weekday 5)
        request_time = datetime(2024, 1, 13, 12, 0, 0, tzinfo=timezone.utc)

        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            request_time=request_time,
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY


class TestIPAllowlistPolicy:
    """Tests for IPAllowlistPolicy."""

    def test_allowed_ip(self, mock_user):
        """IP in allowed network returns NOT_APPLICABLE."""
        policy = IPAllowlistPolicy(allowed_networks=["10.0.0.0/8", "192.168.0.0/16"])
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            client_ip="10.1.2.3",
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE

    def test_blocked_ip(self, mock_user):
        """IP not in allowed network is denied."""
        policy = IPAllowlistPolicy(allowed_networks=["10.0.0.0/8"])
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            client_ip="192.168.1.100",  # Not in 10.0.0.0/8
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY

    def test_no_ip_not_applicable(self, mock_user):
        """No client IP returns NOT_APPLICABLE."""
        policy = IPAllowlistPolicy(allowed_networks=["10.0.0.0/8"])
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            client_ip=None,
        )

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE


class TestCustomPolicy:
    """Tests for CustomPolicy."""

    def test_custom_evaluator(self, mock_user):
        """Custom policy uses provided evaluator."""

        def my_evaluator(ctx: PolicyContext) -> PolicyResult:
            if ctx.user.is_admin:
                return PolicyResult(
                    decision=PolicyDecision.ALLOW,
                    policy_name="admin_bypass",
                    reason="Admin access",
                )
            return PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE,
                policy_name="admin_bypass",
            )

        policy = CustomPolicy(name="admin_bypass", evaluator=my_evaluator)
        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)

        result = policy.evaluate(ctx)

        assert result.decision == PolicyDecision.NOT_APPLICABLE

    def test_custom_priority(self, mock_user):
        """Custom policy can set priority."""
        policy = CustomPolicy(
            name="high_priority",
            evaluator=lambda ctx: PolicyResult(
                decision=PolicyDecision.ALLOW, policy_name="high_priority"
            ),
            priority=1,
        )

        assert policy.priority == 1


class TestABACEngine:
    """Tests for ABACEngine."""

    def test_first_allow_wins(self, mock_user):
        """First policy to ALLOW is returned."""
        allow_policy = CustomPolicy(
            name="always_allow",
            evaluator=lambda ctx: PolicyResult(
                decision=PolicyDecision.ALLOW, policy_name="always_allow"
            ),
            priority=10,
        )
        deny_policy = CustomPolicy(
            name="always_deny",
            evaluator=lambda ctx: PolicyResult(
                decision=PolicyDecision.DENY, policy_name="always_deny"
            ),
            priority=20,
        )

        engine = ABACEngine(policies=[deny_policy, allow_policy])  # Added in wrong order
        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)

        result = engine.evaluate(ctx)

        assert result.decision == PolicyDecision.ALLOW
        assert result.policy_name == "always_allow"

    def test_first_deny_wins(self, mock_user):
        """First policy to DENY is returned."""
        deny_policy = CustomPolicy(
            name="deny_first",
            evaluator=lambda ctx: PolicyResult(
                decision=PolicyDecision.DENY, policy_name="deny_first"
            ),
            priority=5,
        )
        allow_policy = CustomPolicy(
            name="allow_later",
            evaluator=lambda ctx: PolicyResult(
                decision=PolicyDecision.ALLOW, policy_name="allow_later"
            ),
            priority=10,
        )

        engine = ABACEngine(policies=[allow_policy, deny_policy])
        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)

        result = engine.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "deny_first"

    def test_default_deny(self, mock_user):
        """No matching policy results in default deny."""
        na_policy = CustomPolicy(
            name="not_applicable",
            evaluator=lambda ctx: PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE, policy_name="not_applicable"
            ),
        )

        engine = ABACEngine(policies=[na_policy], default_deny=True)
        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)

        result = engine.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "default"

    def test_default_allow(self, mock_user):
        """No matching policy can result in default allow."""
        na_policy = CustomPolicy(
            name="not_applicable",
            evaluator=lambda ctx: PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE, policy_name="not_applicable"
            ),
        )

        engine = ABACEngine(policies=[na_policy], default_deny=False)
        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)

        result = engine.evaluate(ctx)

        assert result.decision == PolicyDecision.ALLOW

    def test_is_allowed(self, mock_user):
        """is_allowed returns boolean."""
        engine = ABACEngine(policies=[], default_deny=False)
        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)

        assert engine.is_allowed(ctx) is True

    def test_add_policy(self, mock_user):
        """Policies can be added dynamically."""
        engine = ABACEngine()

        engine.add_policy(
            CustomPolicy(
                name="allow_all",
                evaluator=lambda ctx: PolicyResult(
                    decision=PolicyDecision.ALLOW, policy_name="allow_all"
                ),
            )
        )

        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)
        assert engine.is_allowed(ctx) is True

    def test_remove_policy(self, mock_user):
        """Policies can be removed by name."""
        engine = ABACEngine(
            policies=[
                CustomPolicy(
                    name="removable",
                    evaluator=lambda ctx: PolicyResult(
                        decision=PolicyDecision.ALLOW, policy_name="removable"
                    ),
                )
            ]
        )

        assert engine.remove_policy("removable") is True
        assert engine.remove_policy("nonexistent") is False

    def test_evaluate_all(self, mock_user):
        """evaluate_all returns all policy results."""
        engine = ABACEngine(
            policies=[
                CustomPolicy(
                    name="p1",
                    evaluator=lambda ctx: PolicyResult(
                        decision=PolicyDecision.NOT_APPLICABLE, policy_name="p1"
                    ),
                ),
                CustomPolicy(
                    name="p2",
                    evaluator=lambda ctx: PolicyResult(
                        decision=PolicyDecision.ALLOW, policy_name="p2"
                    ),
                ),
            ]
        )

        ctx = PolicyContext(user=mock_user, resource_type=ResourceType.AAS)
        results = engine.evaluate_all(ctx)

        assert len(results) == 2
        assert results[0].policy_name == "p1"
        assert results[1].policy_name == "p2"


class TestCreateDefaultEngine:
    """Tests for create_default_engine factory."""

    def test_creates_engine_with_policies(self):
        """Factory creates engine with default policies."""
        engine = create_default_engine()

        assert len(engine.policies) == 2
        assert engine.default_deny is True

    def test_tenant_isolation_included(self, mock_user):
        """Default engine includes tenant isolation."""
        engine = create_default_engine()
        ctx = PolicyContext(
            user=mock_user,
            resource_type=ResourceType.AAS,
            resource_tenant="different-tenant",
        )

        result = engine.evaluate(ctx)

        assert result.decision == PolicyDecision.DENY
        assert result.policy_name == "tenant_isolation"
