"""Service Description endpoint per IDTA-01002 Part 2.

The /description endpoint advertises:
- Supported service profiles
- Supported serialization formats
- Server capabilities and features
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import ORJSONResponse

from titan.config import settings
from titan.security.deps import require_permission_if_public
from titan.security.rbac import Permission

router = APIRouter(
    tags=["description"],
    dependencies=[
        Depends(
            require_permission_if_public(
                Permission.READ_AAS,
                lambda: settings.public_description_endpoints,
            )
        )
    ],
)


# IDTA-01002 Service Specification Profiles
PROFILE_IDS = {
    # AAS Repository
    "aas_repository_full": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRepositoryServiceSpecification/SSP-001",
    "aas_repository_read": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRepositoryServiceSpecification/SSP-002",
    "aas_repository_query": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRepositoryServiceSpecification/SSP-003",
    # Submodel Repository
    "submodel_repository_full": "https://admin-shell.io/aas/API/3/1/SubmodelRepositoryServiceSpecification/SSP-001",
    "submodel_repository_read": "https://admin-shell.io/aas/API/3/1/SubmodelRepositoryServiceSpecification/SSP-002",
    "submodel_repository_template": "https://admin-shell.io/aas/API/3/1/SubmodelRepositoryServiceSpecification/SSP-003",
    "submodel_repository_template_read": "https://admin-shell.io/aas/API/3/1/SubmodelRepositoryServiceSpecification/SSP-004",
    "submodel_repository_query": "https://admin-shell.io/aas/API/3/1/SubmodelRepositoryServiceSpecification/SSP-005",
    # Registry
    "aas_registry_full": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRegistryServiceSpecification/SSP-001",
    "aas_registry_read": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRegistryServiceSpecification/SSP-002",
    "aas_registry_bulk": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRegistryServiceSpecification/SSP-003",
    "aas_registry_query": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRegistryServiceSpecification/SSP-004",
    "aas_registry_min_read": "https://admin-shell.io/aas/API/3/1/AssetAdministrationShellRegistryServiceSpecification/SSP-005",
    "submodel_registry_full": "https://admin-shell.io/aas/API/3/1/SubmodelRegistryServiceSpecification/SSP-001",
    "submodel_registry_read": "https://admin-shell.io/aas/API/3/1/SubmodelRegistryServiceSpecification/SSP-002",
    "submodel_registry_bulk": "https://admin-shell.io/aas/API/3/1/SubmodelRegistryServiceSpecification/SSP-003",
    "submodel_registry_query": "https://admin-shell.io/aas/API/3/1/SubmodelRegistryServiceSpecification/SSP-004",
    # Discovery
    "discovery_full": "https://admin-shell.io/aas/API/3/1/DiscoveryServiceSpecification/SSP-001",
    "discovery_read": "https://admin-shell.io/aas/API/3/1/DiscoveryServiceSpecification/SSP-002",
    # Concept Description Repository
    "concept_description_full": "https://admin-shell.io/aas/API/3/1/ConceptDescriptionRepositoryServiceSpecification/SSP-001",
    "concept_description_query": "https://admin-shell.io/aas/API/3/1/ConceptDescriptionRepositoryServiceSpecification/SSP-002",
    # AASX File Server
    "aasx_file_server": "https://admin-shell.io/aas/API/3/1/AasxFileServerServiceSpecification/SSP-001",
}

SUPPORTED_PROFILE_KEYS = [
    "aas_repository_full",
    "submodel_repository_full",
    "aas_registry_full",
    "submodel_registry_full",
    "discovery_read",
    "concept_description_full",
]


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
            # AAS Repository (full profile)
            PROFILE_IDS["aas_repository_full"],
            # Submodel Repository (full profile)
            PROFILE_IDS["submodel_repository_full"],
            # Registry (full profiles)
            PROFILE_IDS["aas_registry_full"],
            PROFILE_IDS["submodel_registry_full"],
            # Discovery (read profile)
            PROFILE_IDS["discovery_read"],
            # Concept Description Repository (full profile)
            PROFILE_IDS["concept_description_full"],
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
                "oidc": settings.oidc_issuer is not None,
                "anonymous": settings.allow_anonymous_admin,
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
    return [PROFILE_IDS[key] for key in SUPPORTED_PROFILE_KEYS]
