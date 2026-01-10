"""Submodel Repository API router.

Implements IDTA-01002 Part 2 Submodel Repository endpoints:
- GET    /submodels                                        - List all Submodels
- POST   /submodels                                        - Create Submodel
- GET    /submodels/{submodelIdentifier}                   - Get Submodel
- PUT    /submodels/{submodelIdentifier}                   - Update Submodel
- DELETE /submodels/{submodelIdentifier}                   - Delete Submodel
- GET    /submodels/{submodelIdentifier}/submodel-elements - Get all elements
- GET    /submodels/{submodelIdentifier}/submodel-elements/{idShortPath} - Get element
- GET    /submodels/{submodelIdentifier}/$value            - Get Submodel $value

All identifiers in path segments are Base64URL encoded per IDTA spec.
"""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.errors import (
    BadRequestError,
    ConflictError,
    InvalidBase64UrlError,
    NotFoundError,
    PreconditionFailedError,
)
from titan.api.pagination import (
    CursorParam,
    DEFAULT_LIMIT,
    LimitParam,
)
from titan.api.responses import json_bytes_response
from titan.api.routing import (
    ContentParam,
    ExtentParam,
    LevelParam,
    is_fast_path,
)
from titan.cache import RedisCache, get_redis
from titan.core.canonicalize import canonical_bytes
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url, encode_id_to_b64url
from titan.core.model import Submodel
from titan.core.projection import (
    ProjectionModifiers,
    apply_projection,
    extract_value,
    navigate_id_short_path,
)
from titan.persistence.db import get_session
from titan.persistence.repositories import SubmodelRepository

router = APIRouter(prefix="/submodels", tags=["Submodel Repository"])


# Dependency to get repository
async def get_submodel_repo(
    session: AsyncSession = Depends(get_session),
) -> SubmodelRepository:
    """Get Submodel repository instance."""
    return SubmodelRepository(session)


# Dependency to get cache
async def get_cache() -> RedisCache:
    """Get Redis cache instance."""
    redis = await get_redis()
    return RedisCache(redis)


@router.get("")
async def get_all_submodels(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    semantic_id: str | None = None,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    repo: SubmodelRepository = Depends(get_submodel_repo),
) -> Response:
    """Get all Submodels.

    Returns a paginated list of all Submodels in the repository.
    Supports cursor-based pagination for consistent results across pages.
    Optionally filter by semanticId.
    """
    if is_fast_path(request):
        # Fast path: Use zero-copy SQL-level pagination
        paged_result = await repo.list_paged_zero_copy(
            limit=limit, cursor=cursor, semantic_id=semantic_id
        )
        return Response(
            content=paged_result.response_bytes,
            media_type="application/json",
        )
    else:
        # Slow path: Need to apply projections
        if semantic_id:
            results = await repo.find_by_semantic_id(semantic_id, limit=limit)
        else:
            results = await repo.list_all(limit=limit, offset=0)

        items = []
        for doc_bytes, etag in results:
            doc = orjson.loads(doc_bytes)
            modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
            items.append(apply_projection(doc, modifiers))

        response_data = {
            "result": items,
            "paging_metadata": {"cursor": None},
        }

        return json_bytes_response(canonical_bytes(response_data))


@router.post("", status_code=201)
async def post_submodel(
    submodel: Submodel,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new Submodel.

    The Submodel identifier must be unique.
    """
    if await repo.exists(submodel.id):
        raise ConflictError("Submodel", submodel.id)

    try:
        doc_bytes, etag = await repo.create(submodel)
    except ValueError as e:
        raise BadRequestError(str(e)) from e
    await session.commit()

    identifier_b64 = encode_id_to_b64url(submodel.id)
    await cache.set_submodel(identifier_b64, doc_bytes, etag)

    return Response(
        content=doc_bytes,
        status_code=201,
        media_type="application/json",
        headers={"ETag": f'"{etag}"', "Location": f"/submodels/{identifier_b64}"},
    )


@router.get("/{submodel_identifier}")
async def get_submodel_by_id(
    submodel_identifier: str,
    request: Request,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get a specific Submodel by identifier.

    The identifier must be Base64URL encoded.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Fast path: try cache first
    if is_fast_path(request):
        cached = await cache.get_submodel(submodel_identifier)
        if cached:
            doc_bytes, etag = cached
            if if_none_match and if_none_match.strip('"') == etag:
                return Response(status_code=304)
            return Response(
                content=doc_bytes,
                media_type="application/json",
                headers={"ETag": f'"{etag}"'},
            )

    # Cache miss or slow path
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = result
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)

    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    if is_fast_path(request):
        return Response(
            content=doc_bytes,
            media_type="application/json",
            headers={"ETag": f'"{etag}"'},
        )
    else:
        doc = orjson.loads(doc_bytes)
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        projected = apply_projection(doc, modifiers)
        return Response(
            content=canonical_bytes(projected),
            media_type="application/json",
            headers={"ETag": f'"{etag}"'},
        )


@router.put("/{submodel_identifier}")
async def put_submodel_by_id(
    submodel_identifier: str,
    submodel: Submodel,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update an existing Submodel."""
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

    try:
        result = await repo.update(identifier, submodel)
    except ValueError as e:
        raise BadRequestError(str(e)) from e
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = result
    await session.commit()

    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete("/{submodel_identifier}", status_code=204)
async def delete_submodel_by_id(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a Submodel."""
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    deleted = await repo.delete(identifier)
    if not deleted:
        raise NotFoundError("Submodel", identifier)

    await session.commit()

    await cache.delete_submodel(submodel_identifier)
    await cache.invalidate_submodel_elements(submodel_identifier)

    return Response(status_code=204)


@router.get("/{submodel_identifier}/submodel-elements")
async def get_submodel_elements(
    submodel_identifier: str,
    request: Request,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get all SubmodelElements of a Submodel."""
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get submodel
    cached = await cache.get_submodel(submodel_identifier)
    if cached:
        doc_bytes, _ = cached
    else:
        result = await repo.get_bytes_by_id(identifier)
        if result is None:
            raise NotFoundError("Submodel", identifier)
        doc_bytes, etag = result
        await cache.set_submodel(submodel_identifier, doc_bytes, etag)

    doc = orjson.loads(doc_bytes)
    elements = doc.get("submodelElements", [])

    if not is_fast_path(request):
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        elements = [apply_projection(elem, modifiers) for elem in elements]

    response_data = {
        "result": elements,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.get("/{submodel_identifier}/submodel-elements/{id_short_path:path}")
async def get_submodel_element_by_path(
    submodel_identifier: str,
    id_short_path: str,
    request: Request,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get a specific SubmodelElement by idShortPath.

    The idShortPath uses dots as separators: "Collection.Property"
    For list elements, use index notation: "List[0]"
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get submodel
    cached = await cache.get_submodel(submodel_identifier)
    if cached:
        doc_bytes, _ = cached
    else:
        result = await repo.get_bytes_by_id(identifier)
        if result is None:
            raise NotFoundError("Submodel", identifier)
        doc_bytes, etag = result
        await cache.set_submodel(submodel_identifier, doc_bytes, etag)

    doc = orjson.loads(doc_bytes)

    # Navigate to element
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    if not is_fast_path(request):
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        element = apply_projection(element, modifiers)

    return json_bytes_response(canonical_bytes(element))


@router.get("/{submodel_identifier}/$value")
async def get_submodel_value(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $value of a Submodel.

    Returns only the values of all SubmodelElements, stripped of metadata.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    cached = await cache.get_submodel(submodel_identifier)
    if cached:
        doc_bytes, _ = cached
    else:
        result = await repo.get_bytes_by_id(identifier)
        if result is None:
            raise NotFoundError("Submodel", identifier)
        doc_bytes, etag = result
        await cache.set_submodel(submodel_identifier, doc_bytes, etag)

    doc = orjson.loads(doc_bytes)
    elements = doc.get("submodelElements", [])

    # Extract values from all elements
    values = {}
    for elem in elements:
        id_short = elem.get("idShort")
        if id_short:
            values[id_short] = extract_value(elem)

    return json_bytes_response(canonical_bytes(values))


@router.get("/{submodel_identifier}/submodel-elements/{id_short_path:path}/$value")
async def get_element_value(
    submodel_identifier: str,
    id_short_path: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $value of a specific SubmodelElement.

    Returns only the value, stripped of metadata.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Check element value cache first
    cached_value = await cache.get_element_value(submodel_identifier, id_short_path)
    if cached_value:
        return Response(content=cached_value, media_type="application/json")

    # Get submodel
    cached = await cache.get_submodel(submodel_identifier)
    if cached:
        doc_bytes, _ = cached
    else:
        result = await repo.get_bytes_by_id(identifier)
        if result is None:
            raise NotFoundError("Submodel", identifier)
        doc_bytes, etag = result
        await cache.set_submodel(submodel_identifier, doc_bytes, etag)

    doc = orjson.loads(doc_bytes)

    # Navigate to element
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    # Extract value
    value = extract_value(element)
    value_bytes = canonical_bytes(value)

    # Cache the value
    await cache.set_element_value(submodel_identifier, id_short_path, value_bytes)

    return Response(content=value_bytes, media_type="application/json")
