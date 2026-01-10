"""Admin API router.

Provides administrative endpoints for dashboard and management:
- GET  /admin/stats          - Dashboard statistics
- GET  /admin/activity       - Recent activity log
- GET  /admin/health         - System health status
- POST /admin/import-preview - Preview before import
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.persistence.db import get_session
from titan.persistence.tables import (
    AasDescriptorTable,
    AasTable,
    AasxPackageTable,
    BlobAssetTable,
    ConceptDescriptionTable,
    SubmodelDescriptorTable,
    SubmodelTable,
)
from titan.security.deps import require_permission
from titan.security.rbac import Permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/stats",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get dashboard statistics.

    Returns counts of all entity types and storage metrics.
    """
    # Count entities
    aas_count = await session.scalar(select(func.count()).select_from(AasTable))
    submodel_count = await session.scalar(select(func.count()).select_from(SubmodelTable))
    cd_count = await session.scalar(select(func.count()).select_from(ConceptDescriptionTable))
    package_count = await session.scalar(select(func.count()).select_from(AasxPackageTable))

    # Registry counts
    aas_descriptor_count = await session.scalar(
        select(func.count()).select_from(AasDescriptorTable)
    )
    submodel_descriptor_count = await session.scalar(
        select(func.count()).select_from(SubmodelDescriptorTable)
    )

    # Blob storage stats
    blob_count = await session.scalar(select(func.count()).select_from(BlobAssetTable))
    blob_size = await session.scalar(select(func.sum(BlobAssetTable.size_bytes))) or 0

    # Recent activity (last 24h creates)
    cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    recent_aas = await session.scalar(
        select(func.count())
        .select_from(AasTable)
        .where(AasTable.created_at >= cutoff)
    )
    recent_submodels = await session.scalar(
        select(func.count())
        .select_from(SubmodelTable)
        .where(SubmodelTable.created_at >= cutoff)
    )

    return {
        "repository": {
            "shells": aas_count or 0,
            "submodels": submodel_count or 0,
            "conceptDescriptions": cd_count or 0,
        },
        "registry": {
            "shellDescriptors": aas_descriptor_count or 0,
            "submodelDescriptors": submodel_descriptor_count or 0,
        },
        "packages": {
            "count": package_count or 0,
        },
        "storage": {
            "blobCount": blob_count or 0,
            "blobSizeBytes": blob_size,
        },
        "recentActivity": {
            "shellsToday": recent_aas or 0,
            "submodelsToday": recent_submodels or 0,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/activity",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_recent_activity(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get recent activity log.

    Returns recent creates/updates across all entity types.
    """
    activities = []

    # Recent shells
    stmt = (
        select(AasTable.identifier, AasTable.created_at, AasTable.updated_at)
        .order_by(AasTable.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    for row in result.all():
        activities.append({
            "type": "shell",
            "action": "updated" if row.updated_at != row.created_at else "created",
            "identifier": row.identifier,
            "timestamp": row.updated_at.isoformat(),
        })

    # Recent submodels
    stmt = (
        select(SubmodelTable.identifier, SubmodelTable.created_at, SubmodelTable.updated_at)
        .order_by(SubmodelTable.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    for row in result.all():
        activities.append({
            "type": "submodel",
            "action": "updated" if row.updated_at != row.created_at else "created",
            "identifier": row.identifier,
            "timestamp": row.updated_at.isoformat(),
        })

    # Recent packages
    stmt = (
        select(AasxPackageTable.id, AasxPackageTable.filename, AasxPackageTable.created_at)
        .order_by(AasxPackageTable.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    for row in result.all():
        activities.append({
            "type": "package",
            "action": "uploaded",
            "identifier": row.id,
            "filename": row.filename,
            "timestamp": row.created_at.isoformat(),
        })

    # Sort by timestamp and limit
    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    activities = activities[:limit]

    return {
        "activities": activities,
        "count": len(activities),
    }


@router.get("/health")
async def get_admin_health(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get system health status.

    Returns health of database, cache, and storage.
    """
    health = {
        "status": "healthy",
        "components": {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Database health
    try:
        await session.execute(select(1))
        health["components"]["database"] = {"status": "healthy"}
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["database"] = {"status": "unhealthy", "error": str(e)}

    # Redis health
    try:
        from titan.cache import get_redis

        redis = await get_redis()
        await redis.ping()
        health["components"]["cache"] = {"status": "healthy"}
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["cache"] = {"status": "unhealthy", "error": str(e)}

    # Blob storage health
    try:
        from titan.storage.factory import get_blob_storage

        storage = get_blob_storage()
        health["components"]["storage"] = {
            "status": "healthy",
            "type": type(storage).__name__,
        }
    except Exception as e:
        health["status"] = "degraded"
        health["components"]["storage"] = {"status": "unhealthy", "error": str(e)}

    return health


@router.get(
    "/semantic-ids",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
async def get_semantic_ids(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get unique semantic IDs in use.

    Useful for filtering and discovery.
    """
    stmt = (
        select(SubmodelTable.semantic_id, func.count().label("count"))
        .where(SubmodelTable.semantic_id.isnot(None))
        .group_by(SubmodelTable.semantic_id)
        .order_by(func.count().desc())
        .limit(100)
    )
    result = await session.execute(stmt)

    semantic_ids = [
        {"semanticId": row.semantic_id, "count": row.count}
        for row in result.all()
    ]

    return {
        "semanticIds": semantic_ids,
        "count": len(semantic_ids),
    }


@router.get(
    "/asset-ids",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_global_asset_ids(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get unique global asset IDs in use.

    Useful for discovery and validation.
    """
    # Query the JSONB doc for globalAssetId
    stmt = (
        select(
            AasTable.doc["assetInformation"]["globalAssetId"].astext.label("global_asset_id"),
            func.count().label("count"),
        )
        .where(AasTable.doc["assetInformation"]["globalAssetId"].isnot(None))
        .group_by(AasTable.doc["assetInformation"]["globalAssetId"].astext)
        .order_by(func.count().desc())
        .limit(100)
    )
    result = await session.execute(stmt)

    asset_ids = [
        {"globalAssetId": row.global_asset_id, "count": row.count}
        for row in result.all()
    ]

    return {
        "globalAssetIds": asset_ids,
        "count": len(asset_ids),
    }
