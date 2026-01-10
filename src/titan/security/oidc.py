"""OIDC token validation for Titan-AAS.

Validates JWT tokens from OIDC providers (Keycloak, Auth0, Azure AD, etc.).
Supports:
- JWT signature verification with JWKS
- Token expiry validation
- Issuer and audience validation
- Role extraction from claims
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from titan.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OIDCConfig:
    """OIDC provider configuration."""

    issuer: str
    audience: str
    jwks_uri: str | None = None
    roles_claim: str = "roles"
    client_id: str | None = None
    jwks_cache_seconds: int = 3600

    def __post_init__(self) -> None:
        """Set JWKS URI from issuer if not provided."""
        if self.jwks_uri is None:
            self.jwks_uri = f"{self.issuer.rstrip('/')}/.well-known/jwks.json"


@dataclass
class User:
    """Authenticated user from JWT token."""

    sub: str  # Subject (user ID)
    email: str | None = None
    name: str | None = None
    roles: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return "admin" in self.roles or "titan:admin" in self.roles

    @property
    def can_read(self) -> bool:
        """Check if user has read permission."""
        return (
            self.is_admin
            or "reader" in self.roles
            or "titan:read" in self.roles
            or "titan:write" in self.roles
        )

    @property
    def can_write(self) -> bool:
        """Check if user has write permission."""
        return self.is_admin or "writer" in self.roles or "titan:write" in self.roles


class TokenValidator:
    """Validates JWT tokens from OIDC provider."""

    def __init__(self, config: OIDCConfig):
        self.config = config
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at: datetime | None = None

    async def validate_token(self, token: str) -> User:
        """Validate JWT token and return user.

        Args:
            token: The JWT access token (without "Bearer " prefix)

        Returns:
            User object with claims

        Raises:
            InvalidTokenError: If token is invalid
        """
        # Get JWKS keys
        jwks = await self._get_jwks()

        try:
            # Decode and verify token
            payload = jwt.decode(
                token,
                jwks,
                algorithms=["RS256", "ES256"],
                audience=self.config.audience,
                issuer=self.config.issuer,
                options={"verify_exp": True},
            )
        except ExpiredSignatureError as e:
            raise InvalidTokenError("Token has expired") from e
        except JWTError as e:
            raise InvalidTokenError(f"Invalid token: {e}") from e

        # Extract user info
        return User(
            sub=payload.get("sub", ""),
            email=payload.get("email"),
            name=payload.get("name") or payload.get("preferred_username"),
            roles=self._extract_roles(payload),
            tenant_id=payload.get("tenant_id") or payload.get("tenant"),
            claims=payload,
        )

    def _extract_roles(self, payload: dict[str, Any]) -> list[str]:
        """Extract roles from token claims."""
        roles: list[str] = []

        # Try configured roles claim
        claim_value = payload.get(self.config.roles_claim)
        if isinstance(claim_value, list):
            roles.extend(claim_value)
        elif isinstance(claim_value, str):
            roles.append(claim_value)

        # Try nested realm_access.roles (Keycloak)
        realm_access = payload.get("realm_access", {})
        if isinstance(realm_access, dict):
            realm_roles = realm_access.get("roles", [])
            if isinstance(realm_roles, list):
                roles.extend(realm_roles)

        # Try resource_access (Keycloak client roles)
        if self.config.client_id:
            resource_access = payload.get("resource_access", {})
            client_access = resource_access.get(self.config.client_id, {})
            if isinstance(client_access, dict):
                client_roles = client_access.get("roles", [])
                if isinstance(client_roles, list):
                    roles.extend(client_roles)

        return list(set(roles))  # Deduplicate

    async def _get_jwks(self) -> dict[str, Any]:
        """Get JWKS keys, with caching."""
        # Check if we need to refresh (cache with configurable TTL)
        now = datetime.now(UTC)
        if self._jwks is not None and self._jwks_fetched_at is not None:
            age = (now - self._jwks_fetched_at).total_seconds()
            if age < self.config.jwks_cache_seconds:
                assert self._jwks is not None
                return self._jwks

        # Fetch JWKS
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.config.jwks_uri,  # type: ignore
                    timeout=10.0,
                )
                response.raise_for_status()
                self._jwks = response.json()
                self._jwks_fetched_at = now
                logger.info(f"Fetched JWKS from {self.config.jwks_uri}")
                return self._jwks
        except Exception as e:
            if self._jwks is not None:
                logger.warning(f"Failed to refresh JWKS, using cached: {e}")
                assert self._jwks is not None
                return self._jwks
            raise InvalidTokenError(f"Failed to fetch JWKS: {e}") from e


class InvalidTokenError(Exception):
    """Raised when token validation fails."""

    pass


# Global validator instance (configured lazily)
_validator: TokenValidator | None = None


def get_token_validator() -> TokenValidator | None:
    """Get the global token validator.

    Returns None if OIDC is not configured.
    """
    global _validator

    if not settings.oidc_issuer:
        return None

    if _validator is None:
        config = OIDCConfig(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience or settings.app_name,
            roles_claim=settings.oidc_roles_claim or "roles",
            client_id=settings.oidc_client_id,
            jwks_cache_seconds=settings.oidc_jwks_cache_seconds,
        )
        _validator = TokenValidator(config)

    return _validator
