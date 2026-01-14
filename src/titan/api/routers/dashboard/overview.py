"""Dashboard overview endpoint - system health at a glance.

Provides a unified view of all system components and their health status.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from titan.cache import get_redis
from titan.config import settings
from titan.persistence.db import get_session
from titan.persistence.tables import AasTable, ConceptDescriptionTable, SubmodelTable
from titan.security.deps import require_permission
from titan.security.rbac import Permission

if TYPE_CHECKING:
    from redis.asyncio import Redis

router = APIRouter(tags=["Dashboard - Overview"])


class HealthStatus(str, Enum):
    """Health status indicators."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health status of a single component."""

    name: str
    status: HealthStatus
    message: str | None = None
    details: dict[str, Any] | None = None


class EntityCounts(BaseModel):
    """Count of AAS entities in the system."""

    aas: int
    submodels: int
    concept_descriptions: int


class SystemOverview(BaseModel):
    """Complete system health overview."""

    status: HealthStatus
    timestamp: datetime
    uptime_seconds: float
    version: str
    environment: str
    entity_counts: EntityCounts
    components: list[ComponentHealth]


# Track startup time for uptime calculation
_startup_time: datetime | None = None


def _get_startup_time() -> datetime:
    """Get or initialize startup time."""
    global _startup_time
    if _startup_time is None:
        _startup_time = datetime.utcnow()
    return _startup_time


@router.get(
    "/overview",
    response_model=SystemOverview,
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_system_overview(
    session: AsyncSession = Depends(get_session),
) -> SystemOverview:
    """Get comprehensive system health overview.

    Returns health status of all components:
    - Database connectivity and pool status
    - Redis cache connectivity
    - Entity counts
    - Connector states (if enabled)
    """
    startup = _get_startup_time()
    now = datetime.utcnow()
    uptime = (now - startup).total_seconds()

    components: list[ComponentHealth] = []
    overall_status = HealthStatus.HEALTHY

    # Check database
    try:
        # Get entity counts
        aas_stmt = select(func.count()).select_from(AasTable)
        aas_count = (await session.execute(aas_stmt)).scalar() or 0
        sm_stmt = select(func.count()).select_from(SubmodelTable)
        sm_count = (await session.execute(sm_stmt)).scalar() or 0
        cd_stmt = select(func.count()).select_from(ConceptDescriptionTable)
        cd_count = (await session.execute(cd_stmt)).scalar() or 0

        # Get pool stats via raw SQL
        pool_info = await session.execute(text("SELECT 1"))  # Simple connectivity check
        pool_info.close()

        components.append(
            ComponentHealth(
                name="PostgreSQL",
                status=HealthStatus.HEALTHY,
                message="Connected",
                details={
                    "aas_count": aas_count,
                    "submodel_count": sm_count,
                    "concept_description_count": cd_count,
                },
            )
        )
        entity_counts = EntityCounts(
            aas=aas_count, submodels=sm_count, concept_descriptions=cd_count
        )
    except Exception as e:
        components.append(
            ComponentHealth(
                name="PostgreSQL",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
        )
        overall_status = HealthStatus.UNHEALTHY
        entity_counts = EntityCounts(aas=0, submodels=0, concept_descriptions=0)

    # Check Redis
    try:
        redis: Redis = await get_redis()
        info = await redis.info("memory")
        used_memory = info.get("used_memory_human", "unknown")
        components.append(
            ComponentHealth(
                name="Redis",
                status=HealthStatus.HEALTHY,
                message="Connected",
                details={"used_memory": used_memory},
            )
        )
    except Exception as e:
        components.append(
            ComponentHealth(
                name="Redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
        )
        if overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

    # Check OPC-UA (if enabled)
    if settings.opcua_enabled:
        try:
            from titan.connectors.opcua.connection import get_opcua_connection_manager

            manager = await get_opcua_connection_manager()
            if manager and manager.is_connected:
                components.append(
                    ComponentHealth(
                        name="OPC-UA",
                        status=HealthStatus.HEALTHY,
                        message="Connected",
                        details={"endpoint": settings.opcua_endpoint},
                    )
                )
            else:
                components.append(
                    ComponentHealth(
                        name="OPC-UA",
                        status=HealthStatus.DEGRADED,
                        message="Disconnected",
                    )
                )
        except Exception as e:
            components.append(
                ComponentHealth(
                    name="OPC-UA",
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                )
            )

    # Check Modbus (if enabled)
    if settings.modbus_enabled:
        try:
            from titan.connectors.modbus.connection import get_modbus_connection_manager

            modbus_manager = await get_modbus_connection_manager()
            if modbus_manager and modbus_manager.is_connected:
                components.append(
                    ComponentHealth(
                        name="Modbus",
                        status=HealthStatus.HEALTHY,
                        message="Connected",
                        details={"host": settings.modbus_host, "port": settings.modbus_port},
                    )
                )
            else:
                components.append(
                    ComponentHealth(
                        name="Modbus",
                        status=HealthStatus.DEGRADED,
                        message="Disconnected",
                    )
                )
        except Exception as e:
            components.append(
                ComponentHealth(
                    name="Modbus",
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                )
            )

    # Check MQTT (if enabled)
    if settings.mqtt_broker:
        try:
            from titan.connectors.mqtt import get_mqtt_publisher

            publisher = await get_mqtt_publisher()
            if publisher and getattr(publisher, "is_connected", False):
                components.append(
                    ComponentHealth(
                        name="MQTT",
                        status=HealthStatus.HEALTHY,
                        message="Connected",
                        details={"broker": settings.mqtt_broker},
                    )
                )
            else:
                components.append(
                    ComponentHealth(
                        name="MQTT",
                        status=HealthStatus.DEGRADED,
                        message="Disconnected",
                    )
                )
        except Exception as e:
            components.append(
                ComponentHealth(
                    name="MQTT",
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                )
            )

    return SystemOverview(
        status=overall_status,
        timestamp=now,
        uptime_seconds=uptime,
        version="0.1.0",
        environment=settings.env,
        entity_counts=entity_counts,
        components=components,
    )
