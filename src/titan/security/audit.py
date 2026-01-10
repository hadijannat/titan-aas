"""Audit logging for security-relevant operations.

Provides structured audit logging for:
- Authentication events (login, logout, token refresh)
- Authorization events (access granted/denied)
- Data access events (read, create, update, delete)
- Administrative events (config changes, user management)

Audit logs are:
- Immutable (append-only)
- Structured (JSON format)
- Traceable (correlation IDs, user IDs)
- Compliant (ISO 27001, SOC 2 ready)

Example:
    from titan.security.audit import audit_log, AuditAction, AuditResource

    # Log a data access event
    await audit_log.log(
        action=AuditAction.READ,
        resource=AuditResource.SUBMODEL,
        resource_id="urn:example:sm:1",
        user_id="user@example.com",
        success=True,
    )
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

# Dedicated audit logger - separate from application logs
audit_logger = logging.getLogger("titan.audit")


class AuditAction(str, Enum):
    """Type of auditable action."""

    # Authentication
    LOGIN = "login"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    AUTH_FAILURE = "auth_failure"

    # Authorization
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"

    # Data operations
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    IMPORT = "import"

    # Administrative
    CONFIG_CHANGE = "config_change"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    ROLE_ASSIGN = "role_assign"
    ROLE_REVOKE = "role_revoke"

    # System
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    ERROR = "error"


class AuditResource(str, Enum):
    """Type of resource being accessed."""

    AAS = "aas"
    SUBMODEL = "submodel"
    SUBMODEL_ELEMENT = "submodel_element"
    CONCEPT_DESCRIPTION = "concept_description"
    SHELL_DESCRIPTOR = "shell_descriptor"
    SUBMODEL_DESCRIPTOR = "submodel_descriptor"
    USER = "user"
    ROLE = "role"
    CONFIG = "config"
    SYSTEM = "system"


@dataclass
class AuditEvent:
    """Structured audit event."""

    # Event identification
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Action details
    action: AuditAction = AuditAction.READ
    resource: AuditResource = AuditResource.SYSTEM
    resource_id: str | None = None
    success: bool = True

    # Actor identification
    user_id: str | None = None
    user_roles: list[str] = field(default_factory=list)
    client_ip: str | None = None
    user_agent: str | None = None

    # Request context
    request_id: str | None = None
    correlation_id: str | None = None
    http_method: str | None = None
    http_path: str | None = None
    http_status: int | None = None

    # Additional context
    details: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    # Environment
    instance_id: str = field(default_factory=lambda: os.environ.get("HOSTNAME", "unknown"))
    environment: str = field(default_factory=lambda: os.environ.get("ENV", "development"))

    def to_json(self) -> str:
        """Convert to JSON string for logging."""
        data = asdict(self)
        # Handle datetime serialization
        data["timestamp"] = data["timestamp"].isoformat()
        # Handle enum serialization
        data["action"] = data["action"].value if data["action"] else None
        data["resource"] = data["resource"].value if data["resource"] else None
        return json.dumps(data, default=str)


class AuditLog:
    """Audit logging service.

    Provides methods for logging security-relevant events with
    structured data. Events are logged to a dedicated audit logger
    that can be configured to write to various destinations:
    - File (append-only, rotated)
    - Syslog
    - Cloud logging services
    - SIEM systems
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or audit_logger

    async def log(
        self,
        action: AuditAction,
        resource: AuditResource = AuditResource.SYSTEM,
        resource_id: str | None = None,
        success: bool = True,
        user_id: str | None = None,
        user_roles: list[str] | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        correlation_id: str | None = None,
        http_method: str | None = None,
        http_path: str | None = None,
        http_status: int | None = None,
        details: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> AuditEvent:
        """Log an audit event.

        Args:
            action: The action being performed
            resource: The type of resource being accessed
            resource_id: Unique identifier of the resource
            success: Whether the action succeeded
            user_id: ID of the user performing the action
            user_roles: Roles assigned to the user
            client_ip: IP address of the client
            user_agent: User agent string
            request_id: Unique ID for this request
            correlation_id: ID for correlating related requests
            http_method: HTTP method (GET, POST, etc.)
            http_path: HTTP request path
            http_status: HTTP response status code
            details: Additional context about the event
            error_message: Error message if action failed

        Returns:
            The created AuditEvent
        """
        event = AuditEvent(
            action=action,
            resource=resource,
            resource_id=resource_id,
            success=success,
            user_id=user_id,
            user_roles=user_roles or [],
            client_ip=client_ip,
            user_agent=user_agent,
            request_id=request_id,
            correlation_id=correlation_id,
            http_method=http_method,
            http_path=http_path,
            http_status=http_status,
            details=details or {},
            error_message=error_message,
        )

        # Log at appropriate level based on action type
        log_level = self._get_log_level(action, success)
        self.logger.log(log_level, event.to_json())

        return event

    def _get_log_level(self, action: AuditAction, success: bool) -> int:
        """Determine log level based on action type and success."""
        if not success:
            if action in (AuditAction.AUTH_FAILURE, AuditAction.ACCESS_DENIED):
                return logging.WARNING
            return logging.ERROR

        if action in (
            AuditAction.DELETE,
            AuditAction.CONFIG_CHANGE,
            AuditAction.USER_DELETE,
            AuditAction.ROLE_REVOKE,
        ):
            return logging.WARNING

        return logging.INFO

    # Convenience methods for common operations

    async def log_auth_success(
        self,
        user_id: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        **kwargs: Any,
    ) -> AuditEvent:
        """Log a successful authentication."""
        return await self.log(
            action=AuditAction.LOGIN,
            resource=AuditResource.USER,
            resource_id=user_id,
            success=True,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            **kwargs,
        )

    async def log_auth_failure(
        self,
        user_id: str | None,
        reason: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        **kwargs: Any,
    ) -> AuditEvent:
        """Log a failed authentication attempt."""
        return await self.log(
            action=AuditAction.AUTH_FAILURE,
            resource=AuditResource.USER,
            resource_id=user_id,
            success=False,
            user_id=user_id,
            client_ip=client_ip,
            user_agent=user_agent,
            error_message=reason,
            **kwargs,
        )

    async def log_access_denied(
        self,
        user_id: str,
        resource: AuditResource,
        resource_id: str,
        required_permission: str,
        **kwargs: Any,
    ) -> AuditEvent:
        """Log an access denied event."""
        return await self.log(
            action=AuditAction.ACCESS_DENIED,
            resource=resource,
            resource_id=resource_id,
            success=False,
            user_id=user_id,
            details={"required_permission": required_permission},
            **kwargs,
        )

    async def log_data_access(
        self,
        action: AuditAction,
        resource: AuditResource,
        resource_id: str,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> AuditEvent:
        """Log a data access event (CRUD operation)."""
        return await self.log(
            action=action,
            resource=resource,
            resource_id=resource_id,
            success=True,
            user_id=user_id,
            **kwargs,
        )


# Singleton audit log instance
_audit_log: AuditLog | None = None


def get_audit_log() -> AuditLog:
    """Get the global audit log instance."""
    global _audit_log
    if _audit_log is None:
        _audit_log = AuditLog()
    return _audit_log


# Configure audit logger
def configure_audit_logging(
    log_file: str | None = None,
    log_format: str = "%(message)s",  # Just the JSON for audit logs
    level: int = logging.INFO,
) -> None:
    """Configure the audit logger.

    Args:
        log_file: Path to audit log file (None for stdout)
        log_format: Log format string
        level: Logging level
    """
    audit_logger.setLevel(level)
    audit_logger.propagate = False  # Don't propagate to root logger

    formatter = logging.Formatter(log_format)

    handler: logging.Handler
    if log_file:
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(
            log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=10,
        )
    else:
        handler = logging.StreamHandler()

    handler.setFormatter(formatter)
    audit_logger.addHandler(handler)
