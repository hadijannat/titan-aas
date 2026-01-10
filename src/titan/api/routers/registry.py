"""AAS Registry API router.

Implements IDTA-01002 Part 2 Registry endpoints:
- GET    /shell-descriptors                           - List all AAS descriptors
- POST   /shell-descriptors                           - Create AAS descriptor
- GET    /shell-descriptors/{aasIdentifier}           - Get AAS descriptor
- PUT    /shell-descriptors/{aasIdentifier}           - Update AAS descriptor
- DELETE /shell-descriptors/{aasIdentifier}           - Delete AAS descriptor
- GET    /submodel-descriptors                        - List all Submodel descriptors
- POST   /submodel-descriptors                        - Create Submodel descriptor
- GET    /submodel-descriptors/{submodelIdentifier}   - Get Submodel descriptor
- PUT    /submodel-descriptors/{submodelIdentifier}   - Update Submodel descriptor
- DELETE /submodel-descriptors/{submodelIdentifier}   - Delete Submodel descriptor

All identifiers in path segments are Base64URL encoded per IDTA spec.
"""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.errors import (
    ConflictError,
    InvalidBase64UrlError,
    NotFoundError,
    PreconditionFailedError,
)
from titan.api.pagination import DEFAULT_LIMIT, LimitParam
from titan.api.responses import json_bytes_response
from titan.core.canonicalize import canonical_bytes
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url
from titan.core.model.registry import (
    AssetAdministrationShellDescriptor,
    SubmodelDescriptor,
)
from titan.persistence.db import get_session
from titan.persistence.registry import (
    AasDescriptorRepository,
    SubmodelDescriptorRepository,
)

router = APIRouter(tags=["Registry"])


# Dependencies
async def get_aas_descriptor_repo(
    session: AsyncSession = Depends(get_session),
) -> AasDescriptorRepository:
    """Get AAS Descriptor repository instance."""
    return AasDescriptorRepository(session)


async def get_submodel_descriptor_repo(
    session: AsyncSession = Depends(get_session),
) -> SubmodelDescriptorRepository:
    """Get Submodel Descriptor repository instance."""
    return SubmodelDescriptorRepository(session)


# =============================================================================
# Shell Descriptors (AAS Registry)
# =============================================================================


@router.get("/shell-descriptors")
async def get_all_shell_descriptors(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    asset_kind: str | None = None,
    asset_type: str | None = None,
    id_short: str | None = None,
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
) -> Response:
    """Get all AAS Descriptors.

    Returns a paginated list of all AAS descriptors in the registry.
    Supports filtering by assetKind, assetType, and idShort (SSP-004).
    """
    results = await repo.list_all(limit=limit, offset=0)

    items = []
    for doc_bytes, _ in results:
        doc = orjson.loads(doc_bytes)

        # Apply filters (SSP-004 Query Profile)
        if id_short and doc.get("idShort") != id_short:
            continue

        if asset_kind or asset_type:
            asset_info = doc.get("assetInformation", {})
            if asset_kind and asset_info.get("assetKind") != asset_kind:
                continue
            if asset_type and asset_info.get("assetType") != asset_type:
                continue

        items.append(doc)

    response_data = {
        "result": items,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.post("/shell-descriptors", status_code=201)
async def post_shell_descriptor(
    descriptor: AssetAdministrationShellDescriptor,
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new AAS Descriptor.

    The AAS identifier must be unique.
    """
    if await repo.exists(descriptor.id):
        raise ConflictError("AssetAdministrationShellDescriptor", descriptor.id)

    doc_bytes, etag = await repo.create(descriptor)
    await session.commit()

    return Response(
        content=doc_bytes,
        status_code=201,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.get("/shell-descriptors/{aas_identifier}")
async def get_shell_descriptor_by_id(
    aas_identifier: str,
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
) -> Response:
    """Get a specific AAS Descriptor by identifier.

    The identifier must be Base64URL encoded.
    """
    try:
        identifier = decode_id_from_b64url(aas_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(aas_identifier)

    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("AssetAdministrationShellDescriptor", identifier)

    doc_bytes, etag = result

    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.put("/shell-descriptors/{aas_identifier}")
async def put_shell_descriptor_by_id(
    aas_identifier: str,
    descriptor: AssetAdministrationShellDescriptor,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update an existing AAS Descriptor."""
    try:
        identifier = decode_id_from_b64url(aas_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(aas_identifier)

    if if_match:
        current = await repo.get_bytes_by_id(identifier)
        if current:
            _, current_etag = current
            if if_match.strip('"') != current_etag:
                raise PreconditionFailedError()

    result = await repo.update(identifier, descriptor)
    if result is None:
        raise NotFoundError("AssetAdministrationShellDescriptor", identifier)

    doc_bytes, etag = result
    await session.commit()

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete("/shell-descriptors/{aas_identifier}", status_code=204)
async def delete_shell_descriptor_by_id(
    aas_identifier: str,
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete an AAS Descriptor."""
    try:
        identifier = decode_id_from_b64url(aas_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(aas_identifier)

    deleted = await repo.delete(identifier)
    if not deleted:
        raise NotFoundError("AssetAdministrationShellDescriptor", identifier)

    await session.commit()
    return Response(status_code=204)


# =============================================================================
# Shell Descriptors Bulk Operations (SSP-003)
# =============================================================================


@router.post("/shell-descriptors/$bulk", status_code=201)
async def bulk_create_shell_descriptors(
    descriptors: list[AssetAdministrationShellDescriptor],
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Bulk create or update AAS Descriptors.

    Creates new descriptors or updates existing ones.
    Returns a summary of created and updated counts.
    """
    created = 0
    updated = 0

    for descriptor in descriptors:
        if await repo.exists(descriptor.id):
            await repo.update(descriptor.id, descriptor)
            updated += 1
        else:
            await repo.create(descriptor)
            created += 1

    await session.commit()

    result = {
        "created": created,
        "updated": updated,
        "total": len(descriptors),
    }

    return Response(
        content=canonical_bytes(result),
        status_code=201,
        media_type="application/json",
    )


@router.delete("/shell-descriptors/$bulk")
async def bulk_delete_shell_descriptors(
    identifiers: list[str],
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Bulk delete AAS Descriptors.

    Accepts a list of identifiers (not Base64URL encoded).
    Returns a summary of deleted and not found counts.
    """
    deleted = 0
    not_found = 0

    for identifier in identifiers:
        if await repo.delete(identifier):
            deleted += 1
        else:
            not_found += 1

    await session.commit()

    result = {
        "deleted": deleted,
        "notFound": not_found,
        "total": len(identifiers),
    }

    return Response(
        content=canonical_bytes(result),
        media_type="application/json",
    )


# =============================================================================
# Submodel Descriptors (Submodel Registry)
# =============================================================================


@router.get("/submodel-descriptors")
async def get_all_submodel_descriptors(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    semantic_id: str | None = None,
    id_short: str | None = None,
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
) -> Response:
    """Get all Submodel Descriptors.

    Returns a paginated list of all Submodel descriptors in the registry.
    Supports filtering by semanticId and idShort (SSP-004).
    """
    if semantic_id:
        results = await repo.find_by_semantic_id(semantic_id, limit=limit)
    else:
        results = await repo.list_all(limit=limit, offset=0)

    items = []
    for doc_bytes, _ in results:
        doc = orjson.loads(doc_bytes)

        # Apply idShort filter (SSP-004)
        if id_short and doc.get("idShort") != id_short:
            continue

        items.append(doc)

    response_data = {
        "result": items,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.post("/submodel-descriptors", status_code=201)
async def post_submodel_descriptor(
    descriptor: SubmodelDescriptor,
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new Submodel Descriptor.

    The Submodel identifier must be unique.
    """
    if await repo.exists(descriptor.id):
        raise ConflictError("SubmodelDescriptor", descriptor.id)

    doc_bytes, etag = await repo.create(descriptor)
    await session.commit()

    return Response(
        content=doc_bytes,
        status_code=201,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.get("/submodel-descriptors/{submodel_identifier}")
async def get_submodel_descriptor_by_id(
    submodel_identifier: str,
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
) -> Response:
    """Get a specific Submodel Descriptor by identifier.

    The identifier must be Base64URL encoded.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("SubmodelDescriptor", identifier)

    doc_bytes, etag = result

    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.put("/submodel-descriptors/{submodel_identifier}")
async def put_submodel_descriptor_by_id(
    submodel_identifier: str,
    descriptor: SubmodelDescriptor,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update an existing Submodel Descriptor."""
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    if if_match:
        current = await repo.get_bytes_by_id(identifier)
        if current:
            _, current_etag = current
            if if_match.strip('"') != current_etag:
                raise PreconditionFailedError()

    result = await repo.update(identifier, descriptor)
    if result is None:
        raise NotFoundError("SubmodelDescriptor", identifier)

    doc_bytes, etag = result
    await session.commit()

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete("/submodel-descriptors/{submodel_identifier}", status_code=204)
async def delete_submodel_descriptor_by_id(
    submodel_identifier: str,
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a Submodel Descriptor."""
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    deleted = await repo.delete(identifier)
    if not deleted:
        raise NotFoundError("SubmodelDescriptor", identifier)

    await session.commit()
    return Response(status_code=204)


# =============================================================================
# Submodel Descriptors Bulk Operations (SSP-003)
# =============================================================================


@router.post("/submodel-descriptors/$bulk", status_code=201)
async def bulk_create_submodel_descriptors(
    descriptors: list[SubmodelDescriptor],
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Bulk create or update Submodel Descriptors.

    Creates new descriptors or updates existing ones.
    Returns a summary of created and updated counts.
    """
    created = 0
    updated = 0

    for descriptor in descriptors:
        if await repo.exists(descriptor.id):
            await repo.update(descriptor.id, descriptor)
            updated += 1
        else:
            await repo.create(descriptor)
            created += 1

    await session.commit()

    result = {
        "created": created,
        "updated": updated,
        "total": len(descriptors),
    }

    return Response(
        content=canonical_bytes(result),
        status_code=201,
        media_type="application/json",
    )


@router.delete("/submodel-descriptors/$bulk")
async def bulk_delete_submodel_descriptors(
    identifiers: list[str],
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Bulk delete Submodel Descriptors.

    Accepts a list of identifiers (not Base64URL encoded).
    Returns a summary of deleted and not found counts.
    """
    deleted = 0
    not_found = 0

    for identifier in identifiers:
        if await repo.delete(identifier):
            deleted += 1
        else:
            not_found += 1

    await session.commit()

    result = {
        "deleted": deleted,
        "notFound": not_found,
        "total": len(identifiers),
    }

    return Response(
        content=canonical_bytes(result),
        media_type="application/json",
    )
