"""Health check endpoints for Titan-AAS.

Provides Kubernetes-compatible liveness and readiness probes:
- /health/live  - Liveness probe (always returns OK if process is running)
- /health/ready - Readiness probe (checks database and cache connectivity)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from titan.cache.redis import RedisCache, get_redis
from titan.persistence.db import health_check as db_health_check

router = APIRouter(tags=["health"])


class HealthStatus(str, Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    status: HealthStatus
    latency_ms: float
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result: dict[str, Any] = {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
        }
        if self.message:
            result["message"] = self.message
        return result


# Cache health results briefly to prevent health check storms
_health_cache: tuple[float, dict[str, Any]] | None = None
HEALTH_CACHE_TTL = 5  # seconds


async def check_database() -> ComponentHealth:
    """Check database connectivity."""
    start = time.monotonic()
    try:
        healthy = await asyncio.wait_for(db_health_check(), timeout=5.0)
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message=None if healthy else "Database check failed",
        )
    except asyncio.TimeoutError:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message="Database check timed out",
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message=str(e),
        )


async def check_redis() -> ComponentHealth:
    """Check Redis connectivity."""
    start = time.monotonic()
    try:
        redis_client = await get_redis()
        cache = RedisCache(redis_client)
        healthy = await asyncio.wait_for(cache.health_check(), timeout=5.0)
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message=None if healthy else "Redis check failed",
        )
    except asyncio.TimeoutError:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message="Redis check timed out",
        )
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            latency_ms=latency,
            message=str(e),
        )


@router.get("/health")
async def full_health() -> JSONResponse:
    """Full health report for external checks.

    Returns 200 when all dependencies are healthy, 503 otherwise.
    """
    db_result, redis_result = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=False,
    )

    checks: dict[str, dict[str, Any]] = {}
    overall_status = HealthStatus.HEALTHY

    for component in (db_result, redis_result):
        is_healthy = component.status == HealthStatus.HEALTHY
        if not is_healthy:
            overall_status = HealthStatus.UNHEALTHY
        checks[component.name] = {
            "status": "up" if is_healthy else "down",
            "latency_ms": round(component.latency_ms, 2),
        }
        if component.message:
            checks[component.name]["message"] = component.message

    status_code = 200 if overall_status == HealthStatus.HEALTHY else 503
    return JSONResponse(
        content={"status": overall_status.value, "checks": checks},
        status_code=status_code,
    )


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Liveness probe.

    Returns OK if the process is running. Used by Kubernetes
    to determine if the container should be restarted.
    """
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> JSONResponse:
    """Readiness probe.

    Checks database and Redis connectivity. Returns 200 if all
    dependencies are healthy, 503 if any are unhealthy.

    Used by Kubernetes to determine if the pod should receive traffic.
    """
    global _health_cache

    # Check cache
    now = time.monotonic()
    if _health_cache is not None:
        cached_time, cached_result = _health_cache
        if now - cached_time < HEALTH_CACHE_TTL:
            return JSONResponse(
                content=cached_result,
                status_code=200 if cached_result["status"] == "healthy" else 503,
            )

    # Run health checks in parallel
    db_result, redis_result = await asyncio.gather(
        check_database(),
        check_redis(),
        return_exceptions=False,
    )

    components = [db_result, redis_result]

    # Determine overall status
    all_healthy = all(c.status == HealthStatus.HEALTHY for c in components)
    any_unhealthy = any(c.status == HealthStatus.UNHEALTHY for c in components)

    if all_healthy:
        overall_status = HealthStatus.HEALTHY
    elif any_unhealthy:
        overall_status = HealthStatus.UNHEALTHY
    else:
        overall_status = HealthStatus.DEGRADED

    result = {
        "status": overall_status.value,
        "components": [c.to_dict() for c in components],
    }

    # Cache the result
    _health_cache = (now, result)

    status_code = 200 if overall_status == HealthStatus.HEALTHY else 503
    return JSONResponse(content=result, status_code=status_code)
