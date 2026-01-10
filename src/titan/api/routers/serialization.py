"""Serialization endpoint for bulk export per IDTA-01002 Part 2.

The /serialization endpoint provides bulk export of:
- Multiple AAS
- Multiple Submodels
- Environment packages
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from titan.persistence.db import get_session
from titan.persistence.repositories import (
    AasRepository,
    ConceptDescriptionRepository,
    SubmodelRepository,
)

router = APIRouter(tags=["serialization"])


@router.get(
    "/serialization",
    summary="Export AAS environment",
    description="Export multiple AAS and Submodels as a single environment",
    responses={
        200: {
            "description": "AAS Environment JSON",
            "content": {
                "application/json": {},
                "application/asset-administration-shell-package+xml": {},
            },
        }
    },
)
async def get_serialization(
    aas_ids: Annotated[
        list[str] | None,
        Query(
            alias="aasIds",
            description="List of AAS identifiers to include",
        ),
    ] = None,
    submodel_ids: Annotated[
        list[str] | None,
        Query(
            alias="submodelIds",
            description="List of Submodel identifiers to include",
        ),
    ] = None,
    include_concept_descriptions: Annotated[
        bool,
        Query(
            alias="includeConceptDescriptions",
            description="Include referenced ConceptDescriptions",
        ),
    ] = True,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export an AAS environment with selected AAS and Submodels.

    The environment format follows IDTA-01001 Part 1:
    {
        "assetAdministrationShells": [...],
        "submodels": [...],
        "conceptDescriptions": [...]
    }

    If no IDs are specified, exports all resources.
    """
    import orjson

    aas_repo = AasRepository(session)
    submodel_repo = SubmodelRepository(session)
    cd_repo = ConceptDescriptionRepository(session)

    shells: list[dict[str, Any]] = []
    submodels: list[dict[str, Any]] = []
    concept_descriptions: list[dict[str, Any]] = []

    # Fetch AAS
    if aas_ids:
        for aas_id in aas_ids:
            aas_model = await aas_repo.get_model_by_id(aas_id)
            if aas_model:
                shells.append(aas_model.model_dump(by_alias=True, exclude_none=True))
    else:
        # Fetch all (with reasonable limit)
        results = await aas_repo.list_all(limit=1000)
        for doc_bytes, _ in results:
            shells.append(orjson.loads(doc_bytes))

    # Fetch Submodels
    if submodel_ids:
        for sm_id in submodel_ids:
            submodel_model = await submodel_repo.get_model_by_id(sm_id)
            if submodel_model:
                submodels.append(submodel_model.model_dump(by_alias=True, exclude_none=True))
    else:
        # Fetch all (with reasonable limit)
        results = await submodel_repo.list_all(limit=1000)
        for doc_bytes, _ in results:
            submodels.append(orjson.loads(doc_bytes))

    # Fetch ConceptDescriptions if requested
    if include_concept_descriptions:
        results = await cd_repo.list_all(limit=1000)
        for doc_bytes, _ in results:
            concept_descriptions.append(orjson.loads(doc_bytes))

    # Build environment
    environment = {
        "assetAdministrationShells": shells,
        "submodels": submodels,
        "conceptDescriptions": concept_descriptions,
    }

    # Serialize
    content = orjson.dumps(environment)

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="aas-environment.json"',
        },
    )


@router.post(
    "/serialization",
    summary="Import AAS environment",
    description="Import multiple AAS and Submodels from an environment",
    status_code=200,
    responses={
        200: {
            "description": "Import result",
            "content": {
                "application/json": {
                    "example": {
                        "imported": {
                            "shells": 5,
                            "submodels": 10,
                        },
                        "errors": [],
                    }
                }
            },
        }
    },
)
async def post_serialization(
    environment: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Import an AAS environment with AAS, Submodels, and ConceptDescriptions.

    Accepts an environment in IDTA-01001 Part 1 format and imports
    all contained AAS, Submodels, and ConceptDescriptions.
    """
    from titan.core.model import AssetAdministrationShell, ConceptDescription, Submodel

    aas_repo = AasRepository(session)
    submodel_repo = SubmodelRepository(session)
    cd_repo = ConceptDescriptionRepository(session)

    imported_shells = 0
    imported_submodels = 0
    imported_cds = 0
    errors: list[str] = []

    # Import AAS
    shells = environment.get("assetAdministrationShells", [])
    for shell_data in shells:
        try:
            shell = AssetAdministrationShell.model_validate(shell_data)
            if await aas_repo.exists(shell.id):
                errors.append(f"AAS already exists: {shell.id}")
            else:
                await aas_repo.create(shell)
                imported_shells += 1
        except Exception as e:
            errors.append(f"Failed to import AAS: {e}")

    # Import Submodels
    submodels = environment.get("submodels", [])
    for sm_data in submodels:
        try:
            sm = Submodel.model_validate(sm_data)
            if await submodel_repo.exists(sm.id):
                errors.append(f"Submodel already exists: {sm.id}")
            else:
                await submodel_repo.create(sm)
                imported_submodels += 1
        except Exception as e:
            errors.append(f"Failed to import Submodel: {e}")

    # Import ConceptDescriptions
    cds = environment.get("conceptDescriptions", [])
    for cd_data in cds:
        try:
            cd = ConceptDescription.model_validate(cd_data)
            if await cd_repo.exists(cd.id):
                errors.append(f"ConceptDescription already exists: {cd.id}")
            else:
                await cd_repo.create(cd)
                imported_cds += 1
        except Exception as e:
            errors.append(f"Failed to import ConceptDescription: {e}")

    await session.commit()

    return {
        "imported": {
            "shells": imported_shells,
            "submodels": imported_submodels,
            "conceptDescriptions": imported_cds,
        },
        "errors": errors,
    }
