"""FastAPI application factory for Titan-AAS.

Creates the application with:
- IDTA-compliant API routers (/shells, /submodels, /concept-descriptions)
- Registry endpoints (/shell-descriptors, /submodel-descriptors)
- Discovery endpoints
- WebSocket for real-time events
- Lifecycle management for database, cache, MQTT, and OPC-UA connections
- OIDC authentication and RBAC authorization
- OpenTelemetry tracing and Prometheus metrics
- IDTA-compliant error handling
- ORJSON for fast JSON serialization
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from starlette.types import ExceptionHandler

from titan.api.errors import AasApiError, aas_api_exception_handler, generic_exception_handler
from titan.api.middleware import (
    CachingMiddleware,
    CompressionMiddleware,
    CorrelationMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from titan.api.middleware.rate_limit import RateLimitConfig
from titan.api.routers import (
    aas_repository,
    aasx,
    admin,
    blobs,
    concept_description_repository,
    description,
    discovery,
    federation,
    health,
    registry,
    serialization,
    submodel_repository,
    system,
)
from titan.api.routers import metrics as metrics_router
from titan.api.routers import websocket as ws_router
from titan.api.routers.dashboard import router as dashboard_router
from titan.api.routers.websocket import WebSocketEventHandler, get_ws_manager
from titan.api.v1 import create_v1_app
from titan.api.versioning import ApiVersion
from titan.cache import close_redis, get_redis
from titan.config import settings
from titan.connectors.modbus.connection import close_modbus, get_modbus_connection_manager
from titan.connectors.modbus.handler import ModbusEventHandler
from titan.connectors.mqtt import MqttEventHandler, close_mqtt, get_mqtt_publisher
from titan.connectors.mqtt_subscriber import close_mqtt_subscriber, get_mqtt_subscriber
from titan.connectors.opcua.connection import close_opcua, get_opcua_connection_manager
from titan.connectors.opcua.handler import OpcUaEventHandler
from titan.events import AasEvent, AnyEvent, SubmodelElementEvent, SubmodelEvent
from titan.events.runtime import get_event_bus, start_event_bus, stop_event_bus
from titan.observability import configure_logging
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
    - Configure structured logging
    - Initialize OpenTelemetry tracing
    - Initialize Prometheus metrics
    - Initialize database connection pool
    - Initialize Redis connection
    - Initialize MQTT connection (if configured)
    - Initialize OPC-UA connection (if configured)
    - Wire WebSocket event handler to event bus

    On shutdown:
    - Close OPC-UA connection
    - Close MQTT connection
    - Close Redis connection
    - Close database connections
    - Shutdown tracing
    """
    # Configure structured logging (JSON in production, console in dev)
    configure_logging(
        json_format=settings.env != "dev",
        level=settings.log_level,
    )

    # Initialize observability
    setup_tracing()
    get_metrics()  # Initialize metrics registry

    # Startup
    logger.info(f"Starting Titan-AAS ({settings.env})")
    await init_db()
    await get_redis()  # Initialize Redis connection
    await start_event_bus()
    await get_mqtt_publisher()  # Initialize MQTT connection (optional)

    # Wire WebSocket event handler to event bus for real-time broadcasts
    ws_handler = WebSocketEventHandler(get_ws_manager())

    async def broadcast_handler(event: AnyEvent) -> None:
        """Route events to appropriate WebSocket handlers."""
        if isinstance(event, AasEvent):
            await ws_handler.handle_aas_event(event)
        elif isinstance(event, SubmodelEvent):
            await ws_handler.handle_submodel_event(event)

    await get_event_bus().subscribe(broadcast_handler)
    logger.info("WebSocket event broadcast handler subscribed")

    # Wire MQTT event handler to event bus (optional, requires MQTT_BROKER config)
    mqtt_publisher = await get_mqtt_publisher()
    if mqtt_publisher is not None:
        mqtt_handler = MqttEventHandler(mqtt_publisher)

        async def mqtt_broadcast_handler(event: AnyEvent) -> None:
            """Route events to MQTT publisher."""
            if isinstance(event, AasEvent):
                await mqtt_handler.handle_aas_event(event)
            elif isinstance(event, SubmodelEvent):
                await mqtt_handler.handle_submodel_event(event)

        await get_event_bus().subscribe(mqtt_broadcast_handler)
        logger.info("MQTT event handler subscribed")

    # Wire MQTT subscriber (optional, bidirectional communication)
    if settings.mqtt_broker is not None and settings.mqtt_subscribe_enabled:
        mqtt_subscriber = await get_mqtt_subscriber()
        if mqtt_subscriber is not None:
            # Parse topics from settings (comma-separated)
            topics = [t.strip() for t in settings.mqtt_subscribe_topics.split(",") if t.strip()]
            await mqtt_subscriber.start(topics)
            logger.info(f"MQTT subscriber started on {len(topics)} topics")

    # Wire OPC-UA event handler to event bus (optional, industrial IoT integration)
    opcua_manager = await get_opcua_connection_manager()
    if opcua_manager is not None:
        opcua_handler = OpcUaEventHandler(opcua_manager)

        async def opcua_event_handler(event: AnyEvent) -> None:
            """Route events to OPC-UA handler."""
            if isinstance(event, AasEvent):
                await opcua_handler.handle_aas_event(event)
            elif isinstance(event, SubmodelEvent):
                await opcua_handler.handle_submodel_event(event)
            elif isinstance(event, SubmodelElementEvent):
                await opcua_handler.handle_element_event(event)

        await get_event_bus().subscribe(opcua_event_handler)
        logger.info("OPC-UA event handler subscribed")

    # Wire Modbus event handler to event bus (optional, industrial IoT integration)
    modbus_manager = await get_modbus_connection_manager()
    if modbus_manager is not None:
        modbus_client = await modbus_manager.ensure_connected()
        modbus_handler = ModbusEventHandler(modbus_client)

        async def modbus_event_handler(event: AnyEvent) -> None:
            """Route events to Modbus handler."""
            if isinstance(event, SubmodelElementEvent):
                await modbus_handler.handle_element_event(event)

        await get_event_bus().subscribe(modbus_event_handler)
        logger.info("Modbus event handler subscribed")

    # Security warning for development-only settings
    if settings.allow_anonymous_admin:
        logger.warning(
            "⚠️  SECURITY WARNING: ALLOW_ANONYMOUS_ADMIN=true - "
            "ALL REQUESTS GET ADMIN ACCESS. This is intended for local development only. "
            "NEVER enable this in production!"
        )

    logger.info("Titan-AAS startup complete")

    yield

    # Shutdown
    logger.info("Shutting down Titan-AAS")
    await close_modbus()
    await close_opcua()
    await close_mqtt_subscriber()
    await close_mqtt()
    await stop_event_bus()
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
    # Order matters: TracingMiddleware wraps MetricsMiddleware wraps CorrelationMiddleware
    # CorrelationMiddleware is innermost to set context for all other middleware
    app.add_middleware(CorrelationMiddleware)
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

    # Security headers middleware (outermost for response headers)
    if settings.enable_security_headers:
        app.add_middleware(
            SecurityHeadersMiddleware,
            enable_hsts=settings.enable_hsts,
            hsts_max_age=settings.hsts_max_age,
            hsts_include_subdomains=settings.hsts_include_subdomains,
            hsts_preload=settings.hsts_preload,
            csp_policy=settings.csp_policy,
            permissions_policy=settings.permissions_policy,
        )

    # Register exception handlers
    app.add_exception_handler(AasApiError, cast(ExceptionHandler, aas_api_exception_handler))
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
    app.include_router(concept_description_repository.router)

    # IDTA-01002 Part 2 Registry and Discovery API routers
    app.include_router(registry.router)
    app.include_router(discovery.router)

    # IDTA-01002 Part 2 Description and Serialization
    app.include_router(description.router)
    app.include_router(serialization.router)

    # AASX File Server (SSP-001)
    app.include_router(aasx.router)

    # Admin Dashboard API
    app.include_router(admin.router)

    # Control Center Dashboard API
    app.include_router(dashboard_router)

    # Federation API
    app.include_router(federation.router)

    # Real-time events
    app.include_router(ws_router.router)

    # Mount versioned APIs
    # The v1 API is available at /api/v1/* with version headers
    v1_app = create_v1_app()
    app.mount(ApiVersion.V1.prefix, v1_app)

    logger.info(f"Mounted API versions: {ApiVersion.V1.value}")

    return app


app = create_app()
