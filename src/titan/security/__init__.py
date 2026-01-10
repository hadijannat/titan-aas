"""Security module for Titan-AAS.

Provides authentication and authorization:
- OIDC: Token validation with JWT
- RBAC: Role-based access control
- ABAC: Attribute-based access control (future)
"""

from titan.security.deps import (
    get_current_user,
    require_admin,
    require_read,
    require_write,
)
from titan.security.oidc import OIDCConfig, TokenValidator, User
from titan.security.rbac import Permission, RBACPolicy, Role

__all__ = [
    # OIDC
    "OIDCConfig",
    "TokenValidator",
    "User",
    # RBAC
    "Permission",
    "Role",
    "RBACPolicy",
    # Dependencies
    "get_current_user",
    "require_read",
    "require_write",
    "require_admin",
]
