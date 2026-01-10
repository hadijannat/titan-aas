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

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from titan.config import settings
from titan.security.oidc import InvalidTokenError, User, get_token_validator
from titan.security.rbac import Permission, rbac_policy


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
    user: Annotated[User | None, Depends(get_current_user)],
) -> User:
    """Require authenticated user.

    Raises 401 if not authenticated.
    """
    validator = get_token_validator()

    # If OIDC not configured, create anonymous user with full access
    if validator is None:
        return User(
            sub="anonymous",
            name="Anonymous",
            roles=["admin"],  # Full access when auth disabled
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


def require_permission(permission: Permission):
    """Create dependency that requires a specific permission.

    Usage:
        @router.delete("/shells/{id}")
        async def delete_shell(
            user: User = Depends(require_permission(Permission.DELETE_AAS))
        ):
            ...
    """

    async def _require_permission(
        user: Annotated[User, Depends(require_authenticated)],
    ) -> User:
        if not rbac_policy.has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' required",
            )
        return user

    return _require_permission
