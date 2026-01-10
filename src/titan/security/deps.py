"""FastAPI security dependencies for Titan-AAS.

Provides injectable dependencies for authentication and authorization:
- get_current_user: Extract and validate user from request
- require_read: Require read permission
- require_write: Require write permission
- require_admin: Require admin role

Usage:
    @router.get("/shells")
    async def get_shells(user: User = Depends(require_read)):
        ...
"""

from __future__ import annotations

from typing import Annotated, Awaitable, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from titan.config import settings
from titan.security.abac import (
    ABACEngine,
    Action,
    PolicyContext,
    PolicyDecision,
    ResourceType,
    create_default_engine,
)
from titan.security.oidc import InvalidTokenError, User, get_token_validator
from titan.security.rbac import Permission, rbac_policy
from titan.tenancy.context import get_current_tenant_or_none

_ABAC_ENGINE: ABACEngine | None = None


def _get_abac_engine() -> ABACEngine | None:
    """Return ABAC engine if enabled."""
    global _ABAC_ENGINE
    if not settings.enable_abac:
        return None
    if _ABAC_ENGINE is None:
        _ABAC_ENGINE = create_default_engine()
        _ABAC_ENGINE.default_deny = settings.abac_default_deny
    return _ABAC_ENGINE


def _get_client_ip(request: Request) -> str | None:
    """Extract client IP considering common proxy headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None


def _get_resource_tenant(request: Request) -> str | None:
    """Resolve tenant ID from context or headers."""
    tenant_id = get_current_tenant_or_none()
    if tenant_id:
        return tenant_id
    return request.headers.get("X-Tenant-ID")


def _get_resource_id(request: Request, params: list[str] | None) -> str | None:
    """Build a resource identifier from path params."""
    if not params:
        return None
    parts: list[str] = []
    for param in params:
        value = request.path_params.get(param)
        if value is not None:
            parts.append(str(value))
    if not parts:
        return None
    return "/".join(parts)


def _permission_to_abac(permission: Permission) -> tuple[Action, ResourceType]:
    """Map RBAC permission to ABAC action and resource type."""
    mapping: dict[Permission, tuple[Action, ResourceType]] = {
        Permission.READ_AAS: (Action.READ, ResourceType.AAS),
        Permission.CREATE_AAS: (Action.CREATE, ResourceType.AAS),
        Permission.UPDATE_AAS: (Action.UPDATE, ResourceType.AAS),
        Permission.DELETE_AAS: (Action.DELETE, ResourceType.AAS),
        Permission.READ_SUBMODEL: (Action.READ, ResourceType.SUBMODEL),
        Permission.CREATE_SUBMODEL: (Action.CREATE, ResourceType.SUBMODEL),
        Permission.UPDATE_SUBMODEL: (Action.UPDATE, ResourceType.SUBMODEL),
        Permission.DELETE_SUBMODEL: (Action.DELETE, ResourceType.SUBMODEL),
        Permission.READ_DESCRIPTOR: (Action.READ, ResourceType.DESCRIPTOR),
        Permission.CREATE_DESCRIPTOR: (Action.CREATE, ResourceType.DESCRIPTOR),
        Permission.UPDATE_DESCRIPTOR: (Action.UPDATE, ResourceType.DESCRIPTOR),
        Permission.DELETE_DESCRIPTOR: (Action.DELETE, ResourceType.DESCRIPTOR),
        Permission.READ_CONCEPT_DESCRIPTION: (Action.READ, ResourceType.CONCEPT_DESCRIPTION),
        Permission.CREATE_CONCEPT_DESCRIPTION: (Action.CREATE, ResourceType.CONCEPT_DESCRIPTION),
        Permission.UPDATE_CONCEPT_DESCRIPTION: (Action.UPDATE, ResourceType.CONCEPT_DESCRIPTION),
        Permission.DELETE_CONCEPT_DESCRIPTION: (Action.DELETE, ResourceType.CONCEPT_DESCRIPTION),
        Permission.ADMIN: (Action.READ, ResourceType.AAS),
    }
    return mapping.get(permission, (Action.READ, ResourceType.AAS))


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """Extract and validate user from Authorization header.

    Returns None if:
    - OIDC is not configured (authentication disabled)
    - No Authorization header provided

    Raises HTTPException if token is invalid.
    """
    validator = get_token_validator()

    # If OIDC not configured, authentication is disabled
    if validator is None:
        return None

    # No token provided
    if authorization is None:
        return None

    # Extract token from Bearer scheme
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    try:
        user = await validator.validate_token(token)
        request.state.user = user
        return user
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    user: Annotated[User | None, Depends(get_current_user)],
) -> User | None:
    """Get current user if authenticated, None otherwise."""
    return user


async def require_authenticated(
    request: Request,
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """Require authenticated user.

    Raises 401 if not authenticated.
    """
    validator = get_token_validator()

    # If OIDC not configured, create anonymous user with full access
    if validator is None:
        anon = User(
            sub="anonymous",
            name="Anonymous",
            roles=["admin"],  # Full access when auth disabled
        )
        request.state.user = anon
        return anon

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user = user
    return user


async def require_read(
    user: Annotated[User, Depends(require_authenticated)],
) -> User:
    """Require read permission.

    Raises 403 if user doesn't have read permission.
    """
    if not rbac_policy.can_read(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read permission required",
        )
    return user


async def require_write(
    user: Annotated[User, Depends(require_authenticated)],
) -> User:
    """Require write permission.

    Raises 403 if user doesn't have write permission.
    """
    if not rbac_policy.can_write(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write permission required",
        )
    return user


async def require_admin(
    user: Annotated[User, Depends(require_authenticated)],
) -> User:
    """Require admin role.

    Raises 403 if user is not admin.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


def require_permission(
    permission: Permission,
    resource_type: ResourceType | None = None,
    resource_id_params: list[str] | None = None,
) -> Callable[[User], Awaitable[User]]:
    """Create dependency that requires a specific permission.

    Usage:
        @router.delete("/shells/{id}")
        async def delete_shell(
            user: User = Depends(require_permission(Permission.DELETE_AAS))
        ):
            ...
    """

    async def _require_permission(
        request: Request,
        user: Annotated[User, Depends(require_authenticated)],
    ) -> User:
        if not rbac_policy.has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' required",
            )

        engine = _get_abac_engine()
        if engine is not None and not user.is_admin:
            action, mapped_type = _permission_to_abac(permission)
            resolved_type = resource_type or mapped_type
            context = PolicyContext(
                user=user,
                resource_type=resolved_type,
                resource_id=_get_resource_id(request, resource_id_params),
                resource_tenant=_get_resource_tenant(request),
                action=action,
                client_ip=_get_client_ip(request),
            )
            decision = engine.evaluate(context)
            if decision.decision == PolicyDecision.DENY:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"ABAC denied: {decision.reason or 'access denied'}",
                )
        return user

    return _require_permission
