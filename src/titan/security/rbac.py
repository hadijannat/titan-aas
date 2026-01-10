"""Role-based access control for Titan-AAS.

Defines roles and permissions for AAS operations:
- Reader: Read-only access to all resources
- Writer: Read and write access
- Admin: Full access including delete and configuration

Permissions are enforced per endpoint via FastAPI dependencies.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.security.oidc import User


class Permission(str, Enum):
    """Permissions for AAS operations."""

    # Read operations
    READ_AAS = "read:aas"
    READ_SUBMODEL = "read:submodel"
    READ_DESCRIPTOR = "read:descriptor"
    READ_CONCEPT_DESCRIPTION = "read:concept_description"

    # Write operations
    CREATE_AAS = "create:aas"
    UPDATE_AAS = "update:aas"
    DELETE_AAS = "delete:aas"
    CREATE_SUBMODEL = "create:submodel"
    UPDATE_SUBMODEL = "update:submodel"
    DELETE_SUBMODEL = "delete:submodel"
    CREATE_DESCRIPTOR = "create:descriptor"
    UPDATE_DESCRIPTOR = "update:descriptor"
    DELETE_DESCRIPTOR = "delete:descriptor"
    CREATE_CONCEPT_DESCRIPTION = "create:concept_description"
    UPDATE_CONCEPT_DESCRIPTION = "update:concept_description"
    DELETE_CONCEPT_DESCRIPTION = "delete:concept_description"

    # Admin operations
    ADMIN = "admin:*"


class Role(str, Enum):
    """Predefined roles with permission sets."""

    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"

    # Titan-prefixed roles (for OIDC)
    TITAN_READ = "titan:read"
    TITAN_WRITE = "titan:write"
    TITAN_ADMIN = "titan:admin"


# Permission mappings for each role
ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    Role.READER.value: {
        Permission.READ_AAS,
        Permission.READ_SUBMODEL,
        Permission.READ_DESCRIPTOR,
        Permission.READ_CONCEPT_DESCRIPTION,
    },
    Role.TITAN_READ.value: {
        Permission.READ_AAS,
        Permission.READ_SUBMODEL,
        Permission.READ_DESCRIPTOR,
        Permission.READ_CONCEPT_DESCRIPTION,
    },
    Role.WRITER.value: {
        Permission.READ_AAS,
        Permission.READ_SUBMODEL,
        Permission.READ_DESCRIPTOR,
        Permission.READ_CONCEPT_DESCRIPTION,
        Permission.CREATE_AAS,
        Permission.UPDATE_AAS,
        Permission.CREATE_SUBMODEL,
        Permission.UPDATE_SUBMODEL,
        Permission.CREATE_DESCRIPTOR,
        Permission.UPDATE_DESCRIPTOR,
        Permission.CREATE_CONCEPT_DESCRIPTION,
        Permission.UPDATE_CONCEPT_DESCRIPTION,
    },
    Role.TITAN_WRITE.value: {
        Permission.READ_AAS,
        Permission.READ_SUBMODEL,
        Permission.READ_DESCRIPTOR,
        Permission.READ_CONCEPT_DESCRIPTION,
        Permission.CREATE_AAS,
        Permission.UPDATE_AAS,
        Permission.CREATE_SUBMODEL,
        Permission.UPDATE_SUBMODEL,
        Permission.CREATE_DESCRIPTOR,
        Permission.UPDATE_DESCRIPTOR,
        Permission.CREATE_CONCEPT_DESCRIPTION,
        Permission.UPDATE_CONCEPT_DESCRIPTION,
    },
    Role.ADMIN.value: set(Permission),
    Role.TITAN_ADMIN.value: set(Permission),
}


class RBACPolicy:
    """Role-based access control policy checker."""

    def __init__(self, role_permissions: dict[str, set[Permission]] | None = None):
        self.role_permissions = role_permissions or ROLE_PERMISSIONS

    def get_user_permissions(self, user: User) -> set[Permission]:
        """Get all permissions for a user based on their roles."""
        permissions: set[Permission] = set()

        for role in user.roles:
            role_perms = self.role_permissions.get(role, set())
            permissions.update(role_perms)

        return permissions

    def has_permission(self, user: User, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        # Admin has all permissions
        if user.is_admin:
            return True

        user_permissions = self.get_user_permissions(user)
        return permission in user_permissions

    def has_any_permission(self, user: User, permissions: list[Permission]) -> bool:
        """Check if user has any of the specified permissions."""
        if user.is_admin:
            return True

        user_permissions = self.get_user_permissions(user)
        return bool(user_permissions.intersection(permissions))

    def has_all_permissions(self, user: User, permissions: list[Permission]) -> bool:
        """Check if user has all of the specified permissions."""
        if user.is_admin:
            return True

        user_permissions = self.get_user_permissions(user)
        return all(p in user_permissions for p in permissions)

    def can_read(self, user: User) -> bool:
        """Check if user can read resources."""
        return user.can_read or self.has_any_permission(
            user,
            [
                Permission.READ_AAS,
                Permission.READ_SUBMODEL,
                Permission.READ_DESCRIPTOR,
            ],
        )

    def can_write(self, user: User) -> bool:
        """Check if user can write resources."""
        return user.can_write or self.has_any_permission(
            user,
            [
                Permission.CREATE_AAS,
                Permission.UPDATE_AAS,
                Permission.CREATE_SUBMODEL,
                Permission.UPDATE_SUBMODEL,
            ],
        )


# Global RBAC policy instance
rbac_policy = RBACPolicy()
