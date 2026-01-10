"""FastAPI application factory for Titan-AAS.

Creates the application with:
- IDTA-compliant API routers (/shells, /submodels, /shell-descriptors, /submodel-descriptors)
- Registry and Discovery endpoints
- WebSocket for real-time events
- Lifecycle management for database, cache, and MQTT connections
- OIDC authentication and RBAC authorization
- OpenTelemetry tracing and Prometheus metrics
- IDTA-compliant error handling
- ORJSON for fast JSON serialization
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from starlette.types import ExceptionHandler

from titan.api.errors import AasApiError, aas_api_exception_handler, generic_exception_handler
from titan.api.middleware import CachingMiddleware, CompressionMiddleware, RateLimitMiddleware
from titan.api.middleware.rate_limit import RateLimitConfig
from titan.api.routers import (
    aas_repository,
    blobs,
    description,
    discovery,
    health,
    registry,
    serialization,
    submodel_repository,
    system,
)
from titan.api.routers import metrics as metrics_router
from titan.api.routers import websocket as ws_router
from titan.cache import close_redis, get_redis
from titan.config import settings
from titan.connectors.mqtt import close_mqtt, get_mqtt_publisher
from titan.observability.metrics import MetricsMiddleware, get_metrics
from titan.observability.tracing import (
    TracingMiddleware,
    setup_tracing,
    shutdown_tracing,
)
from titan.persistence.db import close_db, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle.

    On startup:
    - Initialize OpenTelemetry tracing
    - Initialize Prometheus metrics
    - Initialize database connection pool
    - Initialize Redis connection
    - Initialize MQTT connection (if configured)

    On shutdown:
    - Close MQTT connection
    - Close Redis connection
    - Close database connections
    - Shutdown tracing
    """
    # Initialize observability
    setup_tracing()
    get_metrics()  # Initialize metrics registry

    # Startup
    logger.info(f"Starting Titan-AAS ({settings.env})")
    await init_db()
    await get_redis()  # Initialize Redis connection
    await get_mqtt_publisher()  # Initialize MQTT connection (optional)
    logger.info("Titan-AAS startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Titan-AAS")
    await close_mqtt()
    await close_redis()
    await close_db()
    shutdown_tracing()
    logger.info("Titan-AAS shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns a fully configured application with:
    - All IDTA-compliant API routers
    - Registry and Discovery endpoints
    - WebSocket for real-time events
    - OIDC authentication (optional, via security dependencies)
    - OpenTelemetry tracing and Prometheus metrics
    - Exception handlers for consistent error responses
    - Lifecycle hooks for connection management
    """
    app = FastAPI(
        title="Titan-AAS",
        description="Industrial-grade Asset Administration Shell runtime",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add observability middleware
    # Order matters: TracingMiddleware wraps MetricsMiddleware
    if settings.enable_metrics:
        app.add_middleware(MetricsMiddleware)
    if settings.enable_tracing:
        app.add_middleware(TracingMiddleware)

    # Add production middleware
    # Order: Compression (outer) -> Rate Limiting -> Caching (inner)
    # This means responses flow: Caching adds headers -> Rate limit adds headers -> Compression
    if settings.enable_http_caching:
        app.add_middleware(
            CachingMiddleware,
            default_max_age=settings.cache_max_age,
            stale_while_revalidate=settings.cache_stale_while_revalidate,
        )

    if settings.enable_rate_limiting:
        app.add_middleware(
            RateLimitMiddleware,
            config=RateLimitConfig(
                requests_per_window=settings.rate_limit_requests,
                window_seconds=settings.rate_limit_window,
            ),
        )

    if settings.enable_compression:
        app.add_middleware(
            CompressionMiddleware,
            minimum_size=settings.compression_min_size,
            compression_level=settings.compression_level,
        )

    # Register exception handlers
    app.add_exception_handler(
        AasApiError, cast(ExceptionHandler, aas_api_exception_handler)
    )
    app.add_exception_handler(Exception, cast(ExceptionHandler, generic_exception_handler))

    # Include routers
    app.include_router(health.router)
    app.include_router(system.router)

    # Metrics endpoint (Prometheus)
    if settings.enable_metrics:
        app.include_router(metrics_router.router)

    # IDTA-01002 Part 2 Repository API routers
    app.include_router(aas_repository.router)
    app.include_router(submodel_repository.router)
    app.include_router(blobs.router)

    # IDTA-01002 Part 2 Registry and Discovery API routers
    app.include_router(registry.router)
    app.include_router(discovery.router)

    # IDTA-01002 Part 2 Description and Serialization
    app.include_router(description.router)
    app.include_router(serialization.router)

    # Real-time events
    app.include_router(ws_router.router)

    return app


app = create_app()
