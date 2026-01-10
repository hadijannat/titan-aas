"""Federation API router.

Provides federation management endpoints:
- GET  /federation/peers              - List registered peers
- POST /federation/peers              - Register new peer
- GET  /federation/peers/{id}         - Get peer details
- DELETE /federation/peers/{id}       - Unregister peer
- GET  /federation/sync/status        - Current sync status
- POST /federation/sync/now           - Trigger immediate sync
- GET  /federation/conflicts          - List unresolved conflicts
- POST /federation/conflicts/{id}/resolve - Resolve conflict
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.federation import (
    ConflictInfo,
    ConflictManager,
    FederationSync,
    Peer,
    PeerRegistry,
    ResolutionStrategy,
    SyncMode,
)
from titan.federation.peer import PeerCapabilities
from titan.persistence.db import get_session
from titan.persistence.tables import FederationConflictTable, FederationSyncLogTable
from titan.security.deps import require_permission
from titan.security.rbac import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/federation", tags=["Federation"])

# Module-level singletons (initialized on first use)
_peer_registry: PeerRegistry | None = None
_conflict_manager: ConflictManager | None = None
_federation_sync: FederationSync | None = None


def get_peer_registry() -> PeerRegistry:
    """Get or create peer registry singleton."""
    global _peer_registry
    if _peer_registry is None:
        _peer_registry = PeerRegistry()
    return _peer_registry


def get_conflict_manager() -> ConflictManager:
    """Get or create conflict manager singleton."""
    global _conflict_manager
    if _conflict_manager is None:
        _conflict_manager = ConflictManager()
    return _conflict_manager


def get_federation_sync() -> FederationSync:
    """Get or create federation sync singleton."""
    global _federation_sync
    if _federation_sync is None:
        _federation_sync = FederationSync(
            registry=get_peer_registry(),
            conflict_manager=get_conflict_manager(),
        )
    return _federation_sync


# --------------------------------------------------------------------------
# Request/Response Models
# --------------------------------------------------------------------------


class PeerCapabilitiesModel(BaseModel):
    """Peer capabilities model."""

    aas_repository: bool = Field(default=True, alias="aasRepository")
    submodel_repository: bool = Field(default=True, alias="submodelRepository")
    aas_registry: bool = Field(default=False, alias="aasRegistry")
    submodel_registry: bool = Field(default=False, alias="submodelRegistry")
    aasx_server: bool = Field(default=False, alias="aasxServer")
    read_only: bool = Field(default=False, alias="readOnly")

    model_config = {"populate_by_name": True}


class RegisterPeerRequest(BaseModel):
    """Request to register a new peer."""

    url: str = Field(..., description="Base URL of the peer instance")
    name: str | None = Field(None, description="Human-readable peer name")
    capabilities: PeerCapabilitiesModel | None = None


class PeerResponse(BaseModel):
    """Peer information response."""

    id: str
    url: str
    name: str | None = None
    status: str
    capabilities: PeerCapabilitiesModel | None = None
    last_seen: str | None = Field(None, alias="lastSeen")
    last_sync: str | None = Field(None, alias="lastSync")
    version: str | None = None

    model_config = {"populate_by_name": True}


class ConflictResponse(BaseModel):
    """Conflict information response."""

    id: str
    peer_id: str = Field(..., alias="peerId")
    entity_type: str = Field(..., alias="entityType")
    entity_id: str = Field(..., alias="entityId")
    local_etag: str = Field(..., alias="localEtag")
    remote_etag: str = Field(..., alias="remoteEtag")
    detected_at: str = Field(..., alias="detectedAt")
    is_resolved: bool = Field(..., alias="isResolved")
    resolution_strategy: str | None = Field(None, alias="resolutionStrategy")
    resolved_at: str | None = Field(None, alias="resolvedAt")
    resolved_by: str | None = Field(None, alias="resolvedBy")

    model_config = {"populate_by_name": True}


class ResolveConflictRequest(BaseModel):
    """Request to resolve a conflict."""

    strategy: str = Field(
        default="last_write_wins",
        description="Resolution strategy: last_write_wins, local_preferred, remote_preferred",
    )
    resolved_by: str | None = Field(None, alias="resolvedBy")

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------
# Peer Endpoints
# --------------------------------------------------------------------------


@router.get(
    "/peers",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def list_peers() -> dict[str, Any]:
    """List all registered federation peers."""
    registry = get_peer_registry()
    peers = registry.list_all()

    return {
        "peers": [_peer_to_response(p) for p in peers],
        "count": len(peers),
        "healthy": len([p for p in peers if p.is_healthy]),
    }


@router.post(
    "/peers",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def register_peer(
    request: RegisterPeerRequest,
) -> PeerResponse:
    """Register a new federation peer."""
    registry = get_peer_registry()

    # Generate peer ID
    peer_id = str(uuid.uuid4())

    # Build capabilities
    caps = PeerCapabilities()
    if request.capabilities:
        caps.aas_repository = request.capabilities.aas_repository
        caps.submodel_repository = request.capabilities.submodel_repository
        caps.aas_registry = request.capabilities.aas_registry
        caps.submodel_registry = request.capabilities.submodel_registry
        caps.aasx_server = request.capabilities.aasx_server
        caps.read_only = request.capabilities.read_only

    peer = Peer(
        id=peer_id,
        url=request.url.rstrip("/"),
        name=request.name,
        capabilities=caps,
    )

    registry.register(peer)

    # Optionally check health immediately
    await registry.check_health(peer)

    logger.info(f"Registered federation peer: {peer_id} at {request.url}")

    return _peer_to_response(peer)


@router.get(
    "/peers/{peer_id}",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def get_peer(peer_id: str) -> PeerResponse:
    """Get details of a specific peer."""
    registry = get_peer_registry()
    peer = registry.get(peer_id)

    if not peer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peer not found: {peer_id}",
        )

    return _peer_to_response(peer)


@router.delete(
    "/peers/{peer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def unregister_peer(peer_id: str) -> None:
    """Unregister a federation peer."""
    registry = get_peer_registry()

    if not registry.unregister(peer_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peer not found: {peer_id}",
        )

    logger.info(f"Unregistered federation peer: {peer_id}")


@router.post(
    "/peers/{peer_id}/health",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def check_peer_health(peer_id: str) -> dict[str, Any]:
    """Check health of a specific peer."""
    registry = get_peer_registry()
    peer = registry.get(peer_id)

    if not peer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Peer not found: {peer_id}",
        )

    status_result = await registry.check_health(peer)

    return {
        "peerId": peer_id,
        "status": status_result.value,
        "lastSeen": peer.last_seen.isoformat() if peer.last_seen else None,
    }


# --------------------------------------------------------------------------
# Sync Endpoints
# --------------------------------------------------------------------------


@router.get(
    "/sync/status",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def get_sync_status() -> dict[str, Any]:
    """Get current federation sync status."""
    sync = get_federation_sync()
    status_info = sync.get_sync_status()

    return {
        **status_info,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.post(
    "/sync/now",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def trigger_sync(
    mode: SyncMode | None = None,
) -> dict[str, Any]:
    """Trigger immediate sync with all healthy peers."""
    sync = get_federation_sync()

    # Optionally override mode
    if mode:
        sync.mode = mode

    result = await sync.sync_once()

    return {
        **result,
        "triggered_at": datetime.now(UTC).isoformat(),
    }


@router.get(
    "/sync/history",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def get_sync_history(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get recent sync history from log."""
    stmt = (
        select(FederationSyncLogTable)
        .order_by(FederationSyncLogTable.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    logs = result.scalars().all()

    history = []
    for log in logs:
        history.append(
            {
                "id": log.id,
                "peerId": log.peer_id,
                "direction": log.sync_direction,
                "entityType": log.entity_type,
                "itemsProcessed": log.items_processed,
                "itemsFailed": log.items_failed,
                "conflictsDetected": log.conflicts_detected,
                "status": log.status,
                "startedAt": log.started_at.isoformat() if log.started_at else None,
                "completedAt": log.completed_at.isoformat() if log.completed_at else None,
                "errorMessage": log.error_message,
            }
        )

    return {
        "history": history,
        "count": len(history),
    }


# --------------------------------------------------------------------------
# Conflict Endpoints
# --------------------------------------------------------------------------


@router.get(
    "/conflicts",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def list_conflicts(
    peer_id: str | None = None,
    resolved: bool = False,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List federation conflicts."""
    stmt = select(FederationConflictTable)

    if peer_id:
        stmt = stmt.where(FederationConflictTable.peer_id == peer_id)

    if not resolved:
        stmt = stmt.where(FederationConflictTable.resolved_at.is_(None))
    else:
        stmt = stmt.where(FederationConflictTable.resolved_at.isnot(None))

    stmt = stmt.order_by(FederationConflictTable.created_at.desc()).limit(limit)

    result = await session.execute(stmt)
    conflicts = result.scalars().all()

    items = []
    for conflict in conflicts:
        items.append(
            {
                "id": conflict.id,
                "peerId": conflict.peer_id,
                "entityType": conflict.entity_type,
                "entityId": conflict.entity_id,
                "localEtag": conflict.local_etag,
                "remoteEtag": conflict.remote_etag,
                "detectedAt": conflict.created_at.isoformat(),
                "isResolved": conflict.resolved_at is not None,
                "resolutionStrategy": conflict.resolution_strategy,
                "resolvedAt": conflict.resolved_at.isoformat() if conflict.resolved_at else None,
                "resolvedBy": conflict.resolved_by,
            }
        )

    return {
        "conflicts": items,
        "count": len(items),
    }


@router.get(
    "/conflicts/{conflict_id}",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def get_conflict(
    conflict_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get details of a specific conflict including document diffs."""
    stmt = select(FederationConflictTable).where(FederationConflictTable.id == conflict_id)
    result = await session.execute(stmt)
    conflict = result.scalar_one_or_none()

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict not found: {conflict_id}",
        )

    return {
        "id": conflict.id,
        "peerId": conflict.peer_id,
        "entityType": conflict.entity_type,
        "entityId": conflict.entity_id,
        "localEtag": conflict.local_etag,
        "remoteEtag": conflict.remote_etag,
        "localDoc": conflict.local_doc,
        "remoteDoc": conflict.remote_doc,
        "detectedAt": conflict.created_at.isoformat(),
        "isResolved": conflict.resolved_at is not None,
        "resolutionStrategy": conflict.resolution_strategy,
        "resolvedAt": conflict.resolved_at.isoformat() if conflict.resolved_at else None,
        "resolvedBy": conflict.resolved_by,
    }


@router.post(
    "/conflicts/{conflict_id}/resolve",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def resolve_conflict(
    conflict_id: str,
    request: ResolveConflictRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Resolve a specific conflict."""
    # Get conflict from database
    stmt = select(FederationConflictTable).where(FederationConflictTable.id == conflict_id)
    result = await session.execute(stmt)
    conflict = result.scalar_one_or_none()

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict not found: {conflict_id}",
        )

    if conflict.resolved_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conflict already resolved",
        )

    # Parse strategy
    try:
        strategy = ResolutionStrategy(request.strategy)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resolution strategy: {request.strategy}",
        )

    # Build ConflictInfo for resolver
    conflict_info = ConflictInfo(
        id=conflict.id,
        peer_id=conflict.peer_id,
        entity_type=conflict.entity_type,
        entity_id=conflict.entity_id,
        local_doc=conflict.local_doc or {},
        local_etag=conflict.local_etag,
        remote_doc=conflict.remote_doc or {},
        remote_etag=conflict.remote_etag,
        detected_at=conflict.created_at,
    )

    # Resolve using conflict manager
    manager = get_conflict_manager()
    manager.add_conflict(conflict_info)
    resolution = manager.resolve_conflict(
        conflict_id=conflict_id,
        strategy=strategy,
        resolved_by=request.resolved_by,
    )

    if resolution.success:
        # Update database record
        conflict.resolution_strategy = strategy.value
        conflict.resolved_at = datetime.now(UTC)
        conflict.resolved_by = request.resolved_by
        await session.commit()

        logger.info(f"Resolved conflict {conflict_id} using {strategy.value}")

        return {
            "success": True,
            "conflictId": conflict_id,
            "strategy": strategy.value,
            "resolvedAt": conflict.resolved_at.isoformat(),
            "resolvedBy": request.resolved_by,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=resolution.error or "Resolution failed",
        )


@router.post(
    "/conflicts/resolve-all",
    dependencies=[Depends(require_permission(Permission.ADMIN))],
)
async def resolve_all_conflicts(
    strategy: str = "last_write_wins",
    peer_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Resolve all unresolved conflicts."""
    try:
        strategy_enum = ResolutionStrategy(strategy)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resolution strategy: {strategy}",
        )

    # Get unresolved conflicts from database
    stmt = select(FederationConflictTable).where(FederationConflictTable.resolved_at.is_(None))
    if peer_id:
        stmt = stmt.where(FederationConflictTable.peer_id == peer_id)

    result = await session.execute(stmt)
    conflicts = result.scalars().all()

    resolved_count = 0
    failed_count = 0

    for conflict in conflicts:
        try:
            conflict.resolution_strategy = strategy_enum.value
            conflict.resolved_at = datetime.now(UTC)
            conflict.resolved_by = "batch_resolution"
            resolved_count += 1
        except Exception as e:
            logger.error(f"Failed to resolve conflict {conflict.id}: {e}")
            failed_count += 1

    await session.commit()

    return {
        "total": len(conflicts),
        "resolved": resolved_count,
        "failed": failed_count,
        "strategy": strategy,
    }


# --------------------------------------------------------------------------
# Helper Functions
# --------------------------------------------------------------------------


def _peer_to_response(peer: Peer) -> PeerResponse:
    """Convert Peer to response model."""
    return PeerResponse(
        id=peer.id,
        url=peer.url,
        name=peer.name,
        status=peer.status.value,
        capabilities=PeerCapabilitiesModel(
            aasRepository=peer.capabilities.aas_repository,
            submodelRepository=peer.capabilities.submodel_repository,
            aasRegistry=peer.capabilities.aas_registry,
            submodelRegistry=peer.capabilities.submodel_registry,
            aasxServer=peer.capabilities.aasx_server,
            readOnly=peer.capabilities.read_only,
        ),
        lastSeen=peer.last_seen.isoformat() if peer.last_seen else None,
        lastSync=peer.last_sync.isoformat() if peer.last_sync else None,
        version=peer.version,
    )
