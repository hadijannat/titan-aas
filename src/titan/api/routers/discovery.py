"""AAS Discovery API router.

Implements IDTA-01002 Part 2 Discovery endpoints (SSP-001/SSP-002):
- POST /lookup/shellsByAssetLink - Bulk search AAS by asset links (SSP-002)
- GET /lookup/shells/{aasIdentifier} - Get asset links for an AAS (SSP-002)
- POST /lookup/shells/{aasIdentifier} - Create/replace asset links (SSP-001)
- DELETE /lookup/shells/{aasIdentifier} - Delete asset links (SSP-001)
- GET /lookup/shells - Search AAS by asset identifiers (deprecated, SSP-001)

Discovery allows finding AAS based on:
- globalAssetId: The global identifier of the asset (name="globalAssetId")
- specificAssetIds: Domain-specific identifiers (name/value pairs)

Returns a list of AAS identifiers (Base64URL encoded) matching the criteria.
"""

from __future__ import annotations

from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.pagination import DEFAULT_LIMIT, LimitParam
from titan.api.responses import json_bytes_response
from titan.core.canonicalize import canonical_bytes
from titan.core.ids import decode_id_from_b64url, encode_id_to_b64url
from titan.persistence.db import get_session
from titan.persistence.registry import AasDescriptorRepository
from titan.persistence.tables import AasDescriptorTable
from titan.security.deps import require_permission
from titan.security.rbac import Permission

router = APIRouter(prefix="/lookup", tags=["Discovery"])


class AssetLink(BaseModel):
    """Asset link for discovery queries (IDTA-01002 Part 2 v3.0).

    Per Constraint AASd-116, the global asset ID is represented as a
    specific asset ID with name="globalAssetId".
    """

    name: Annotated[str, Field(min_length=1, max_length=64)]
    value: Annotated[str, Field(min_length=1, max_length=2000)]


async def get_aas_descriptor_repo(
    session: AsyncSession = Depends(get_session),
) -> AasDescriptorRepository:
    """Get AAS Descriptor repository instance."""
    return AasDescriptorRepository(session)


@router.get(
    "/shells",
    dependencies=[Depends(require_permission(Permission.READ_DESCRIPTOR))],
)
async def lookup_shells(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    asset_ids: Annotated[
        list[str] | None,
        Query(
            alias="assetIds",
            description="List of asset identifiers to search for (Base64URL encoded JSON)",
        ),
    ] = None,
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Look up AAS by asset identifiers.

    Search for AAS descriptors matching the provided asset identifiers.
    The assetIds parameter accepts Base64URL-encoded JSON objects with:
    - globalAssetId: string (optional)
    - specificAssetIds: array of {name, value} objects (optional)

    Returns a list of AAS identifiers (Base64URL encoded) matching any of the criteria.

    Example:
        GET /lookup/shells?assetIds=eyJnbG9iYWxBc3NldElkIjoiaHR0cHM6Ly9leGFtcGxlLmNvbS9hc3NldC8xIn0
    """
    if not asset_ids:
        # No filter - return all AAS identifiers
        stmt = (
            select(AasDescriptorTable.identifier)
            .order_by(AasDescriptorTable.created_at)
            .limit(limit)
        )
        result = await session.execute(stmt)
        identifiers = [encode_id_to_b64url(row.identifier) for row in result.all()]
    else:
        # Parse and search by asset IDs
        identifiers = []
        seen = set()

        for asset_id_b64 in asset_ids:
            # Decode Base64URL-encoded JSON
            try:
                import base64

                # Restore padding
                padded = asset_id_b64 + "=" * ((4 - len(asset_id_b64) % 4) % 4)
                json_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
                asset_id_obj = orjson.loads(json_bytes)
            except Exception:
                # Skip invalid asset IDs
                continue

            # Search by globalAssetId
            if "globalAssetId" in asset_id_obj:
                global_asset_id = asset_id_obj["globalAssetId"]
                results = await repo.find_by_global_asset_id(global_asset_id, limit=limit)
                for doc_bytes, _ in results:
                    doc = orjson.loads(doc_bytes)
                    aas_id = doc.get("id")
                    if aas_id and aas_id not in seen:
                        seen.add(aas_id)
                        identifiers.append(encode_id_to_b64url(aas_id))

            # Search by specificAssetIds
            if "specificAssetIds" in asset_id_obj:
                for specific_id in asset_id_obj.get("specificAssetIds", []):
                    name = specific_id.get("name")
                    value = specific_id.get("value")
                    if name and value:
                        results = await repo.find_by_specific_asset_id(name, value, limit=limit)
                        for doc_bytes, _ in results:
                            doc = orjson.loads(doc_bytes)
                            aas_id = doc.get("id")
                            if aas_id and aas_id not in seen:
                                seen.add(aas_id)
                                identifiers.append(encode_id_to_b64url(aas_id))

    response_data = {
        "result": identifiers,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.get("/submodels")
async def lookup_submodels(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    semantic_id: Annotated[
        str | None,
        Query(
            alias="semanticId",
            description="Semantic ID to filter Submodels (Base64URL encoded)",
        ),
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Look up Submodels by semantic ID.

    Search for Submodel descriptors matching the provided semantic ID.

    Returns a list of Submodel identifiers (Base64URL encoded) matching the criteria.
    """
    from titan.persistence.registry import SubmodelDescriptorRepository
    from titan.persistence.tables import SubmodelDescriptorTable

    repo = SubmodelDescriptorRepository(session)

    if semantic_id:
        # Decode Base64URL-encoded semantic ID
        try:
            import base64

            padded = semantic_id + "=" * ((4 - len(semantic_id) % 4) % 4)
            decoded_semantic_id = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        except Exception:
            decoded_semantic_id = semantic_id  # Use as-is if not encoded

        results = await repo.find_by_semantic_id(decoded_semantic_id, limit=limit)
        identifiers = []
        for doc_bytes, _ in results:
            doc = orjson.loads(doc_bytes)
            sm_id = doc.get("id")
            if sm_id:
                identifiers.append(encode_id_to_b64url(sm_id))
    else:
        # No filter - return all Submodel identifiers
        stmt = (
            select(SubmodelDescriptorTable.identifier)
            .order_by(SubmodelDescriptorTable.created_at)
            .limit(limit)
        )
        result = await session.execute(stmt)
        identifiers = [encode_id_to_b64url(row.identifier) for row in result.all()]

    response_data = {
        "result": identifiers,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


# =============================================================================
# SSP-002 READ Profile Endpoints
# =============================================================================


@router.post(
    "/shellsByAssetLink",
    dependencies=[Depends(require_permission(Permission.READ_DESCRIPTOR))],
    summary="Search AAS IDs by asset links",
    description="Returns a list of AAS IDs linked to the provided asset identifiers. "
    "Per Constraint AASd-116, set name='globalAssetId' to search by global asset ID.",
)
async def search_shells_by_asset_link(
    request: Request,
    asset_links: list[AssetLink],
    limit: LimitParam = DEFAULT_LIMIT,
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
) -> Response:
    """Bulk search for AAS by asset links (IDTA-01002 SSP-002).

    This is the non-deprecated way to search for AAS by asset identifiers.
    Accepts an array of AssetLink objects in the request body.

    Example request body:
        [
            {"name": "globalAssetId", "value": "https://example.com/asset/1"},
            {"name": "serialNumber", "value": "SN12345"}
        ]
    """
    identifiers: list[str] = []
    seen: set[str] = set()

    for asset_link in asset_links:
        if asset_link.name == "globalAssetId":
            # Search by global asset ID
            results = await repo.find_by_global_asset_id(asset_link.value, limit=limit)
            for doc_bytes, _ in results:
                doc = orjson.loads(doc_bytes)
                aas_id = doc.get("id")
                if aas_id and aas_id not in seen:
                    seen.add(aas_id)
                    identifiers.append(encode_id_to_b64url(aas_id))
        else:
            # Search by specific asset ID
            results = await repo.find_by_specific_asset_id(
                asset_link.name, asset_link.value, limit=limit
            )
            for doc_bytes, _ in results:
                doc = orjson.loads(doc_bytes)
                aas_id = doc.get("id")
                if aas_id and aas_id not in seen:
                    seen.add(aas_id)
                    identifiers.append(encode_id_to_b64url(aas_id))

    response_data = {
        "result": identifiers,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/shells/{aas_identifier}",
    dependencies=[Depends(require_permission(Permission.READ_DESCRIPTOR))],
    summary="Get asset links for an AAS",
    description="Returns all asset identifiers linked to the specified AAS. "
    "The global asset ID is returned as a specific asset ID with name='globalAssetId'.",
)
async def get_asset_links_by_id(
    aas_identifier: Annotated[
        str,
        Path(
            alias="aas_identifier",
            description="Base64URL-encoded AAS identifier",
        ),
    ],
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
) -> Response:
    """Get all asset links for an AAS (IDTA-01002 SSP-002).

    Returns the global asset ID (as name='globalAssetId') and all specific
    asset IDs associated with the AAS descriptor.
    """
    # Decode the AAS identifier
    try:
        aas_id = decode_id_from_b64url(aas_identifier)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Base64URL-encoded identifier: {e}",
        )

    # Get the AAS descriptor
    result = await repo.get_bytes_by_id(aas_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AAS descriptor not found: {aas_id}",
        )

    doc_bytes, _ = result
    doc = orjson.loads(doc_bytes)

    # Build list of asset links
    asset_links: list[dict[str, str]] = []

    # Add global asset ID (per AASd-116)
    asset_info = doc.get("assetInformation")
    if not isinstance(asset_info, dict):
        asset_info = {}
    global_asset_id = asset_info.get("globalAssetId") or doc.get("globalAssetId")
    if global_asset_id:
        asset_links.append({"name": "globalAssetId", "value": global_asset_id})

    # Add specific asset IDs
    specific_asset_ids = asset_info.get("specificAssetIds") or doc.get("specificAssetIds") or []
    for specific_id in specific_asset_ids:
        name = specific_id.get("name")
        value = specific_id.get("value")
        if name and value:
            asset_links.append({"name": name, "value": value})

    return json_bytes_response(canonical_bytes(asset_links))


# =============================================================================
# SSP-001 FULL Profile Endpoints (Write Operations)
# =============================================================================


@router.post(
    "/shells/{aas_identifier}",
    dependencies=[Depends(require_permission(Permission.UPDATE_DESCRIPTOR))],
    status_code=status.HTTP_201_CREATED,
    summary="Create or replace asset links for an AAS",
    description="Creates or replaces all asset identifiers linked to the specified AAS. "
    "Existing links are replaced with the provided set.",
)
async def post_asset_links_by_id(
    aas_identifier: Annotated[
        str,
        Path(
            alias="aas_identifier",
            description="Base64URL-encoded AAS identifier",
        ),
    ],
    asset_links: list[AssetLink],
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create or replace asset links for an AAS (IDTA-01002 SSP-001).

    Replaces all existing asset links with the provided set. The global
    asset ID can be updated by providing name='globalAssetId'.
    """
    # Decode the AAS identifier
    try:
        aas_id = decode_id_from_b64url(aas_identifier)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Base64URL-encoded identifier: {e}",
        )

    # Get the existing AAS descriptor
    result = await repo.get_bytes_by_id(aas_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AAS descriptor not found: {aas_id}",
        )

    doc_bytes, _ = result
    doc = orjson.loads(doc_bytes)

    # Update asset information
    if "assetInformation" not in doc:
        doc["assetInformation"] = {}

    # Process the asset links
    new_specific_ids: list[dict[str, str]] = []
    new_global_asset_id: str | None = None
    for link in asset_links:
        if link.name == "globalAssetId":
            new_global_asset_id = link.value
        else:
            new_specific_ids.append({"name": link.name, "value": link.value})

    # Replace asset IDs (top-level fields)
    doc["globalAssetId"] = new_global_asset_id
    doc["specificAssetIds"] = new_specific_ids

    # Keep assetInformation in sync for compatibility
    asset_info = doc.get("assetInformation")
    if not isinstance(asset_info, dict):
        asset_info = {}
    asset_info["globalAssetId"] = new_global_asset_id
    asset_info["specificAssetIds"] = new_specific_ids
    doc["assetInformation"] = asset_info

    # Update the descriptor in the database
    from titan.core.model.registry import AssetAdministrationShellDescriptor

    updated_descriptor = AssetAdministrationShellDescriptor.model_validate(doc)
    await repo.update(aas_id, updated_descriptor)
    await session.commit()

    # Return the new asset links
    return json_bytes_response(
        canonical_bytes([{"name": link.name, "value": link.value} for link in asset_links]),
        status_code=status.HTTP_201_CREATED,
    )


@router.delete(
    "/shells/{aas_identifier}",
    dependencies=[Depends(require_permission(Permission.DELETE_DESCRIPTOR))],
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete asset links for an AAS",
    description="Deletes all asset identifiers linked to the specified AAS. "
    "The AAS will no longer be discoverable via asset ID lookups.",
)
async def delete_asset_links_by_id(
    aas_identifier: Annotated[
        str,
        Path(
            alias="aas_identifier",
            description="Base64URL-encoded AAS identifier",
        ),
    ],
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete all asset links for an AAS (IDTA-01002 SSP-001).

    Removes the global asset ID and all specific asset IDs from the AAS
    descriptor, making it undiscoverable via asset ID lookups.
    """
    # Decode the AAS identifier
    try:
        aas_id = decode_id_from_b64url(aas_identifier)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Base64URL-encoded identifier: {e}",
        )

    # Get the existing AAS descriptor
    result = await repo.get_bytes_by_id(aas_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AAS descriptor not found: {aas_id}",
        )

    doc_bytes, _ = result
    doc = orjson.loads(doc_bytes)

    # Clear asset information (remove links while keeping descriptor valid)
    doc["globalAssetId"] = None
    doc["specificAssetIds"] = []

    asset_info = doc.get("assetInformation")
    if isinstance(asset_info, dict):
        if "assetKind" not in doc and "assetKind" in asset_info:
            doc["assetKind"] = asset_info["assetKind"]
        if "assetType" not in doc and "assetType" in asset_info:
            doc["assetType"] = asset_info["assetType"]
    doc.pop("assetInformation", None)

    # Update the descriptor in the database
    from titan.core.model.registry import AssetAdministrationShellDescriptor

    updated_descriptor = AssetAdministrationShellDescriptor.model_validate(doc)
    await repo.update(aas_id, updated_descriptor)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
