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

from typing import Any

import orjson
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.errors import (
    BadRequestError,
    ConflictError,
    InvalidBase64UrlError,
    NotFoundError,
    PreconditionFailedError,
)
from titan.api.pagination import (
    DEFAULT_LIMIT,
    CursorParam,
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
from titan.core.element_operations import (
    ElementExistsError,
    ElementNotFoundError,
    InvalidPathError,
    delete_element,
    insert_element,
    patch_element,
    replace_element,
    update_element_value,
)
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url, encode_id_to_b64url
from titan.core.model import Submodel
from titan.core.projection import (
    ProjectionModifiers,
    apply_projection,
    extract_metadata,
    extract_path,
    extract_reference,
    extract_value,
    navigate_id_short_path,
)
from titan.events import EventType, get_event_bus, publish_submodel_deleted, publish_submodel_event
from titan.persistence.db import get_session
from titan.persistence.repositories import SubmodelRepository
from titan.security.abac import ResourceType
from titan.security.deps import require_permission
from titan.security.rbac import Permission

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


@router.get(
    "",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
async def get_all_submodels(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    semantic_id: str | None = Query(None, alias="semanticId"),
    id_short: str | None = Query(None, alias="idShort"),
    kind: str | None = Query(None, description="Filter by kind: Instance or Template"),
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    repo: SubmodelRepository = Depends(get_submodel_repo),
) -> Response:
    """Get all Submodels.

    Returns a paginated list of all Submodels in the repository.
    Supports cursor-based pagination for consistent results across pages.
    Optionally filter by semanticId, idShort, or kind (Template/Instance).
    """
    has_id_short_filter = id_short is not None
    has_kind_filter = kind is not None

    if is_fast_path(request) and not has_id_short_filter and not has_kind_filter:
        # Fast path: Use zero-copy SQL-level pagination (semanticId supported at SQL level)
        paged_result = await repo.list_paged_zero_copy(
            limit=limit, cursor=cursor, semantic_id=semantic_id
        )
        return Response(
            content=paged_result.response_bytes,
            media_type="application/json",
        )
    else:
        # Slow path: Need to apply projections or idShort filter
        if semantic_id and not has_id_short_filter:
            results = await repo.find_by_semantic_id(semantic_id, limit=limit)
        else:
            results = await repo.list_all(limit=limit, offset=0)

        items = []
        for doc_bytes, etag in results:
            doc = orjson.loads(doc_bytes)

            # Apply idShort filter
            if id_short and doc.get("idShort") != id_short:
                continue

            # Apply kind filter (Template/Instance)
            if kind and doc.get("kind") != kind:
                continue

            # Apply semanticId filter (if not already filtered at SQL level)
            if semantic_id and has_id_short_filter:
                doc_semantic_id = None
                sem_ref = doc.get("semanticId")
                if sem_ref and isinstance(sem_ref, dict):
                    keys = sem_ref.get("keys", [])
                    if keys and isinstance(keys, list) and len(keys) > 0:
                        doc_semantic_id = keys[-1].get("value")
                if doc_semantic_id != semantic_id:
                    continue

            # Apply projections if needed
            if not is_fast_path(request):
                modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
                doc = apply_projection(doc, modifiers)

            items.append(doc)

        response_data = {
            "result": items,
            "paging_metadata": {"cursor": None},
        }

        return json_bytes_response(canonical_bytes(response_data))


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CREATE_SUBMODEL))],
)
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

    # Extract semantic_id for event filtering
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    # Publish event for real-time subscribers
    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.CREATED,
        identifier=submodel.id,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    return Response(
        content=doc_bytes,
        status_code=201,
        media_type="application/json",
        headers={"ETag": f'"{etag}"', "Location": f"/submodels/{identifier_b64}"},
    )


@router.get(
    "/{submodel_identifier}",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
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


@router.put(
    "/{submodel_identifier}",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
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

    # Extract semantic_id for event filtering
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    # Publish event for real-time subscribers
    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete(
    "/{submodel_identifier}",
    status_code=204,
    dependencies=[
        Depends(
            require_permission(
                Permission.DELETE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
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

    # Publish event for real-time subscribers
    await publish_submodel_deleted(
        event_bus=get_event_bus(),
        identifier=identifier,
        identifier_b64=submodel_identifier,
    )

    return Response(status_code=204)


@router.get(
    "/{submodel_identifier}/submodel-elements",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
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


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
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


@router.get(
    "/{submodel_identifier}/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
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


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
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


@router.get(
    "/{submodel_identifier}/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_metadata(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $metadata of a Submodel.

    Returns only metadata fields (no values) per IDTA-01002.
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
    metadata = extract_metadata(doc)

    return json_bytes_response(canonical_bytes(metadata))


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def get_element_metadata(
    submodel_identifier: str,
    id_short_path: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $metadata of a specific SubmodelElement.

    Returns only metadata fields (no values) per IDTA-01002.
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

    # Navigate to element
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    metadata = extract_metadata(element)
    return json_bytes_response(canonical_bytes(metadata))


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/$reference",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def get_element_reference(
    submodel_identifier: str,
    id_short_path: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $reference of a specific SubmodelElement.

    Returns a ModelReference pointing to this element per IDTA-01002.
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
    submodel_id = doc.get("id", "")

    # Navigate to element
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    reference = extract_reference(element, submodel_id, id_short_path)
    return json_bytes_response(canonical_bytes(reference))


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/$path",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def get_element_path(
    submodel_identifier: str,
    id_short_path: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $path of a specific SubmodelElement.

    Returns the idShortPath representation per IDTA-01002.
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

    # Navigate to element
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    path_result = extract_path(element, id_short_path)
    return json_bytes_response(canonical_bytes(path_result))


# ============================================================================
# SubmodelElement CRUD Endpoints (POST, PUT, PATCH, DELETE)
# ============================================================================


@router.post(
    "/{submodel_identifier}/submodel-elements",
    status_code=201,
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def post_submodel_element(
    submodel_identifier: str,
    element: dict,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new SubmodelElement at root level.

    The element idShort must be unique within the Submodel.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, _ = result
    doc = orjson.loads(doc_bytes)

    # Insert element at root
    try:
        updated_doc = insert_element(doc, None, element)
    except ElementExistsError as e:
        raise ConflictError("SubmodelElement", e.path)
    except (InvalidPathError, ValueError) as e:
        raise BadRequestError(str(e))

    # Update submodel in database
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e
    update_result = await repo.update(identifier, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    # Update cache
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    # Publish event
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    id_short = element.get("idShort", "")
    return Response(
        content=canonical_bytes(element),
        status_code=201,
        media_type="application/json",
        headers={"Location": f"/submodels/{submodel_identifier}/submodel-elements/{id_short}"},
    )


@router.post(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}",
    status_code=201,
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def post_nested_submodel_element(
    submodel_identifier: str,
    id_short_path: str,
    element: dict,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new SubmodelElement within a container element.

    The parent path must point to a SubmodelElementCollection or SubmodelElementList.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, _ = result
    doc = orjson.loads(doc_bytes)

    # Insert element at specified path
    try:
        updated_doc = insert_element(doc, id_short_path, element)
    except ElementExistsError as e:
        raise ConflictError("SubmodelElement", e.path)
    except InvalidPathError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except ValueError as e:
        raise BadRequestError(str(e))

    # Update submodel in database
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e
    update_result = await repo.update(identifier, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    # Update cache
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    # Publish event
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    container = navigate_id_short_path(updated_doc, id_short_path)
    if container and container.get("modelType") == "SubmodelElementList":
        elements = container.get("value", [])
        new_index = len(elements) - 1 if elements else 0
        new_path = f"{id_short_path}[{new_index}]"
    else:
        id_short = element.get("idShort", "")
        new_path = f"{id_short_path}.{id_short}"
    return Response(
        content=canonical_bytes(element),
        status_code=201,
        media_type="application/json",
        headers={"Location": f"/submodels/{submodel_identifier}/submodel-elements/{new_path}"},
    )


@router.put(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def put_submodel_element(
    submodel_identifier: str,
    id_short_path: str,
    element: dict,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Replace an existing SubmodelElement.

    The element at the given path is completely replaced.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result

    # Check If-Match precondition
    if if_match and if_match.strip('"') != current_etag:
        raise PreconditionFailedError()

    doc = orjson.loads(doc_bytes)

    # Replace element
    try:
        updated_doc = replace_element(doc, id_short_path, element)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e))

    # Update submodel in database
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e
    update_result = await repo.update(identifier, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    # Update cache
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    # Publish event
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    return Response(
        content=canonical_bytes(element),
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.patch(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def patch_submodel_element(
    submodel_identifier: str,
    id_short_path: str,
    updates: dict,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Partially update a SubmodelElement.

    Only the provided fields are updated, other fields remain unchanged.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result

    # Check If-Match precondition
    if if_match and if_match.strip('"') != current_etag:
        raise PreconditionFailedError()

    doc = orjson.loads(doc_bytes)

    # Patch element
    try:
        updated_doc = patch_element(doc, id_short_path, updates)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e))

    # Update submodel in database
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e
    update_result = await repo.update(identifier, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    # Update cache
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    # Publish event
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    # Get updated element for response
    updated_element = navigate_id_short_path(updated_doc, id_short_path)

    return Response(
        content=canonical_bytes(updated_element),
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.patch(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def patch_element_value(
    submodel_identifier: str,
    id_short_path: str,
    value: Any,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update only the value of a SubmodelElement.

    This is a convenience endpoint for updating just the value field.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result

    # Check If-Match precondition
    if if_match and if_match.strip('"') != current_etag:
        raise PreconditionFailedError()

    doc = orjson.loads(doc_bytes)

    # Update value
    try:
        updated_doc = update_element_value(doc, id_short_path, value)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e))

    # Update submodel in database
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e
    update_result = await repo.update(identifier, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    # Update cache
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    # Publish event
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    return Response(
        content=canonical_bytes(value),
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}",
    status_code=204,
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def delete_submodel_element(
    submodel_identifier: str,
    id_short_path: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a SubmodelElement.

    Removes the element at the given path from the Submodel.
    """
    try:
        identifier = decode_id_from_b64url(submodel_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, _ = result
    doc = orjson.loads(doc_bytes)

    # Delete element
    try:
        updated_doc = delete_element(doc, id_short_path)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e))

    # Update submodel in database
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e
    update_result = await repo.update(identifier, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    # Update cache
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    # Publish event
    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    return Response(status_code=204)
