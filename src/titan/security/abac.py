"""Attribute-based access control for Titan-AAS.

ABAC extends RBAC by evaluating policies against attributes:
- User attributes (roles, department, clearance level)
- Resource attributes (owner, classification, type)
- Action attributes (create, read, update, delete)
- Environment attributes (time, IP address, location)

This provides fine-grained access control beyond role-based permissions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from ipaddress import ip_address, ip_network
from typing import Any

from titan.security.oidc import User


class Action(str, Enum):
    """Standard ABAC actions."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    EXECUTE = "execute"


class ResourceType(str, Enum):
    """Resource types in AAS."""

    AAS = "aas"
    SUBMODEL = "submodel"
    SUBMODEL_ELEMENT = "submodel_element"
    CONCEPT_DESCRIPTION = "concept_description"
    DESCRIPTOR = "descriptor"


@dataclass
class PolicyContext:
    """Context for policy evaluation.

    Contains all attributes that policies can evaluate against.
    """

    # User attributes
    user: User

    # Resource attributes
    resource_type: ResourceType
    resource_id: str | None = None
    resource_owner: str | None = None
    resource_tenant: str | None = None
    resource_attributes: dict[str, Any] = field(default_factory=dict)

    # Action being performed
    action: Action = Action.READ

    # Environment attributes
    client_ip: str | None = None
    request_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    environment: dict[str, Any] = field(default_factory=dict)


class PolicyDecision(str, Enum):
    """Result of policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class PolicyResult:
    """Result of a policy evaluation."""

    decision: PolicyDecision
    policy_name: str
    reason: str | None = None


class ABACPolicy(ABC):
    """Abstract base class for ABAC policies.

    Policies are evaluated in order. The first policy to return
    ALLOW or DENY determines the outcome. NOT_APPLICABLE policies
    are skipped.
    """

    name: str = "unnamed_policy"
    priority: int = 100  # Lower = higher priority

    @abstractmethod
    def evaluate(self, context: PolicyContext) -> PolicyResult:
        """Evaluate the policy against the context.

        Args:
            context: The policy evaluation context

        Returns:
            PolicyResult with the decision
        """
        pass


class AllowOwnerPolicy(ABACPolicy):
    """Allow resource owners full access to their resources."""

    name = "allow_owner"
    priority = 10

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        if context.resource_owner is None:
            return PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE,
                policy_name=self.name,
                reason="No resource owner specified",
            )

        if context.user.sub == context.resource_owner:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                policy_name=self.name,
                reason="User is resource owner",
            )

        return PolicyResult(
            decision=PolicyDecision.NOT_APPLICABLE,
            policy_name=self.name,
            reason="User is not resource owner",
        )


class TenantIsolationPolicy(ABACPolicy):
    """Enforce tenant isolation - users can only access their tenant's resources."""

    name = "tenant_isolation"
    priority = 5

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        if context.resource_tenant is None:
            return PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE,
                policy_name=self.name,
                reason="No tenant context",
            )

        user_tenant = context.user.tenant_id
        if user_tenant is None:
            return PolicyResult(
                decision=PolicyDecision.DENY,
                policy_name=self.name,
                reason="User has no tenant assignment",
            )

        if user_tenant == context.resource_tenant:
            return PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE,
                policy_name=self.name,
                reason="Same tenant",
            )

        return PolicyResult(
            decision=PolicyDecision.DENY,
            policy_name=self.name,
            reason=f"Tenant mismatch: user={user_tenant}, resource={context.resource_tenant}",
        )


class TimeBasedPolicy(ABACPolicy):
    """Restrict access based on time of day."""

    name = "time_based"
    priority = 50

    def __init__(
        self,
        allowed_hours: tuple[int, int] = (0, 24),
        allowed_days: list[int] | None = None,
    ):
        """Initialize time-based policy.

        Args:
            allowed_hours: Tuple of (start_hour, end_hour) in UTC
            allowed_days: List of allowed weekdays (0=Monday, 6=Sunday).
                         None means all days allowed.
        """
        self.allowed_hours = allowed_hours
        self.allowed_days = allowed_days

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        request_time = context.request_time
        current_hour = request_time.hour
        current_day = request_time.weekday()

        # Check day restriction
        if self.allowed_days is not None and current_day not in self.allowed_days:
            return PolicyResult(
                decision=PolicyDecision.DENY,
                policy_name=self.name,
                reason=f"Access denied on day {current_day}",
            )

        # Check hour restriction
        start_hour, end_hour = self.allowed_hours
        if not (start_hour <= current_hour < end_hour):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                policy_name=self.name,
                reason=f"Access denied at hour {current_hour}",
            )

        return PolicyResult(
            decision=PolicyDecision.NOT_APPLICABLE,
            policy_name=self.name,
            reason="Within allowed time window",
        )


class IPAllowlistPolicy(ABACPolicy):
    """Restrict access to specific IP ranges."""

    name = "ip_allowlist"
    priority = 20

    def __init__(self, allowed_networks: list[str]):
        """Initialize IP allowlist policy.

        Args:
            allowed_networks: List of CIDR notation networks (e.g., ["10.0.0.0/8"])
        """
        self.allowed_networks = [ip_network(net) for net in allowed_networks]

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        if context.client_ip is None:
            return PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE,
                policy_name=self.name,
                reason="No client IP available",
            )

        try:
            client = ip_address(context.client_ip)
        except ValueError:
            return PolicyResult(
                decision=PolicyDecision.DENY,
                policy_name=self.name,
                reason=f"Invalid IP address: {context.client_ip}",
            )

        for network in self.allowed_networks:
            if client in network:
                return PolicyResult(
                    decision=PolicyDecision.NOT_APPLICABLE,
                    policy_name=self.name,
                    reason="IP in allowed network",
                )

        return PolicyResult(
            decision=PolicyDecision.DENY,
            policy_name=self.name,
            reason=f"IP {context.client_ip} not in allowed networks",
        )


class ResourceTypePolicy(ABACPolicy):
    """Restrict access to specific resource types per action."""

    name = "resource_type"
    priority = 30

    def __init__(
        self,
        allowed_resources: dict[Action, set[ResourceType]],
    ):
        """Initialize resource type policy.

        Args:
            allowed_resources: Mapping of actions to allowed resource types
        """
        self.allowed_resources = allowed_resources

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        allowed = self.allowed_resources.get(context.action, set())

        if not allowed:
            # No restriction for this action
            return PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE,
                policy_name=self.name,
                reason=f"No restriction for action {context.action}",
            )

        if context.resource_type in allowed:
            return PolicyResult(
                decision=PolicyDecision.NOT_APPLICABLE,
                policy_name=self.name,
                reason="Resource type allowed for action",
            )

        return PolicyResult(
            decision=PolicyDecision.DENY,
            policy_name=self.name,
            reason=f"Resource type {context.resource_type} not allowed for {context.action}",
        )


class CustomPolicy(ABACPolicy):
    """Custom policy using a callable function."""

    def __init__(
        self,
        name: str,
        evaluator: Callable[[PolicyContext], PolicyResult],
        priority: int = 100,
    ):
        self.name = name
        self.priority = priority
        self._evaluator = evaluator

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        return self._evaluator(context)


class ABACEngine:
    """Engine for evaluating ABAC policies.

    Policies are evaluated in priority order (lower = higher priority).
    The first ALLOW or DENY result is returned.
    If all policies return NOT_APPLICABLE, access is denied by default.
    """

    def __init__(
        self,
        policies: list[ABACPolicy] | None = None,
        default_deny: bool = True,
    ):
        """Initialize ABAC engine.

        Args:
            policies: List of policies to evaluate
            default_deny: If True, deny when no policy matches
        """
        self.policies = policies or []
        self.default_deny = default_deny
        # Sort by priority
        self.policies.sort(key=lambda p: p.priority)

    def add_policy(self, policy: ABACPolicy) -> None:
        """Add a policy to the engine."""
        self.policies.append(policy)
        self.policies.sort(key=lambda p: p.priority)

    def remove_policy(self, name: str) -> bool:
        """Remove a policy by name.

        Returns True if policy was found and removed.
        """
        for i, policy in enumerate(self.policies):
            if policy.name == name:
                del self.policies[i]
                return True
        return False

    def is_allowed(self, context: PolicyContext) -> bool:
        """Check if access is allowed.

        Args:
            context: The policy evaluation context

        Returns:
            True if access is allowed, False otherwise
        """
        result = self.evaluate(context)
        return result.decision == PolicyDecision.ALLOW

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        """Evaluate all policies and return the final decision.

        Args:
            context: The policy evaluation context

        Returns:
            PolicyResult with the final decision
        """
        for policy in self.policies:
            result = policy.evaluate(context)

            if result.decision in (PolicyDecision.ALLOW, PolicyDecision.DENY):
                return result

        # No policy made a decision
        if self.default_deny:
            return PolicyResult(
                decision=PolicyDecision.DENY,
                policy_name="default",
                reason="No policy allowed access (default deny)",
            )
        else:
            return PolicyResult(
                decision=PolicyDecision.ALLOW,
                policy_name="default",
                reason="No policy denied access (default allow)",
            )

    def evaluate_all(self, context: PolicyContext) -> list[PolicyResult]:
        """Evaluate all policies and return all results.

        Useful for debugging and audit logging.

        Args:
            context: The policy evaluation context

        Returns:
            List of all policy results
        """
        return [policy.evaluate(context) for policy in self.policies]


# Default engine with common policies
def create_default_engine() -> ABACEngine:
    """Create an ABAC engine with default policies."""
    return ABACEngine(
        policies=[
            TenantIsolationPolicy(),
            AllowOwnerPolicy(),
        ],
        default_deny=True,
    )
