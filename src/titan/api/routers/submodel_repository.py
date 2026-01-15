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

Operation Invocation endpoints (IDTA-01002 Part 2):
- POST   /submodels/{id}/submodel-elements/{path}/invoke          - Invoke operation
- POST   /submodels/{id}/submodel-elements/{path}/invoke-async    - Invoke async
- GET    /submodels/{id}/submodel-elements/{path}/operation-results/{handleId}

All identifiers in path segments are Base64URL encoded per IDTA spec.
"""

from __future__ import annotations

from typing import Any

import orjson
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel as PydanticBaseModel
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.attachment_utils import (
    apply_attachment_payload,
    build_attachment_response,
    clear_attachment_payload,
)
from titan.api.deps import (
    check_not_modified,
    check_precondition,
    decode_identifier,
    json_response_with_etag,
    no_content_response,
)
from titan.api.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from titan.api.operation_utils import arguments_to_value_map, coerce_value_only_arguments
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
from titan.api.submodel_update_utils import (
    apply_submodel_metadata_patch,
    apply_submodel_value_patch,
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
from titan.core.ids import encode_id_to_b64url
from titan.core.model import Submodel
from titan.core.model.submodel_elements import Operation
from titan.core.operation_executor import (
    InvokeOperationRequest,
    InvokeOperationResult,
    OperationExecutor,
    OperationValidationError,
)
from titan.core.projection import (
    ProjectionModifiers,
    apply_projection,
    collect_element_references,
    collect_id_short_paths,
    extract_metadata,
    extract_path,
    extract_reference,
    extract_reference_for_submodel,
    extract_value,
    navigate_id_short_path,
)
from titan.core.templates import (
    InstantiationRequest,
    InstantiationResult,
    instantiate_template,
)
from titan.events import EventType, get_event_bus, publish_submodel_deleted, publish_submodel_event
from titan.events.schemas import OperationExecutionState
from titan.persistence.db import get_session
from titan.persistence.repositories import OperationInvocationRepository, SubmodelRepository
from titan.security.abac import ResourceType
from titan.security.deps import get_current_user, require_permission
from titan.security.oidc import User
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


async def _query_submodels(
    request: Request,
    limit: int,
    cursor: str | None,
    semantic_id: str | None,
    id_short: str | None,
    kind: str | None,
    repo: SubmodelRepository,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load submodel documents with optional filters."""
    has_id_short_filter = id_short is not None
    has_kind_filter = kind is not None

    if is_fast_path(request) and not has_id_short_filter and not has_kind_filter:
        paged_result = await repo.list_paged_zero_copy(
            limit=limit,
            cursor=cursor,
            semantic_id=semantic_id,
        )
        payload = orjson.loads(paged_result.response_bytes)
        items = payload.get("result", [])
        paging = payload.get("paging_metadata") or {"cursor": None}
        return items, paging

    if kind and not has_id_short_filter and not semantic_id:
        results = await repo.find_by_kind(kind, limit=limit)
    elif semantic_id and not has_id_short_filter and not kind:
        results = await repo.find_by_semantic_id(semantic_id, limit=limit)
    else:
        results = await repo.list_all(limit=limit, offset=0)

    items: list[dict[str, Any]] = []
    for doc_bytes, _etag in results:
        doc = orjson.loads(doc_bytes)

        if id_short and doc.get("idShort") != id_short:
            continue
        if kind and doc.get("kind") != kind:
            continue

        if semantic_id and has_id_short_filter:
            doc_semantic_id = None
            sem_ref = doc.get("semanticId")
            if sem_ref and isinstance(sem_ref, dict):
                keys = sem_ref.get("keys", [])
                if keys and isinstance(keys, list) and len(keys) > 0:
                    doc_semantic_id = keys[-1].get("value")
            if doc_semantic_id != semantic_id:
                continue

        items.append(doc)

    return items, {"cursor": None}


async def _persist_submodel_doc_update(
    identifier: str,
    identifier_b64: str,
    updated_doc: dict[str, Any],
    repo: SubmodelRepository,
    cache: RedisCache,
    session: AsyncSession,
) -> tuple[bytes, str, Submodel]:
    """Validate and persist a full Submodel document update."""
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e

    update_result = await repo.update(identifier, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    await cache.set_submodel(identifier_b64, doc_bytes, etag)
    await cache.invalidate_submodel_elements(identifier_b64)

    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    return doc_bytes, etag, submodel


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
        # Slow path: Need to apply projections or filters not supported at zero-copy level
        # Use SQL-level filtering where possible
        if kind and not has_id_short_filter and not semantic_id:
            # Kind-only filter: use SQL-level filtering
            results = await repo.find_by_kind(kind, limit=limit)
        elif semantic_id and not has_id_short_filter and not kind:
            # SemanticId-only filter: use SQL-level filtering
            results = await repo.find_by_semantic_id(semantic_id, limit=limit)
        else:
            # Multiple filters or unsupported: fetch all and filter in memory
            results = await repo.list_all(limit=limit, offset=0)

        items = []
        for doc_bytes, _etag in results:
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


def _extract_submodel_values(doc: dict[str, Any]) -> dict[str, Any]:
    elements = doc.get("submodelElements", [])
    values: dict[str, Any] = {}
    for elem in elements:
        id_short = elem.get("idShort")
        if id_short:
            values[id_short] = extract_value(elem)
    return values


@router.get(
    "/$metadata",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
async def get_all_submodels_metadata(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    semantic_id: str | None = Query(None, alias="semanticId"),
    id_short: str | None = Query(None, alias="idShort"),
    kind: str | None = Query(None, description="Filter by kind: Instance or Template"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
) -> Response:
    """Get all Submodels in $metadata representation."""
    items, paging = await _query_submodels(
        request=request,
        limit=limit,
        cursor=cursor,
        semantic_id=semantic_id,
        id_short=id_short,
        kind=kind,
        repo=repo,
    )
    metadata = [extract_metadata(doc) for doc in items]
    response_data = {"result": metadata, "paging_metadata": paging}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/$reference",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
async def get_all_submodels_reference(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    semantic_id: str | None = Query(None, alias="semanticId"),
    id_short: str | None = Query(None, alias="idShort"),
    kind: str | None = Query(None, description="Filter by kind: Instance or Template"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
) -> Response:
    """Get References for all Submodels."""
    items, paging = await _query_submodels(
        request=request,
        limit=limit,
        cursor=cursor,
        semantic_id=semantic_id,
        id_short=id_short,
        kind=kind,
        repo=repo,
    )
    references = [extract_reference_for_submodel(doc) for doc in items]
    response_data = {"result": references, "paging_metadata": paging}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/$path",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
async def get_all_submodels_path(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    semantic_id: str | None = Query(None, alias="semanticId"),
    id_short: str | None = Query(None, alias="idShort"),
    kind: str | None = Query(None, description="Filter by kind: Instance or Template"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
) -> Response:
    """Get all Submodels in $path representation."""
    items, paging = await _query_submodels(
        request=request,
        limit=limit,
        cursor=cursor,
        semantic_id=semantic_id,
        id_short=id_short,
        kind=kind,
        repo=repo,
    )
    paths = [doc.get("idShort") for doc in items if doc.get("idShort")]
    response_data = {"result": paths, "paging_metadata": paging}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/$value",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
async def get_all_submodels_value(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    semantic_id: str | None = Query(None, alias="semanticId"),
    id_short: str | None = Query(None, alias="idShort"),
    kind: str | None = Query(None, description="Filter by kind: Instance or Template"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
) -> Response:
    """Get all Submodels in $value representation."""
    items, paging = await _query_submodels(
        request=request,
        limit=limit,
        cursor=cursor,
        semantic_id=semantic_id,
        id_short=id_short,
        kind=kind,
        repo=repo,
    )
    values = [_extract_submodel_values(doc) for doc in items]
    response_data = {"result": values, "paging_metadata": paging}
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
    identifier = decode_identifier(submodel_identifier)

    # Fast path: try cache first
    if is_fast_path(request):
        cached = await cache.get_submodel(submodel_identifier)
        if cached:
            doc_bytes, etag = cached
            not_modified = check_not_modified(if_none_match, etag)
            if not_modified:
                return not_modified
            return json_response_with_etag(doc_bytes, etag)

    # Cache miss or slow path
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, etag = result
    await cache.set_submodel(submodel_identifier, doc_bytes, etag)

    not_modified = check_not_modified(if_none_match, etag)
    if not_modified:
        return not_modified

    if is_fast_path(request):
        return json_response_with_etag(doc_bytes, etag)
    else:
        doc = orjson.loads(doc_bytes)
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        projected = apply_projection(doc, modifiers)
        return json_response_with_etag(canonical_bytes(projected), etag)


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
    identifier = decode_identifier(submodel_identifier)
    if identifier != submodel.id:
        raise BadRequestError("Path identifier does not match Submodel.id")

    current = await repo.get_bytes_by_id(identifier)

    if current and if_match:
        _, current_etag = current
        check_precondition(if_match, current_etag)

    try:
        if current is None:
            doc_bytes, etag = await repo.create(submodel)
            await session.commit()

            await cache.set_submodel(submodel_identifier, doc_bytes, etag)
            await cache.invalidate_submodel_elements(submodel_identifier)

            semantic_id = None
            if submodel.semantic_id and submodel.semantic_id.keys:
                semantic_id = submodel.semantic_id.keys[0].value

            await publish_submodel_event(
                event_bus=get_event_bus(),
                event_type=EventType.CREATED,
                identifier=identifier,
                identifier_b64=submodel_identifier,
                doc_bytes=doc_bytes,
                etag=etag,
                semantic_id=semantic_id,
            )

            return json_response_with_etag(
                doc_bytes,
                etag,
                status_code=201,
                location=f"/submodels/{submodel_identifier}",
            )

        doc_bytes, etag = await repo.update(identifier, submodel)
    except ValueError as e:
        raise BadRequestError(str(e)) from e

    await session.commit()

    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

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

    return no_content_response(etag)


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
    identifier = decode_identifier(submodel_identifier)

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
    identifier = decode_identifier(submodel_identifier)

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

    if content == "reference":
        references = collect_element_references(doc)
        response_data = {
            "result": references,
            "paging_metadata": {"cursor": None},
        }
        return json_bytes_response(canonical_bytes(response_data))

    if content == "path":
        paths = collect_id_short_paths(doc)
        response_data = {
            "result": paths,
            "paging_metadata": {"cursor": None},
        }
        return json_bytes_response(canonical_bytes(response_data))

    if not is_fast_path(request):
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        elements = [apply_projection(elem, modifiers) for elem in elements]

    response_data = {
        "result": elements,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{submodel_identifier}/submodel-elements/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_metadata(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $metadata for all SubmodelElements (including hierarchy)."""
    identifier = decode_identifier(submodel_identifier)

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
    metadata = [extract_metadata(elem) for elem in elements]

    response_data = {
        "result": metadata,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{submodel_identifier}/submodel-elements/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_value(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $value for all SubmodelElements (value-only representation)."""
    identifier = decode_identifier(submodel_identifier)

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

    values: dict[str, Any] = {}
    for elem in elements:
        id_short = elem.get("idShort")
        if id_short:
            values[id_short] = extract_value(elem)

    response_data = {
        "result": values,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{submodel_identifier}/submodel-elements/$reference",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_reference(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get References for all SubmodelElements (including hierarchy)."""
    identifier = decode_identifier(submodel_identifier)

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
    references = collect_element_references(doc)

    response_data = {
        "result": references,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{submodel_identifier}/submodel-elements/$path",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_path(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get idShortPaths for all SubmodelElements (including hierarchy)."""
    identifier = decode_identifier(submodel_identifier)

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
    paths = collect_id_short_paths(doc)

    response_data = {
        "result": paths,
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
    identifier = decode_identifier(submodel_identifier)

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

    if content == "reference":
        submodel_id = doc.get("id", "")
        reference = extract_reference(element, submodel_id, id_short_path)
        return json_bytes_response(canonical_bytes(reference))

    if content == "path":
        return json_bytes_response(canonical_bytes(extract_path(element, id_short_path)))

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
    identifier = decode_identifier(submodel_identifier)

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


@router.patch(
    "/{submodel_identifier}/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def patch_submodel_value(
    submodel_identifier: str,
    payload: Any = Body(...),
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Patch Submodel values using idShortPath keys."""
    identifier = decode_identifier(submodel_identifier)
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    values_payload = payload.get("values") if isinstance(payload, dict) else payload
    updated_doc = apply_submodel_value_patch(doc, values_payload)

    _, etag, _ = await _persist_submodel_doc_update(
        identifier,
        submodel_identifier,
        updated_doc,
        repo,
        cache,
        session,
    )

    return no_content_response(etag)


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
    identifier = decode_identifier(submodel_identifier)

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
    identifier = decode_identifier(submodel_identifier)

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


@router.patch(
    "/{submodel_identifier}/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def patch_submodel_metadata(
    submodel_identifier: str,
    updates: dict,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Patch Submodel metadata fields."""
    identifier = decode_identifier(submodel_identifier)
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    updated_doc = apply_submodel_metadata_patch(doc, updates)

    _, etag, _ = await _persist_submodel_doc_update(
        identifier,
        submodel_identifier,
        updated_doc,
        repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.get(
    "/{submodel_identifier}/$reference",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_reference(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $reference of a Submodel."""
    identifier = decode_identifier(submodel_identifier)

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
    reference = extract_reference_for_submodel(doc)

    return json_bytes_response(canonical_bytes(reference))


@router.get(
    "/{submodel_identifier}/$path",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_path(
    submodel_identifier: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $path representation of a Submodel."""
    identifier = decode_identifier(submodel_identifier)

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
    paths = collect_id_short_paths(doc)

    return json_bytes_response(canonical_bytes(paths))


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
    identifier = decode_identifier(submodel_identifier)

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
    identifier = decode_identifier(submodel_identifier)

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
    identifier = decode_identifier(submodel_identifier)

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
# Attachment Endpoint
# ============================================================================


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/attachment",
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
async def get_element_attachment(
    submodel_identifier: str,
    id_short_path: str,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download attachment for a File or Blob SubmodelElement."""
    identifier = decode_identifier(submodel_identifier)

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
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    model_type = element.get("modelType")
    if model_type not in ("File", "Blob"):
        raise BadRequestError("Attachment is only valid for File or Blob elements")

    value = element.get("value")
    if not value:
        raise NotFoundError("Attachment", id_short_path)

    content_type = element.get("contentType") or "application/octet-stream"
    return await build_attachment_response(value, content_type, session)


@router.put(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/attachment",
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
async def put_element_attachment(
    submodel_identifier: str,
    id_short_path: str,
    file: UploadFile = File(...),
    file_name: str | None = Form(None),
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Upload attachment for a File or Blob SubmodelElement."""
    identifier = decode_identifier(submodel_identifier)

    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    content = await file.read()
    apply_attachment_payload(element, content, file.content_type)

    _, etag, _ = await _persist_submodel_doc_update(
        identifier,
        submodel_identifier,
        doc,
        repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.delete(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/attachment",
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
async def delete_element_attachment(
    submodel_identifier: str,
    id_short_path: str,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete attachment for a File or Blob SubmodelElement."""
    identifier = decode_identifier(submodel_identifier)

    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    if not element.get("value"):
        raise NotFoundError("Attachment", id_short_path)

    clear_attachment_payload(element)

    _, etag, _ = await _persist_submodel_doc_update(
        identifier,
        submodel_identifier,
        doc,
        repo,
        cache,
        session,
    )

    return no_content_response(etag)


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
    identifier = decode_identifier(submodel_identifier)

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
    identifier = decode_identifier(submodel_identifier)

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
    identifier = decode_identifier(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result

    # Check If-Match precondition
    check_precondition(if_match, current_etag)

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

    return no_content_response(etag)


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
    payload: Any = Body(...),
    if_match: str | None = Header(None, alias="If-Match"),
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update only the value of a SubmodelElement.

    This is a convenience endpoint for updating just the value field.
    """
    identifier = decode_identifier(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result

    # Check If-Match precondition
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)

    # Accept either raw JSON value or {"value": ...}
    value = payload
    if isinstance(payload, dict) and "value" in payload:
        value = payload["value"]

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
    identifier = decode_identifier(submodel_identifier)

    # Get existing submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, current_etag = result

    # Check If-Match precondition
    check_precondition(if_match, current_etag)

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
    identifier = decode_identifier(submodel_identifier)

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


# ============================================================================
# Operation Invocation Endpoints (IDTA-01002 Part 2)
# ============================================================================


async def get_operation_invocation_repo(
    session: AsyncSession = Depends(get_session),
) -> OperationInvocationRepository:
    """Get Operation Invocation repository instance."""
    return OperationInvocationRepository(session)


async def _invoke_operation(
    submodel_identifier: str,
    id_short_path: str,
    request_body: InvokeOperationRequest,
    repo: SubmodelRepository,
    invocation_repo: OperationInvocationRepository,
    session: AsyncSession,
    user: User | None,
) -> InvokeOperationResult:
    """Invoke an Operation and persist invocation record."""
    identifier = decode_identifier(submodel_identifier)

    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, _ = result
    doc = orjson.loads(doc_bytes)

    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    if element.get("modelType") != "Operation":
        raise BadRequestError(f"Element at path '{id_short_path}' is not an Operation")

    try:
        operation = Operation.model_validate(element)
    except ValidationError as e:
        raise BadRequestError(f"Invalid Operation element: {e}") from e

    executor = OperationExecutor(get_event_bus())
    requested_by = user.subject if user else None

    try:
        invoke_result = await executor.invoke(
            submodel_id=identifier,
            id_short_path=id_short_path,
            operation=operation,
            request=request_body,
            requested_by=requested_by,
        )
    except OperationValidationError as e:
        raise BadRequestError(e.message)

    await invocation_repo.create(
        invocation_id=invoke_result.invocation_id,
        submodel_id=identifier,
        submodel_id_b64=submodel_identifier,
        id_short_path=id_short_path,
        execution_state=invoke_result.execution_state.value,
        input_arguments=request_body.input_arguments,
        inoutput_arguments=request_body.inoutput_arguments,
        timeout_ms=request_body.timeout,
        requested_by=requested_by,
    )
    await session.commit()

    return invoke_result


@router.post(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                Permission.INVOKE_OPERATION,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def invoke_operation_sync(
    submodel_identifier: str,
    id_short_path: str,
    request_body: InvokeOperationRequest,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> Response:
    """Invoke an Operation synchronously.

    Validates input arguments against declared inputVariables, emits an
    OperationInvocationEvent, and returns a handle for polling results.

    Note: This endpoint is event-based. Downstream connectors (OPC-UA, Modbus, HTTP)
    subscribe to operation invocation events and execute the operation.
    """
    invoke_result = await _invoke_operation(
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        repo=repo,
        invocation_repo=invocation_repo,
        session=session,
        user=user,
    )

    # Build response per IDTA-01002
    response_data = {
        "executionState": invoke_result.execution_state.value,
        "outputArguments": invoke_result.output_arguments,
        "inoutputArguments": invoke_result.inoutput_arguments,
    }

    return Response(
        content=canonical_bytes(response_data),
        media_type="application/json",
        headers={"X-Invocation-Id": invoke_result.invocation_id},
    )


@router.post(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke/$value",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                Permission.INVOKE_OPERATION,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def invoke_operation_sync_value_only(
    submodel_identifier: str,
    id_short_path: str,
    payload: dict,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> Response:
    """Invoke an Operation synchronously (value-only representation)."""
    input_args = coerce_value_only_arguments(payload.get("inputArguments"), "inputArguments")
    inoutput_args = coerce_value_only_arguments(
        payload.get("inoutputArguments"),
        "inoutputArguments",
    )
    request_body = InvokeOperationRequest.model_validate(
        {
            "inputArguments": input_args,
            "inoutputArguments": inoutput_args,
            "timeout": payload.get("timeout"),
        }
    )

    invoke_result = await _invoke_operation(
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        repo=repo,
        invocation_repo=invocation_repo,
        session=session,
        user=user,
    )

    response_data = {
        "executionState": invoke_result.execution_state.value,
        "outputArguments": arguments_to_value_map(invoke_result.output_arguments),
        "inoutputArguments": arguments_to_value_map(invoke_result.inoutput_arguments),
    }

    return Response(
        content=canonical_bytes(response_data),
        media_type="application/json",
        headers={"X-Invocation-Id": invoke_result.invocation_id},
    )


@router.post(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke-async",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                Permission.INVOKE_OPERATION,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def invoke_operation_async(
    submodel_identifier: str,
    id_short_path: str,
    request_body: InvokeOperationRequest,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> Response:
    """Invoke an Operation asynchronously.

    Returns immediately with a handle (invocation ID) that can be used to
    poll for results via GET operation-results/{handleId}.

    Validates input arguments against declared inputVariables, emits an
    OperationInvocationEvent for downstream connectors to execute.
    """
    invoke_result = await _invoke_operation(
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        repo=repo,
        invocation_repo=invocation_repo,
        session=session,
        user=user,
    )

    # Build async response per IDTA-01002
    response_data = {
        "handleId": invoke_result.invocation_id,
        "executionState": invoke_result.execution_state.value,
    }

    return Response(
        content=canonical_bytes(response_data),
        media_type="application/json",
    )


@router.post(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke-async/$value",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                Permission.INVOKE_OPERATION,
                resource_type=ResourceType.SUBMODEL_ELEMENT,
                resource_id_params=["submodel_identifier", "id_short_path"],
            )
        )
    ],
)
async def invoke_operation_async_value_only(
    submodel_identifier: str,
    id_short_path: str,
    payload: dict,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
) -> Response:
    """Invoke an Operation asynchronously (value-only representation)."""
    input_args = coerce_value_only_arguments(payload.get("inputArguments"), "inputArguments")
    inoutput_args = coerce_value_only_arguments(
        payload.get("inoutputArguments"),
        "inoutputArguments",
    )
    request_body = InvokeOperationRequest.model_validate(
        {
            "inputArguments": input_args,
            "inoutputArguments": inoutput_args,
            "timeout": payload.get("timeout"),
        }
    )

    invoke_result = await _invoke_operation(
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        repo=repo,
        invocation_repo=invocation_repo,
        session=session,
        user=user,
    )

    response_data = {
        "handleId": invoke_result.invocation_id,
        "executionState": invoke_result.execution_state.value,
    }

    return Response(
        content=canonical_bytes(response_data),
        media_type="application/json",
    )


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/operation-results/{handle_id}",
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
async def get_operation_result(
    submodel_identifier: str,
    id_short_path: str,
    handle_id: str,
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
) -> Response:
    """Get the result of an asynchronous operation invocation.

    Returns the current execution state and, if completed, the output arguments.
    Poll this endpoint until executionState is 'completed', 'failed', or 'timeout'.
    """
    identifier = decode_identifier(submodel_identifier)

    # Get invocation record
    invocation = await invocation_repo.get_by_id(handle_id)
    if invocation is None:
        raise NotFoundError("OperationResult", handle_id)

    # Verify it matches the requested submodel/path
    if invocation.id_short_path != id_short_path or invocation.submodel_id != identifier:
        raise NotFoundError("OperationResult", handle_id)

    # Build response per IDTA-01002
    response_data: dict[str, Any] = {
        "executionState": invocation.execution_state,
    }

    # Include results if completed
    if invocation.execution_state == OperationExecutionState.COMPLETED.value:
        response_data["outputArguments"] = invocation.output_arguments
        response_data["inoutputArguments"] = invocation.inoutput_arguments
    elif invocation.execution_state == OperationExecutionState.FAILED.value:
        response_data["message"] = invocation.error_message
        if invocation.error_code:
            response_data["messageType"] = invocation.error_code

    return Response(
        content=canonical_bytes(response_data),
        media_type="application/json",
    )


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/operation-status/{handle_id}",
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
async def get_operation_status(
    submodel_identifier: str,
    id_short_path: str,
    handle_id: str,
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
) -> Response:
    """Get the status of an async operation invocation."""
    identifier = decode_identifier(submodel_identifier)

    invocation = await invocation_repo.get_by_id(handle_id)
    if invocation is None:
        raise NotFoundError("OperationResult", handle_id)
    if invocation.id_short_path != id_short_path or invocation.submodel_id != identifier:
        raise NotFoundError("OperationResult", handle_id)

    response_data: dict[str, Any] = {
        "executionState": invocation.execution_state,
    }
    if invocation.execution_state == OperationExecutionState.FAILED.value:
        response_data["message"] = invocation.error_message
        if invocation.error_code:
            response_data["messageType"] = invocation.error_code

    return Response(
        content=canonical_bytes(response_data),
        media_type="application/json",
    )


@router.get(
    "/{submodel_identifier}/submodel-elements/{id_short_path:path}/operation-results/{handle_id}/$value",
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
async def get_operation_result_value_only(
    submodel_identifier: str,
    id_short_path: str,
    handle_id: str,
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
) -> Response:
    """Get value-only results of an async operation invocation."""
    identifier = decode_identifier(submodel_identifier)

    invocation = await invocation_repo.get_by_id(handle_id)
    if invocation is None:
        raise NotFoundError("OperationResult", handle_id)
    if invocation.id_short_path != id_short_path or invocation.submodel_id != identifier:
        raise NotFoundError("OperationResult", handle_id)

    response_data: dict[str, Any] = {
        "executionState": invocation.execution_state,
    }

    if invocation.execution_state == OperationExecutionState.COMPLETED.value:
        response_data["outputArguments"] = arguments_to_value_map(invocation.output_arguments)
        response_data["inoutputArguments"] = arguments_to_value_map(invocation.inoutput_arguments)
    elif invocation.execution_state == OperationExecutionState.FAILED.value:
        response_data["message"] = invocation.error_message
        if invocation.error_code:
            response_data["messageType"] = invocation.error_code

    return Response(
        content=canonical_bytes(response_data),
        media_type="application/json",
    )


# ============================================================================
# Template Instantiation Endpoints (SSP-003/004)
# ============================================================================


class InstantiateTemplateRequest(PydanticBaseModel):
    """Request body for instantiating a Submodel from a template.

    Attributes:
        new_id: The identifier for the new instance (required)
        id_short: Optional idShort override for the instance
        value_overrides: Optional dict mapping idShortPath to new values
        copy_semantic_id: Whether to copy semanticId from template (default True)
    """

    new_id: str
    id_short: str | None = None
    value_overrides: dict[str, Any] | None = None
    copy_semantic_id: bool = True


@router.post(
    "/{submodel_identifier}/instantiate",
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CREATE_SUBMODEL))],
)
async def instantiate_template_endpoint(
    submodel_identifier: str,
    request_body: InstantiateTemplateRequest,
    repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Instantiate a new Submodel from a template.

    Creates a new Submodel instance based on the template submodel at the given
    identifier. The template must have kind=Template.

    This endpoint supports the IDTA SSP-003 and SSP-004 template profiles.

    Args:
        submodel_identifier: Base64URL encoded identifier of the template
        request_body: Instantiation parameters including new_id

    Returns:
        The newly created Submodel instance

    Raises:
        400 Bad Request: If the source is not a template or validation fails
        404 Not Found: If the template doesn't exist
        409 Conflict: If a Submodel with new_id already exists
    """
    identifier = decode_identifier(submodel_identifier)

    # Get template submodel
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)

    doc_bytes, _ = result
    template_doc = orjson.loads(doc_bytes)

    # Check if new_id already exists
    if await repo.exists(request_body.new_id):
        raise ConflictError("Submodel", request_body.new_id)

    # Create instantiation request
    inst_request = InstantiationRequest(
        new_id=request_body.new_id,
        id_short=request_body.id_short,
        value_overrides=request_body.value_overrides or {},
        copy_semantic_id=request_body.copy_semantic_id,
    )

    # Instantiate
    inst_result: InstantiationResult = instantiate_template(template_doc, inst_request)

    if not inst_result.success:
        raise BadRequestError(inst_result.error or "Template instantiation failed")

    # Validate and create the new submodel
    try:
        new_submodel = Submodel.model_validate(inst_result.submodel_doc)
    except ValidationError as e:
        raise BadRequestError(f"Invalid instantiated submodel: {e}") from e

    # Persist the new instance
    try:
        new_doc_bytes, new_etag = await repo.create(new_submodel)
    except ValueError as e:
        raise BadRequestError(str(e)) from e

    await session.commit()

    # Cache the new instance
    new_identifier_b64 = encode_id_to_b64url(request_body.new_id)
    await cache.set_submodel(new_identifier_b64, new_doc_bytes, new_etag)

    # Extract semantic_id for event filtering
    semantic_id = None
    if new_submodel.semantic_id and new_submodel.semantic_id.keys:
        semantic_id = new_submodel.semantic_id.keys[0].value

    # Publish creation event
    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.CREATED,
        identifier=request_body.new_id,
        identifier_b64=new_identifier_b64,
        doc_bytes=new_doc_bytes,
        etag=new_etag,
        semantic_id=semantic_id,
    )

    return Response(
        content=new_doc_bytes,
        status_code=201,
        media_type="application/json",
        headers={
            "ETag": f'"{new_etag}"',
            "Location": f"/submodels/{new_identifier_b64}",
            "X-Template-Id": submodel_identifier,
        },
    )
