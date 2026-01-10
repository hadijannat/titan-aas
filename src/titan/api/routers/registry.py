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
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url, encode_id_to_b64url
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
    repo: AasDescriptorRepository = Depends(get_aas_descriptor_repo),
) -> Response:
    """Get all AAS Descriptors.

    Returns a paginated list of all AAS descriptors in the registry.
    """
    results = await repo.list_all(limit=limit, offset=0)

    items = [orjson.loads(doc_bytes) for doc_bytes, _ in results]

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
# Submodel Descriptors (Submodel Registry)
# =============================================================================


@router.get("/submodel-descriptors")
async def get_all_submodel_descriptors(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    semantic_id: str | None = None,
    repo: SubmodelDescriptorRepository = Depends(get_submodel_descriptor_repo),
) -> Response:
    """Get all Submodel Descriptors.

    Returns a paginated list of all Submodel descriptors in the registry.
    Optionally filter by semanticId.
    """
    if semantic_id:
        results = await repo.find_by_semantic_id(semantic_id, limit=limit)
    else:
        results = await repo.list_all(limit=limit, offset=0)

    items = [orjson.loads(doc_bytes) for doc_bytes, _ in results]

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
