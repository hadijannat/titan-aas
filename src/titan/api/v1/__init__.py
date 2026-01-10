"""Titan-AAS API v1.

This module provides the v1 API endpoints for the Asset Administration Shell.
All routers are re-exported here for versioned mounting.

The v1 API is the current stable version and follows IDTA-01002 Part 2.

Example:
    from titan.api.v1 import create_v1_app

    v1_app = create_v1_app()
    main_app.mount("/api/v1", v1_app)
"""

from __future__ import annotations

from fastapi import FastAPI

from titan.api.routers import (
    aas_repository,
    blobs,
    description,
    discovery,
    registry,
    serialization,
    submodel_repository,
)
from titan.api.versioning import ApiVersion, create_versioned_app


def create_v1_app() -> FastAPI:
    """Create the v1 API application.

    Returns a FastAPI application with all v1 routers mounted.
    This should be mounted at /api/v1 on the main application.

    Returns:
        FastAPI application for v1 API
    """
    app = create_versioned_app(
        version=ApiVersion.V1,
        title="Titan-AAS",
        description="Asset Administration Shell Repository API v1 (IDTA-01002 Part 2)",
    )

    # IDTA-01002 Part 2 Repository API routers
    app.include_router(
        aas_repository.router,
        tags=["Asset Administration Shell Repository API"],
    )
    app.include_router(
        submodel_repository.router,
        tags=["Submodel Repository API"],
    )
    app.include_router(
        blobs.router,
        tags=["Submodel Repository API"],
    )

    # IDTA-01002 Part 2 Registry and Discovery API routers
    app.include_router(
        registry.router,
        tags=["Asset Administration Shell Registry API"],
    )
    app.include_router(
        discovery.router,
        tags=["Discovery API"],
    )

    # IDTA-01002 Part 2 Description and Serialization
    app.include_router(
        description.router,
        tags=["Description API"],
    )
    app.include_router(
        serialization.router,
        tags=["Serialization API"],
    )

    return app


# Export router references for direct access if needed
__all__ = [
    "create_v1_app",
    "aas_repository",
    "submodel_repository",
    "blobs",
    "registry",
    "discovery",
    "description",
    "serialization",
]
