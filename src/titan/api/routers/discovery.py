"""AAS Discovery API router.

Implements IDTA-01002 Part 2 Discovery endpoints:
- GET /lookup/shells - Search AAS by asset identifiers

Discovery allows finding AAS based on:
- globalAssetId: The global identifier of the asset
- specificAssetIds: Domain-specific identifiers (name/value pairs)

Returns a list of AAS identifiers (Base64URL encoded) matching the criteria.
"""

from __future__ import annotations

from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.pagination import DEFAULT_LIMIT, LimitParam
from titan.api.responses import json_bytes_response
from titan.core.canonicalize import canonical_bytes
from titan.core.ids import encode_id_to_b64url
from titan.persistence.db import get_session
from titan.persistence.registry import AasDescriptorRepository
from titan.persistence.tables import AasDescriptorTable

router = APIRouter(prefix="/lookup", tags=["Discovery"])


async def get_aas_descriptor_repo(
    session: AsyncSession = Depends(get_session),
) -> AasDescriptorRepository:
    """Get AAS Descriptor repository instance."""
    return AasDescriptorRepository(session)


@router.get("/shells")
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
