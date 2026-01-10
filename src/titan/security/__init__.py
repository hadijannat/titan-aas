"""Security module for Titan-AAS.

Provides authentication and authorization:
- OIDC: Token validation with JWT
- RBAC: Role-based access control
- ABAC: Attribute-based access control (future)
- Audit: Security event logging
- Signing: Request signature verification
"""

from titan.security.audit import (
    AuditAction,
    AuditEvent,
    AuditLog,
    AuditResource,
    configure_audit_logging,
    get_audit_log,
)
from titan.security.deps import (
    get_current_user,
    require_admin,
    require_read,
    require_write,
)
from titan.security.oidc import OIDCConfig, TokenValidator, User
from titan.security.rbac import Permission, RBACPolicy, Role
from titan.security.signing import (
    RequestSigner,
    RequestVerifier,
    SignatureMiddleware,
    generate_secret_key,
)

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
    # Audit
    "AuditAction",
    "AuditResource",
    "AuditEvent",
    "AuditLog",
    "get_audit_log",
    "configure_audit_logging",
    # Signing
    "RequestSigner",
    "RequestVerifier",
    "SignatureMiddleware",
    "generate_secret_key",
]
