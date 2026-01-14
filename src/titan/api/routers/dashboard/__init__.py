"""Dashboard API routers for Titan-AAS Control Center.

Provides comprehensive observability and control endpoints for all
architectural layers:
- Database (PostgreSQL) - Connection pool, query stats, slow queries
- Cache (Redis) - Memory stats, hit ratio, key management, invalidation
- Events - Stream stats, live feed (SSE), event replay
- Connectors - OPC-UA/Modbus/MQTT status and control
- Security - Audit logs, active sessions
- Observability - Log levels, traces

All endpoints require ADMIN role for access.
"""

from __future__ import annotations

from fastapi import APIRouter

from titan.api.routers.dashboard.cache import router as cache_router
from titan.api.routers.dashboard.connectors import router as connectors_router
from titan.api.routers.dashboard.database import router as database_router
from titan.api.routers.dashboard.events import router as events_router
from titan.api.routers.dashboard.observability import router as observability_router
from titan.api.routers.dashboard.overview import router as overview_router
from titan.api.routers.dashboard.security import router as security_router

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Mount all sub-routers
router.include_router(overview_router)
router.include_router(database_router)
router.include_router(cache_router)
router.include_router(events_router)
router.include_router(connectors_router)
router.include_router(security_router)
router.include_router(observability_router)

__all__ = ["router"]
