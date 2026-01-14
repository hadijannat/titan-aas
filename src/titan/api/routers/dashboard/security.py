"""Dashboard security endpoints - Audit logs and session management.

Provides:
- Audit log search and filtering
- Active session listing
- Session revocation
- Authentication statistics
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from titan.security.deps import require_permission
from titan.security.rbac import Permission

router = APIRouter(prefix="/security", tags=["Dashboard - Security"])


class AuditEntry(BaseModel):
    """A single audit log entry."""

    id: str
    timestamp: datetime
    user_id: str | None = None
    user_email: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    success: bool = True


class AuditLogResponse(BaseModel):
    """Paginated audit log response."""

    entries: list[AuditEntry]
    total: int
    has_more: bool


class ActiveSession(BaseModel):
    """An active user session."""

    session_id: str
    user_id: str
    user_email: str | None = None
    created_at: datetime
    last_activity: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    expires_at: datetime | None = None


class SessionsResponse(BaseModel):
    """List of active sessions."""

    sessions: list[ActiveSession]
    total: int


class AuthStats(BaseModel):
    """Authentication statistics."""

    timestamp: datetime
    total_logins_24h: int
    failed_logins_24h: int
    active_sessions: int
    unique_users_24h: int


# In-memory audit log storage (would be backed by database in production)
_audit_log: list[AuditEntry] = []
_active_sessions: dict[str, ActiveSession] = {}


def add_audit_entry(
    action: str,
    user_id: str | None = None,
    user_email: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    success: bool = True,
) -> None:
    """Add an entry to the audit log.

    Called by security middleware to log actions.
    """
    entry = AuditEntry(
        id=str(len(_audit_log) + 1),
        timestamp=datetime.utcnow(),
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
    )
    _audit_log.append(entry)

    # Keep only last 10000 entries in memory
    if len(_audit_log) > 10000:
        _audit_log.pop(0)


def register_session(
    session_id: str,
    user_id: str,
    user_email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    """Register an active session.

    Called when a user authenticates.
    """
    now = datetime.utcnow()
    _active_sessions[session_id] = ActiveSession(
        session_id=session_id,
        user_id=user_id,
        user_email=user_email,
        created_at=now,
        last_activity=now,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at,
    )


def update_session_activity(session_id: str) -> None:
    """Update last activity timestamp for a session."""
    if session_id in _active_sessions:
        _active_sessions[session_id].last_activity = datetime.utcnow()


def remove_session(session_id: str) -> bool:
    """Remove a session (logout or revocation)."""
    if session_id in _active_sessions:
        del _active_sessions[session_id]
        return True
    return False


@router.get(
    "/audit-log",
    response_model=AuditLogResponse,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_audit_log(
    from_time: datetime | None = Query(None, description="Start time filter"),
    to_time: datetime | None = Query(None, description="End time filter"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    user_email: str | None = Query(None, description="Filter by user email"),
    action: str | None = Query(None, description="Filter by action type"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    success: bool | None = Query(None, description="Filter by success/failure"),
    limit: int = Query(default=50, le=500, description="Maximum entries to return"),
    offset: int = Query(default=0, description="Offset for pagination"),
) -> AuditLogResponse:
    """Search and filter audit log entries.

    Returns audit entries matching the specified filters.
    Entries are returned in reverse chronological order (newest first).
    """
    # Filter entries
    filtered = _audit_log.copy()

    if from_time:
        filtered = [e for e in filtered if e.timestamp >= from_time]
    if to_time:
        filtered = [e for e in filtered if e.timestamp <= to_time]
    if user_id:
        filtered = [e for e in filtered if e.user_id == user_id]
    if user_email:
        filtered = [
            e for e in filtered if e.user_email and user_email.lower() in e.user_email.lower()
        ]
    if action:
        filtered = [e for e in filtered if action.lower() in e.action.lower()]
    if resource_type:
        filtered = [e for e in filtered if e.resource_type == resource_type]
    if success is not None:
        filtered = [e for e in filtered if e.success == success]

    # Sort by timestamp descending
    filtered.sort(key=lambda e: e.timestamp, reverse=True)

    total = len(filtered)
    entries = filtered[offset : offset + limit]

    return AuditLogResponse(
        entries=entries,
        total=total,
        has_more=offset + limit < total,
    )


@router.get(
    "/sessions",
    response_model=SessionsResponse,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_active_sessions(
    user_id: str | None = Query(None, description="Filter by user ID"),
) -> SessionsResponse:
    """Get list of active sessions.

    Returns all active sessions, optionally filtered by user ID.
    """
    sessions = list(_active_sessions.values())

    if user_id:
        sessions = [s for s in sessions if s.user_id == user_id]

    # Sort by last activity descending
    sessions.sort(key=lambda s: s.last_activity, reverse=True)

    return SessionsResponse(
        sessions=sessions,
        total=len(sessions),
    )


@router.delete(
    "/sessions/{session_id}",
    dependencies=[Depends(require_permission(Permission.DELETE_AAS))],
)
async def revoke_session(session_id: str) -> dict[str, Any]:
    """Revoke (terminate) a session.

    Forcibly logs out the user associated with this session.
    """
    if remove_session(session_id):
        add_audit_entry(
            action="SESSION_REVOKED",
            details={"session_id": session_id},
        )
        return {
            "success": True,
            "message": f"Session {session_id} revoked",
            "timestamp": datetime.utcnow().isoformat(),
        }
    else:
        return {
            "success": False,
            "message": f"Session {session_id} not found",
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get(
    "/stats",
    response_model=AuthStats,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_auth_stats() -> AuthStats:
    """Get authentication statistics for the last 24 hours."""
    now = datetime.utcnow()
    day_ago = datetime(now.year, now.month, now.day, now.hour, now.minute, now.second)
    # Subtract 24 hours manually
    from datetime import timedelta

    day_ago = now - timedelta(hours=24)

    # Count logins in last 24h
    recent_entries = [e for e in _audit_log if e.timestamp >= day_ago]
    logins = [e for e in recent_entries if "LOGIN" in e.action.upper()]
    failed_logins = [e for e in logins if not e.success]
    unique_users = {e.user_id for e in logins if e.user_id}

    return AuthStats(
        timestamp=now,
        total_logins_24h=len(logins),
        failed_logins_24h=len(failed_logins),
        active_sessions=len(_active_sessions),
        unique_users_24h=len(unique_users),
    )


@router.get(
    "/permissions",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def list_permissions() -> dict[str, Any]:
    """List all available permissions in the system."""
    permissions = [
        {
            "name": p.name,
            "value": p.value,
            "description": _get_permission_description(p),
        }
        for p in Permission
    ]

    return {
        "permissions": permissions,
        "total": len(permissions),
    }


def _get_permission_description(permission: Permission) -> str:
    """Get human-readable description for a permission."""
    descriptions = {
        Permission.READ_AAS: "Read Asset Administration Shells",
        Permission.CREATE_AAS: "Create Asset Administration Shells",
        Permission.UPDATE_AAS: "Update Asset Administration Shells",
        Permission.DELETE_AAS: "Delete Asset Administration Shells",
        Permission.READ_SUBMODEL: "Read Submodels",
        Permission.CREATE_SUBMODEL: "Create Submodels",
        Permission.UPDATE_SUBMODEL: "Update Submodels",
        Permission.DELETE_SUBMODEL: "Delete Submodels",
        Permission.READ_CONCEPT_DESCRIPTION: "Read Concept Descriptions",
        Permission.CREATE_CONCEPT_DESCRIPTION: "Create Concept Descriptions",
        Permission.UPDATE_CONCEPT_DESCRIPTION: "Update Concept Descriptions",
        Permission.DELETE_CONCEPT_DESCRIPTION: "Delete Concept Descriptions",
    }
    return descriptions.get(permission, permission.value)
