"""Service Description endpoint per IDTA-01002 Part 2.

The /description endpoint advertises:
- Supported service profiles
- Supported serialization formats
- Server capabilities and features
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

router = APIRouter(tags=["description"])


# IDTA-01002 Service Specification Profiles
SERVICE_PROFILES = {
    # AAS Repository
    "aas_repository_read": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRepositoryServiceSpecification/SSP-001",
    "aas_repository_crud": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRepositoryServiceSpecification/SSP-002",
    # Submodel Repository
    "submodel_repository_read": "https://admin-shell.io/aas/API/3/1/SubmodelRepositoryServiceSpecification/SSP-001",
    "submodel_repository_crud": "https://admin-shell.io/aas/API/3/1/SubmodelRepositoryServiceSpecification/SSP-002",
    # Registry
    "aas_registry_read": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRegistryServiceSpecification/SSP-001",
    "aas_registry_crud": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRegistryServiceSpecification/SSP-002",
    "submodel_registry_read": "https://admin-shell.io/aas/API/3/1/SubmodelRegistryServiceSpecification/SSP-001",
    "submodel_registry_crud": "https://admin-shell.io/aas/API/3/1/SubmodelRegistryServiceSpecification/SSP-002",
    # Discovery
    "discovery": "https://admin-shell.io/aas/API/3/1/DiscoveryServiceSpecification/SSP-001",
}


@router.get(
    "/description",
    response_class=ORJSONResponse,
    summary="Get server description",
    description="Returns information about supported profiles and features",
    responses={
        200: {
            "description": "Server description",
            "content": {
                "application/json": {
                    "example": {
                        "profiles": [
                            "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRepositoryServiceSpecification/SSP-002"
                        ],
                        "features": {
                            "serialization": ["json"],
                            "modifiers": ["$value", "$metadata", "$reference", "$path"],
                        },
                    }
                }
            },
        }
    },
)
async def get_description() -> dict[str, Any]:
    """Return server description with supported profiles and features.

    Per IDTA-01002 Part 2, this endpoint advertises:
    - Supported service specification profiles
    - Supported serialization formats
    - Available modifiers and query parameters
    """
    return {
        "profiles": [
            # AAS Repository (full CRUD)
            SERVICE_PROFILES["aas_repository_crud"],
            # Submodel Repository (full CRUD)
            SERVICE_PROFILES["submodel_repository_crud"],
            # Registry (full CRUD)
            SERVICE_PROFILES["aas_registry_crud"],
            SERVICE_PROFILES["submodel_registry_crud"],
            # Discovery
            SERVICE_PROFILES["discovery"],
        ],
        "features": {
            # Serialization formats
            "serialization": ["json"],
            # Supported modifiers
            "modifiers": [
                "$value",
                "$metadata",
                "$reference",
                "$path",
            ],
            # Query parameters
            "queryParameters": {
                "level": ["deep", "core"],
                "content": ["normal", "metadata", "value", "reference", "path"],
                "extent": ["withBlobValue", "withoutBlobValue"],
            },
            # Pagination
            "pagination": {
                "type": "cursor",
                "defaultLimit": 100,
                "maxLimit": 1000,
            },
            # Real-time events
            "events": {
                "websocket": True,
                "mqtt": True,
            },
            # Authentication
            "authentication": {
                "oidc": True,
                "anonymous": True,  # When OIDC not configured
            },
        },
        "version": {
            "specificationVersion": "3.1.1",
            "serverVersion": "0.1.0",
            "serverName": "Titan-AAS",
        },
    }


@router.get(
    "/description/profiles",
    response_class=ORJSONResponse,
    summary="List supported profiles",
    description="Returns list of supported service specification profiles",
)
async def list_profiles() -> list[str]:
    """Return list of all supported service specification profiles."""
    return list(SERVICE_PROFILES.values())
