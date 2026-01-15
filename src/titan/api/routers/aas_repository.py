"""AAS Repository API router.

Implements IDTA-01002 Part 2 AAS Repository endpoints:
- GET    /shells                     - List all AAS (paginated)
- POST   /shells                     - Create AAS
- GET    /shells/{aasIdentifier}     - Get AAS (fast/slow path)
- PUT    /shells/{aasIdentifier}     - Update AAS
- DELETE /shells/{aasIdentifier}     - Delete AAS

All identifiers in path segments are Base64URL encoded per IDTA spec.
"""

from __future__ import annotations

import base64
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
from titan.core.model import (
    AssetAdministrationShell,
    AssetInformation,
    Operation,
    Reference,
    Resource,
    Submodel,
)
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
    extract_reference_for_aas,
    extract_reference_for_submodel,
    extract_value,
    navigate_id_short_path,
)
from titan.events import (
    EventType,
    get_event_bus,
    publish_aas_deleted,
    publish_aas_event,
    publish_submodel_deleted,
    publish_submodel_event,
)
from titan.events.schemas import OperationExecutionState
from titan.persistence.db import get_session
from titan.persistence.repositories import (
    AasRepository,
    OperationInvocationRepository,
    SubmodelRepository,
)
from titan.security.abac import ResourceType
from titan.security.deps import get_current_user, require_permission
from titan.security.rbac import Permission

router = APIRouter(prefix="/shells", tags=["AAS Repository"])


# Dependency to get repository
async def get_aas_repo(
    session: AsyncSession = Depends(get_session),
) -> AasRepository:
    """Get AAS repository instance."""
    return AasRepository(session)


async def get_submodel_repo(
    session: AsyncSession = Depends(get_session),
) -> SubmodelRepository:
    """Get Submodel repository instance."""
    return SubmodelRepository(session)


async def get_operation_invocation_repo(
    session: AsyncSession = Depends(get_session),
) -> OperationInvocationRepository:
    """Get Operation Invocation repository instance."""
    return OperationInvocationRepository(session)


# Dependency to get cache
async def get_cache() -> RedisCache:
    """Get Redis cache instance."""
    redis = await get_redis()
    return RedisCache(redis)


def _match_asset_ids(doc: dict, asset_ids: list[str]) -> bool:
    """Check if AAS matches any of the given asset IDs.

    Checks both globalAssetId and specificAssetIds.
    """
    asset_info = doc.get("assetInformation", {})

    # Check globalAssetId
    global_asset_id = asset_info.get("globalAssetId")
    if global_asset_id and global_asset_id in asset_ids:
        return True

    # Check specificAssetIds
    specific_ids = asset_info.get("specificAssetIds", [])
    for specific_id in specific_ids:
        if isinstance(specific_id, dict):
            value = specific_id.get("value")
            if value and value in asset_ids:
                return True

    return False


_AAS_METADATA_FIELDS = frozenset(
    {
        "modelType",
        "id",
        "idShort",
        "category",
        "description",
        "displayName",
        "administration",
        "extensions",
        "embeddedDataSpecifications",
        "derivedFrom",
    }
)


def _extract_aas_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    """Extract AAS metadata fields for $metadata endpoints."""
    return {key: value for key, value in doc.items() if key in _AAS_METADATA_FIELDS}


def _extract_submodel_id_from_reference(reference: dict[str, Any]) -> str | None:
    """Extract Submodel identifier from a Reference."""
    keys = reference.get("keys")
    if not isinstance(keys, list):
        return None
    for key in keys:
        if isinstance(key, dict) and key.get("type") == "Submodel":
            value = key.get("value")
            if value:
                return value
    return None


def _extract_submodel_ids(references: list[dict[str, Any]]) -> list[str]:
    """Extract submodel identifiers from a list of references."""
    submodel_ids: list[str] = []
    for ref in references:
        if not isinstance(ref, dict):
            continue
        submodel_id = _extract_submodel_id_from_reference(ref)
        if submodel_id:
            submodel_ids.append(submodel_id)
    return submodel_ids


def _find_submodel_reference(
    references: list[dict[str, Any]],
    submodel_id: str,
) -> tuple[dict[str, Any] | None, int | None]:
    """Find submodel reference and its index by submodel identifier."""
    for index, ref in enumerate(references):
        if not isinstance(ref, dict):
            continue
        if _extract_submodel_id_from_reference(ref) == submodel_id:
            return ref, index
    return None, None


def _ensure_submodel_reference(aas_doc: dict[str, Any], submodel_id: str) -> None:
    """Ensure the AAS references the given submodel."""
    references = aas_doc.get("submodels") or []
    if not isinstance(references, list):
        raise NotFoundError("Submodel", submodel_id)
    submodel_ids = _extract_submodel_ids(references)
    if submodel_id not in submodel_ids:
        raise NotFoundError("Submodel", submodel_id)


async def _load_aas_doc(
    identifier: str,
    identifier_b64: str,
    repo: AasRepository,
    cache: RedisCache,
) -> dict[str, Any]:
    """Load AAS document from cache or repository."""
    cached = await cache.get_aas(identifier_b64)
    if cached:
        doc_bytes, _ = cached
    else:
        result = await repo.get_bytes_by_id(identifier)
        if result is None:
            raise NotFoundError("AssetAdministrationShell", identifier)
        doc_bytes, etag = result
        await cache.set_aas(identifier_b64, doc_bytes, etag)
    return orjson.loads(doc_bytes)


async def _persist_aas_update(
    identifier: str,
    identifier_b64: str,
    updated_doc: dict[str, Any],
    repo: AasRepository,
    cache: RedisCache,
    session: AsyncSession,
) -> tuple[bytes, str, AssetAdministrationShell]:
    """Validate and persist a full AAS update."""
    try:
        aas = AssetAdministrationShell.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e

    update_result = await repo.update(identifier, aas)
    if update_result is None:
        raise NotFoundError("AssetAdministrationShell", identifier)

    doc_bytes, etag = update_result
    await session.commit()

    await cache.set_aas(identifier_b64, doc_bytes, etag)

    await publish_aas_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
    )

    return doc_bytes, etag, aas


async def _load_submodel_bytes(
    identifier: str,
    identifier_b64: str,
    repo: SubmodelRepository,
    cache: RedisCache,
) -> tuple[bytes, str]:
    """Load Submodel bytes and etag from cache or repository."""
    cached = await cache.get_submodel(identifier_b64)
    if cached:
        return cached
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("Submodel", identifier)
    doc_bytes, etag = result
    await cache.set_submodel(identifier_b64, doc_bytes, etag)
    return doc_bytes, etag


async def _load_submodel_for_shell(
    aas_id: str,
    aas_id_b64: str,
    submodel_id: str,
    submodel_id_b64: str,
    aas_repo: AasRepository,
    submodel_repo: SubmodelRepository,
    cache: RedisCache,
) -> tuple[bytes, str]:
    """Ensure shell references submodel and return submodel bytes + etag."""
    aas_doc = await _load_aas_doc(aas_id, aas_id_b64, aas_repo, cache)
    _ensure_submodel_reference(aas_doc, submodel_id)
    return await _load_submodel_bytes(submodel_id, submodel_id_b64, submodel_repo, cache)


async def _persist_submodel_update(
    submodel_id: str,
    submodel_id_b64: str,
    updated_doc: dict[str, Any],
    repo: SubmodelRepository,
    cache: RedisCache,
    session: AsyncSession,
) -> tuple[bytes, str, Submodel]:
    """Validate, persist, and publish a Submodel update."""
    try:
        submodel = Submodel.model_validate(updated_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e

    update_result = await repo.update(submodel_id, submodel)
    if update_result is None:
        raise NotFoundError("Submodel", submodel_id)

    doc_bytes, etag = update_result
    await session.commit()

    await cache.set_submodel(submodel_id_b64, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_id_b64)

    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=submodel_id,
        identifier_b64=submodel_id_b64,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    return doc_bytes, etag, submodel


async def _invoke_operation_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    request_body: InvokeOperationRequest,
    aas_repo: AasRepository,
    submodel_repo: SubmodelRepository,
    invocation_repo: OperationInvocationRepository,
    cache: RedisCache,
    session: AsyncSession,
    user: Any,
) -> InvokeOperationResult:
    """Invoke an Operation scoped to an AAS and persist invocation record."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

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
            submodel_id=submodel_id,
            id_short_path=id_short_path,
            operation=operation,
            request=request_body,
            requested_by=requested_by,
        )
    except OperationValidationError as e:
        raise BadRequestError(e.message)

    await invocation_repo.create(
        invocation_id=invoke_result.invocation_id,
        submodel_id=submodel_id,
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

@router.get(
    "",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_all_shells(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    id_short: str | None = Query(None, alias="idShort"),
    asset_ids: list[str] | None = Query(None, alias="assetIds"),
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    repo: AasRepository = Depends(get_aas_repo),
) -> Response:
    """Get all Asset Administration Shells.

    Returns a paginated list of all AAS in the repository.
    Supports cursor-based pagination for consistent results across pages.
    Optionally filter by idShort or assetIds (globalAssetId or specificAssetIds).
    """
    has_filters = id_short is not None or asset_ids is not None

    if is_fast_path(request) and not has_filters:
        # Fast path: Use zero-copy SQL-level pagination (no filters)
        paged_result = await repo.list_paged_zero_copy(limit=limit, cursor=cursor)
        return Response(
            content=paged_result.response_bytes,
            media_type="application/json",
        )
    else:
        # Slow path: Need to apply projections or filters
        results = await repo.list_all(limit=limit, offset=0)

        items = []
        for doc_bytes, _etag in results:
            doc = orjson.loads(doc_bytes)

            # Apply idShort filter
            if id_short and doc.get("idShort") != id_short:
                continue

            # Apply assetIds filter
            if asset_ids and not _match_asset_ids(doc, asset_ids):
                continue

            # Apply projections if needed
            if not is_fast_path(request):
                modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
                doc = apply_projection(doc, modifiers)

            items.append(doc)

        # Build paginated response (no cursor for slow path with offset)
        response_data = {
            "result": items,
            "paging_metadata": {"cursor": None},
        }

        return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/$metadata",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_all_shells_metadata(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    id_short: str | None = Query(None, alias="idShort"),
    asset_ids: list[str] | None = Query(None, alias="assetIds"),
    repo: AasRepository = Depends(get_aas_repo),
) -> Response:
    """Get metadata for all Asset Administration Shells."""
    has_filters = id_short is not None or asset_ids is not None

    if is_fast_path(request) and not has_filters:
        paged_result = await repo.list_paged_zero_copy(limit=limit, cursor=cursor)
        payload = orjson.loads(paged_result.response_bytes)
        items = payload.get("result", [])
        metadata_items = [_extract_aas_metadata(item) for item in items]
        paging = payload.get("paging_metadata") or {"cursor": None}
    else:
        results = await repo.list_all(limit=limit, offset=0)
        metadata_items = []
        for doc_bytes, _etag in results:
            doc = orjson.loads(doc_bytes)
            if id_short and doc.get("idShort") != id_short:
                continue
            if asset_ids and not _match_asset_ids(doc, asset_ids):
                continue
            metadata_items.append(_extract_aas_metadata(doc))
        paging = {"cursor": None}

    response_data = {"result": metadata_items, "paging_metadata": paging}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/$reference",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def get_all_shell_references(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    id_short: str | None = Query(None, alias="idShort"),
    asset_ids: list[str] | None = Query(None, alias="assetIds"),
    repo: AasRepository = Depends(get_aas_repo),
) -> Response:
    """Get References for all Asset Administration Shells."""
    has_filters = id_short is not None or asset_ids is not None

    if is_fast_path(request) and not has_filters:
        paged_result = await repo.list_paged_zero_copy(limit=limit, cursor=cursor)
        payload = orjson.loads(paged_result.response_bytes)
        items = payload.get("result", [])
        references = [extract_reference_for_aas(item) for item in items]
        paging = payload.get("paging_metadata") or {"cursor": None}
    else:
        results = await repo.list_all(limit=limit, offset=0)
        references = []
        for doc_bytes, _etag in results:
            doc = orjson.loads(doc_bytes)

            if id_short and doc.get("idShort") != id_short:
                continue
            if asset_ids and not _match_asset_ids(doc, asset_ids):
                continue

            references.append(extract_reference_for_aas(doc))

        paging = {"cursor": None}

    response_data = {"result": references, "paging_metadata": paging}
    return json_bytes_response(canonical_bytes(response_data))


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CREATE_AAS))],
)
async def post_shell(
    aas: AssetAdministrationShell,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new Asset Administration Shell.

    The AAS identifier must be unique.
    """
    # Check if already exists
    if await repo.exists(aas.id):
        raise ConflictError("AssetAdministrationShell", aas.id)

    # Create in database
    doc_bytes, etag = await repo.create(aas)
    await session.commit()

    # Update cache
    identifier_b64 = encode_id_to_b64url(aas.id)
    await cache.set_aas(identifier_b64, doc_bytes, etag)

    # Publish event for real-time subscribers
    await publish_aas_event(
        event_bus=get_event_bus(),
        event_type=EventType.CREATED,
        identifier=aas.id,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
    )

    # Return the created AAS
    return json_response_with_etag(
        doc_bytes, etag, status_code=201, location=f"/shells/{identifier_b64}"
    )


@router.get(
    "/{aas_identifier}",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def get_shell_by_id(
    aas_identifier: str,
    request: Request,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get a specific Asset Administration Shell by identifier.

    The identifier must be Base64URL encoded.

    Fast path: No modifiers - stream bytes directly from cache/DB
    Slow path: Modifiers present - hydrate and apply projections
    """
    identifier = decode_identifier(aas_identifier)

    # Fast path: try cache first
    if is_fast_path(request):
        cached = await cache.get_aas(aas_identifier)
        if cached:
            doc_bytes, etag = cached
            not_modified = check_not_modified(if_none_match, etag)
            if not_modified:
                return not_modified
            return json_response_with_etag(doc_bytes, etag)

    # Cache miss or slow path - get from database
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("AssetAdministrationShell", identifier)

    doc_bytes, etag = result

    # Update cache on miss
    await cache.set_aas(aas_identifier, doc_bytes, etag)

    # Check If-None-Match
    not_modified = check_not_modified(if_none_match, etag)
    if not_modified:
        return not_modified

    if is_fast_path(request):
        # Fast path - return bytes directly
        return json_response_with_etag(doc_bytes, etag)
    else:
        # Slow path - apply projections
        doc = orjson.loads(doc_bytes)
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        projected = apply_projection(doc, modifiers)
        return json_response_with_etag(canonical_bytes(projected), etag)


@router.put(
    "/{aas_identifier}",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def put_shell_by_id(
    aas_identifier: str,
    aas: AssetAdministrationShell,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update an existing Asset Administration Shell.

    The identifier must be Base64URL encoded.
    Supports conditional update with If-Match header.
    """
    identifier = decode_identifier(aas_identifier)
    if identifier != aas.id:
        raise BadRequestError("Path identifier does not match AssetAdministrationShell.id")

    current = await repo.get_bytes_by_id(identifier)

    # Check If-Match precondition for updates
    if current and if_match:
        _, current_etag = current
        check_precondition(if_match, current_etag)

    if current is None:
        # Create new AAS on PUT if not exists
        doc_bytes, etag = await repo.create(aas)
        await session.commit()

        await cache.set_aas(aas_identifier, doc_bytes, etag)

        await publish_aas_event(
            event_bus=get_event_bus(),
            event_type=EventType.CREATED,
            identifier=identifier,
            identifier_b64=aas_identifier,
            doc_bytes=doc_bytes,
            etag=etag,
        )

        return json_response_with_etag(
            doc_bytes, etag, status_code=201, location=f"/shells/{aas_identifier}"
        )

    # Update in database
    doc_bytes, etag = await repo.update(identifier, aas)
    await session.commit()

    await cache.set_aas(aas_identifier, doc_bytes, etag)

    await publish_aas_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=aas_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
    )

    return no_content_response(etag)


@router.delete(
    "/{aas_identifier}",
    status_code=204,
    dependencies=[
        Depends(
            require_permission(
                Permission.DELETE_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def delete_shell_by_id(
    aas_identifier: str,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete an Asset Administration Shell.

    The identifier must be Base64URL encoded.
    """
    identifier = decode_identifier(aas_identifier)

    # Delete from database
    deleted = await repo.delete(identifier)
    if not deleted:
        raise NotFoundError("AssetAdministrationShell", identifier)

    await session.commit()

    # Invalidate cache
    await cache.delete_aas(aas_identifier)

    # Publish event for real-time subscribers
    await publish_aas_deleted(
        event_bus=get_event_bus(),
        identifier=identifier,
        identifier_b64=aas_identifier,
    )

    return Response(status_code=204)


@router.get(
    "/{aas_identifier}/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def get_shell_metadata(
    aas_identifier: str,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $metadata representation of an AAS."""
    identifier = decode_identifier(aas_identifier)

    cached = await cache.get_aas(aas_identifier)
    if cached:
        doc_bytes, _ = cached
    else:
        result = await repo.get_bytes_by_id(identifier)
        if result is None:
            raise NotFoundError("AssetAdministrationShell", identifier)
        doc_bytes, etag = result
        await cache.set_aas(aas_identifier, doc_bytes, etag)

    doc = orjson.loads(doc_bytes)
    metadata = _extract_aas_metadata(doc)

    return json_bytes_response(canonical_bytes(metadata))


@router.get(
    "/{aas_identifier}/$reference",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def get_shell_reference(
    aas_identifier: str,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $reference of an AAS.

    Returns a ModelReference pointing to this AAS per IDTA-01002.
    """
    identifier = decode_identifier(aas_identifier)

    cached = await cache.get_aas(aas_identifier)
    if cached:
        doc_bytes, _ = cached
    else:
        result = await repo.get_bytes_by_id(identifier)
        if result is None:
            raise NotFoundError("AssetAdministrationShell", identifier)
        doc_bytes, etag = result
        await cache.set_aas(aas_identifier, doc_bytes, etag)

    doc = orjson.loads(doc_bytes)
    reference = extract_reference_for_aas(doc)

    return Response(
        content=canonical_bytes(reference),
        media_type="application/json",
    )


# ============================================================================
# AssetInformation Endpoints
# ============================================================================


@router.get(
    "/{aas_identifier}/asset-information",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def get_asset_information(
    aas_identifier: str,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get AssetInformation for a specific AAS."""
    identifier = decode_identifier(aas_identifier)
    doc = await _load_aas_doc(identifier, aas_identifier, repo, cache)
    asset_info = doc.get("assetInformation")
    if not asset_info:
        raise NotFoundError("AssetInformation", identifier)
    return json_bytes_response(canonical_bytes(asset_info))


@router.put(
    "/{aas_identifier}/asset-information",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def put_asset_information(
    aas_identifier: str,
    asset_information: AssetInformation,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Replace AssetInformation for a specific AAS."""
    identifier = decode_identifier(aas_identifier)
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("AssetAdministrationShell", identifier)

    doc_bytes, current_etag = result
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    doc["assetInformation"] = asset_information.model_dump(by_alias=True, exclude_none=True)

    _, etag, _ = await _persist_aas_update(
        identifier,
        aas_identifier,
        doc,
        repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.get(
    "/{aas_identifier}/asset-information/thumbnail",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def get_asset_information_thumbnail(
    aas_identifier: str,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Get the asset information thumbnail for an AAS."""
    identifier = decode_identifier(aas_identifier)
    doc = await _load_aas_doc(identifier, aas_identifier, repo, cache)
    asset_info = doc.get("assetInformation") or {}
    thumbnail = asset_info.get("defaultThumbnail") or {}

    path = thumbnail.get("path")
    if not path:
        raise NotFoundError("Thumbnail", identifier)

    content_type = thumbnail.get("contentType") or "application/octet-stream"
    return await build_attachment_response(path, content_type, session)


@router.put(
    "/{aas_identifier}/asset-information/thumbnail",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def put_asset_information_thumbnail(
    aas_identifier: str,
    file: UploadFile = File(...),
    file_name: str | None = Form(None),
    if_match: str | None = Header(None, alias="If-Match"),
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Upload or replace the asset information thumbnail for an AAS."""
    identifier = decode_identifier(aas_identifier)
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("AssetAdministrationShell", identifier)

    doc_bytes, current_etag = result
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    asset_info = doc.get("assetInformation")
    if not asset_info:
        raise NotFoundError("AssetInformation", identifier)

    content = await file.read()
    if not content:
        raise BadRequestError("Thumbnail content is empty")

    content_type = file.content_type or "application/octet-stream"
    b64 = base64.b64encode(content).decode("ascii")
    thumbnail = Resource(path=f"data:{content_type};base64,{b64}", content_type=content_type)
    asset_info["defaultThumbnail"] = thumbnail.model_dump(by_alias=True, exclude_none=True)
    doc["assetInformation"] = asset_info

    _, etag, _ = await _persist_aas_update(
        identifier,
        aas_identifier,
        doc,
        repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.delete(
    "/{aas_identifier}/asset-information/thumbnail",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def delete_asset_information_thumbnail(
    aas_identifier: str,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete the asset information thumbnail for an AAS."""
    identifier = decode_identifier(aas_identifier)
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("AssetAdministrationShell", identifier)

    doc_bytes, current_etag = result
    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    asset_info = doc.get("assetInformation")
    if not asset_info or not asset_info.get("defaultThumbnail"):
        raise NotFoundError("Thumbnail", identifier)

    asset_info.pop("defaultThumbnail", None)
    doc["assetInformation"] = asset_info

    _, etag, _ = await _persist_aas_update(
        identifier,
        aas_identifier,
        doc,
        repo,
        cache,
        session,
    )

    return no_content_response(etag)


# ============================================================================
# Submodel Reference Endpoints (AAS Repository)
# ============================================================================


@router.get(
    "/{aas_identifier}/submodel-refs",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def get_submodel_references(
    aas_identifier: str,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get all submodel references for an AAS."""
    aas_id = decode_identifier(aas_identifier)
    aas_doc = await _load_aas_doc(aas_id, aas_identifier, repo, cache)

    references = aas_doc.get("submodels") or []
    if not isinstance(references, list):
        references = []

    # Best-effort limit support; cursor not supported for embedded lists.
    if limit is not None:
        references = references[:limit]

    response_data = {
        "result": references,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.post(
    "/{aas_identifier}/submodel-refs",
    status_code=201,
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def post_submodel_reference(
    aas_identifier: str,
    reference: Reference,
    repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a submodel reference on an AAS."""
    aas_id = decode_identifier(aas_identifier)
    aas_doc = await _load_aas_doc(aas_id, aas_identifier, repo, cache)

    ref_dict = reference.model_dump(by_alias=True, exclude_none=True)
    submodel_id = _extract_submodel_id_from_reference(ref_dict)
    if not submodel_id:
        raise BadRequestError("Reference must contain a Submodel key")

    if not await submodel_repo.exists(submodel_id):
        raise NotFoundError("Submodel", submodel_id)

    references = aas_doc.get("submodels") or []
    if not isinstance(references, list):
        references = []

    if submodel_id in _extract_submodel_ids(references):
        raise ConflictError("Submodel", submodel_id)

    references.append(ref_dict)
    aas_doc["submodels"] = references

    try:
        aas_model = AssetAdministrationShell.model_validate(aas_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e

    doc_bytes, etag = await repo.update(aas_id, aas_model)
    await session.commit()

    await cache.set_aas(aas_identifier, doc_bytes, etag)

    await publish_aas_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=aas_id,
        identifier_b64=aas_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
    )

    submodel_b64 = encode_id_to_b64url(submodel_id)
    return Response(
        content=canonical_bytes(ref_dict),
        status_code=201,
        media_type="application/json",
        headers={"Location": f"/shells/{aas_identifier}/submodel-refs/{submodel_b64}"},
    )


@router.delete(
    "/{aas_identifier}/submodel-refs/{submodel_identifier}",
    status_code=204,
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_AAS,
                resource_id_params=["aas_identifier"],
            )
        )
    ],
)
async def delete_submodel_reference(
    aas_identifier: str,
    submodel_identifier: str,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a submodel reference from an AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    aas_doc = await _load_aas_doc(aas_id, aas_identifier, repo, cache)
    references = aas_doc.get("submodels") or []
    if not isinstance(references, list):
        references = []

    _, index = _find_submodel_reference(references, submodel_id)
    if index is None:
        raise NotFoundError("Submodel", submodel_id)

    references.pop(index)
    if references:
        aas_doc["submodels"] = references
    else:
        aas_doc["submodels"] = None

    try:
        aas_model = AssetAdministrationShell.model_validate(aas_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e

    doc_bytes, etag = await repo.update(aas_id, aas_model)
    await session.commit()

    await cache.set_aas(aas_identifier, doc_bytes, etag)

    await publish_aas_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=aas_id,
        identifier_b64=aas_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
    )

    return Response(status_code=204)


# ============================================================================
# Submodel Endpoints scoped to AAS (read-only)
# ============================================================================


@router.get(
    "/{aas_identifier}/submodels",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
async def get_submodels_for_shell(
    aas_identifier: str,
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """List Submodels referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    aas_doc = await _load_aas_doc(aas_id, aas_identifier, aas_repo, cache)

    references = aas_doc.get("submodels") or []
    if not isinstance(references, list):
        references = []

    submodel_ids = _extract_submodel_ids(references)
    if limit is not None:
        submodel_ids = submodel_ids[:limit]

    items: list[dict[str, Any]] = []
    for submodel_id in submodel_ids:
        submodel_b64 = encode_id_to_b64url(submodel_id)
        doc_bytes, _ = await _load_submodel_bytes(submodel_id, submodel_b64, submodel_repo, cache)
        doc = orjson.loads(doc_bytes)
        if not is_fast_path(request):
            modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
            doc = apply_projection(doc, modifiers)
        items.append(doc)

    response_data = {
        "result": items,
        "paging_metadata": {"cursor": None},
    }
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_by_id_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    request: Request,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    not_modified = check_not_modified(if_none_match, etag)
    if not_modified:
        return not_modified

    if is_fast_path(request):
        return json_response_with_etag(doc_bytes, etag)

    doc = orjson.loads(doc_bytes)
    modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
    projected = apply_projection(doc, modifiers)
    return json_response_with_etag(canonical_bytes(projected), etag)


@router.put(
    "/{aas_identifier}/submodels/{submodel_identifier}",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def put_submodel_by_id_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    submodel: Submodel,
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create or update a Submodel and ensure it's referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    if submodel_id != submodel.id:
        raise BadRequestError("Path identifier does not match Submodel.id")

    aas_doc = await _load_aas_doc(aas_id, aas_identifier, aas_repo, cache)

    current = await submodel_repo.get_bytes_by_id(submodel_id)
    if current and if_match:
        _, current_etag = current
        check_precondition(if_match, current_etag)

    created = False
    if current is None:
        doc_bytes, etag = await submodel_repo.create(submodel)
        await session.commit()
        created = True
    else:
        doc_bytes, etag = await submodel_repo.update(submodel_id, submodel)
        await session.commit()

    await cache.set_submodel(submodel_identifier, doc_bytes, etag)
    await cache.invalidate_submodel_elements(submodel_identifier)

    semantic_id = None
    if submodel.semantic_id and submodel.semantic_id.keys:
        semantic_id = submodel.semantic_id.keys[0].value

    await publish_submodel_event(
        event_bus=get_event_bus(),
        event_type=EventType.CREATED if created else EventType.UPDATED,
        identifier=submodel_id,
        identifier_b64=submodel_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
        semantic_id=semantic_id,
    )

    references = aas_doc.get("submodels") or []
    if not isinstance(references, list):
        references = []

    if submodel_id not in _extract_submodel_ids(references):
        references.append(
            {
                "type": "ModelReference",
                "keys": [{"type": "Submodel", "value": submodel_id}],
            }
        )
        aas_doc["submodels"] = references

        try:
            aas_model = AssetAdministrationShell.model_validate(aas_doc)
        except ValidationError as e:
            raise BadRequestError(str(e)) from e

        aas_doc_bytes, aas_etag = await aas_repo.update(aas_id, aas_model)
        await session.commit()
        await cache.set_aas(aas_identifier, aas_doc_bytes, aas_etag)

        await publish_aas_event(
            event_bus=get_event_bus(),
            event_type=EventType.UPDATED,
            identifier=aas_id,
            identifier_b64=aas_identifier,
            doc_bytes=aas_doc_bytes,
            etag=aas_etag,
        )

    if created:
        return json_response_with_etag(
            doc_bytes,
            etag,
            status_code=201,
            location=f"/shells/{aas_identifier}/submodels/{submodel_identifier}",
        )
    return no_content_response(etag)


@router.patch(
    "/{aas_identifier}/submodels/{submodel_identifier}",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def patch_submodel_by_id_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    updates: dict,
    level: LevelParam = None,
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Patch core fields of a Submodel referenced by the AAS."""
    if level and level != "core":
        raise BadRequestError("Only level=core is supported for PATCH")

    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)

    if "submodelElements" in updates:
        raise BadRequestError("submodelElements cannot be modified via PATCH")
    if "id" in updates and updates["id"] != submodel_id:
        raise BadRequestError("Path identifier does not match Submodel.id")

    updated_doc = {**doc, **updates}
    if "submodelElements" in doc:
        updated_doc["submodelElements"] = doc.get("submodelElements")

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.delete(
    "/{aas_identifier}/submodels/{submodel_identifier}",
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
async def delete_submodel_by_id_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a Submodel and remove its reference from the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    aas_doc = await _load_aas_doc(aas_id, aas_identifier, aas_repo, cache)
    references = aas_doc.get("submodels") or []
    if not isinstance(references, list):
        references = []

    _, index = _find_submodel_reference(references, submodel_id)
    if index is None:
        raise NotFoundError("Submodel", submodel_id)

    deleted = await submodel_repo.delete(submodel_id)
    if not deleted:
        raise NotFoundError("Submodel", submodel_id)

    references.pop(index)
    if references:
        aas_doc["submodels"] = references
    else:
        aas_doc["submodels"] = None

    try:
        aas_model = AssetAdministrationShell.model_validate(aas_doc)
    except ValidationError as e:
        raise BadRequestError(str(e)) from e

    aas_doc_bytes, aas_etag = await aas_repo.update(aas_id, aas_model)
    await session.commit()

    await cache.delete_submodel(submodel_identifier)
    await cache.invalidate_submodel_elements(submodel_identifier)
    await cache.set_aas(aas_identifier, aas_doc_bytes, aas_etag)

    await publish_submodel_deleted(
        event_bus=get_event_bus(),
        identifier=submodel_id,
        identifier_b64=submodel_identifier,
    )

    await publish_aas_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=aas_id,
        identifier_b64=aas_identifier,
        doc_bytes=aas_doc_bytes,
        etag=aas_etag,
    )

    return Response(status_code=204)


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_metadata_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $metadata of a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    metadata = extract_metadata(doc)
    return json_bytes_response(canonical_bytes(metadata))


@router.patch(
    "/{aas_identifier}/submodels/{submodel_identifier}/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def patch_submodel_metadata_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    updates: dict,
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Patch Submodel metadata for a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    updated_doc = apply_submodel_metadata_patch(doc, updates)

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_value_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $value of a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    elements = doc.get("submodelElements", [])
    values: dict[str, Any] = {}
    for elem in elements:
        id_short = elem.get("idShort")
        if id_short:
            values[id_short] = extract_value(elem)

    return json_bytes_response(canonical_bytes(values))


@router.patch(
    "/{aas_identifier}/submodels/{submodel_identifier}/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.UPDATE_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def patch_submodel_value_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    payload: Any = Body(...),
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Patch Submodel values for a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    values_payload = payload.get("values") if isinstance(payload, dict) else payload
    updated_doc = apply_submodel_value_patch(doc, values_payload)

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/$reference",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_reference_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $reference of a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    reference = extract_reference_for_submodel(doc)
    return json_bytes_response(canonical_bytes(reference))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/$path",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_path_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get the $path representation of a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    paths = collect_id_short_paths(doc)
    return json_bytes_response(canonical_bytes(paths))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_submodel_elements_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    request: Request,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get all SubmodelElements for a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    elements = doc.get("submodelElements", [])

    if content == "reference":
        references = collect_element_references(doc)
        response_data = {"result": references, "paging_metadata": {"cursor": None}}
        return json_bytes_response(canonical_bytes(response_data))

    if content == "path":
        paths = collect_id_short_paths(doc)
        response_data = {"result": paths, "paging_metadata": {"cursor": None}}
        return json_bytes_response(canonical_bytes(response_data))

    if not is_fast_path(request):
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        elements = [apply_projection(elem, modifiers) for elem in elements]

    response_data = {"result": elements, "paging_metadata": {"cursor": None}}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/$metadata",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_metadata_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $metadata for all SubmodelElements referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    elements = doc.get("submodelElements", [])
    metadata = [extract_metadata(elem) for elem in elements]
    response_data = {"result": metadata, "paging_metadata": {"cursor": None}}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/$value",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_value_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $value for all SubmodelElements referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    elements = doc.get("submodelElements", [])
    values: dict[str, Any] = {}
    for elem in elements:
        id_short = elem.get("idShort")
        if id_short:
            values[id_short] = extract_value(elem)

    response_data = {"result": values, "paging_metadata": {"cursor": None}}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/$reference",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_reference_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get References for all SubmodelElements referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    references = collect_element_references(doc)
    response_data = {"result": references, "paging_metadata": {"cursor": None}}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/$path",
    dependencies=[
        Depends(
            require_permission(
                Permission.READ_SUBMODEL,
                resource_id_params=["submodel_identifier"],
            )
        )
    ],
)
async def get_all_submodel_elements_path_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get idShortPaths for all SubmodelElements referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    paths = collect_id_short_paths(doc)
    response_data = {"result": paths, "paging_metadata": {"cursor": None}}
    return json_bytes_response(canonical_bytes(response_data))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}",
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
async def get_submodel_element_by_path_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    request: Request,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get a specific SubmodelElement by idShortPath scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    if content == "reference":
        reference = extract_reference(element, submodel_id, id_short_path)
        return json_bytes_response(canonical_bytes(reference))

    if content == "path":
        return json_bytes_response(canonical_bytes(extract_path(element, id_short_path)))

    if not is_fast_path(request):
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        element = apply_projection(element, modifiers)

    return json_bytes_response(canonical_bytes(element))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/$metadata",
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
async def get_submodel_element_metadata_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $metadata for a SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    metadata = extract_metadata(element)
    return json_bytes_response(canonical_bytes(metadata))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/$value",
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
async def get_submodel_element_value_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $value for a SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    value = extract_value(element)
    return json_bytes_response(canonical_bytes(value))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/$reference",
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
async def get_submodel_element_reference_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $reference for a SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    reference = extract_reference(element, submodel_id, id_short_path)
    return json_bytes_response(canonical_bytes(reference))


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/$path",
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
async def get_submodel_element_path_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get $path for a SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    path_result = extract_path(element, id_short_path)
    return json_bytes_response(canonical_bytes(path_result))


# ============================================================================
# Attachment and Operation Endpoints scoped to AAS
# ============================================================================


@router.get(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/attachment",
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
async def get_element_attachment_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download attachment for a File or Blob SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

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
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/attachment",
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
async def put_element_attachment_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    file: UploadFile = File(...),
    file_name: str | None = Form(None),
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Upload attachment for a File or Blob SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    content = await file.read()
    apply_attachment_payload(element, content, file.content_type)

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        doc,
        submodel_repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.delete(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/attachment",
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
async def delete_element_attachment_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete attachment for a File or Blob SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    element = navigate_id_short_path(doc, id_short_path)
    if element is None:
        raise NotFoundError("SubmodelElement", id_short_path)

    if not element.get("value"):
        raise NotFoundError("Attachment", id_short_path)

    clear_attachment_payload(element)

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        doc,
        submodel_repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.post(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke",
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
async def invoke_operation_sync_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    request_body: InvokeOperationRequest,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
    user: Any = Depends(get_current_user),
) -> Response:
    """Invoke an Operation synchronously scoped to the AAS."""
    invoke_result = await _invoke_operation_for_shell(
        aas_identifier=aas_identifier,
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        aas_repo=aas_repo,
        submodel_repo=submodel_repo,
        invocation_repo=invocation_repo,
        cache=cache,
        session=session,
        user=user,
    )

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
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke/$value",
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
async def invoke_operation_sync_value_only_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    payload: dict,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
    user: Any = Depends(get_current_user),
) -> Response:
    """Invoke an Operation synchronously with value-only payload scoped to the AAS."""
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

    invoke_result = await _invoke_operation_for_shell(
        aas_identifier=aas_identifier,
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        aas_repo=aas_repo,
        submodel_repo=submodel_repo,
        invocation_repo=invocation_repo,
        cache=cache,
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
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke-async",
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
async def invoke_operation_async_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    request_body: InvokeOperationRequest,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
    user: Any = Depends(get_current_user),
) -> Response:
    """Invoke an Operation asynchronously scoped to the AAS."""
    invoke_result = await _invoke_operation_for_shell(
        aas_identifier=aas_identifier,
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        aas_repo=aas_repo,
        submodel_repo=submodel_repo,
        invocation_repo=invocation_repo,
        cache=cache,
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


@router.post(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/invoke-async/$value",
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
async def invoke_operation_async_value_only_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    payload: dict,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
    user: Any = Depends(get_current_user),
) -> Response:
    """Invoke an Operation asynchronously with value-only payload scoped to the AAS."""
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

    invoke_result = await _invoke_operation_for_shell(
        aas_identifier=aas_identifier,
        submodel_identifier=submodel_identifier,
        id_short_path=id_short_path,
        request_body=request_body,
        aas_repo=aas_repo,
        submodel_repo=submodel_repo,
        invocation_repo=invocation_repo,
        cache=cache,
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
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/operation-status/{handle_id}",
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
async def get_operation_status_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    handle_id: str,
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    aas_repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get status of an async operation invocation scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    aas_doc = await _load_aas_doc(aas_id, aas_identifier, aas_repo, cache)
    _ensure_submodel_reference(aas_doc, submodel_id)

    invocation = await invocation_repo.get_by_id(handle_id)
    if invocation is None:
        raise NotFoundError("OperationResult", handle_id)
    if invocation.id_short_path != id_short_path or invocation.submodel_id != submodel_id:
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
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/operation-results/{handle_id}",
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
async def get_operation_result_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    handle_id: str,
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    aas_repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get operation result scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    aas_doc = await _load_aas_doc(aas_id, aas_identifier, aas_repo, cache)
    _ensure_submodel_reference(aas_doc, submodel_id)

    invocation = await invocation_repo.get_by_id(handle_id)
    if invocation is None:
        raise NotFoundError("OperationResult", handle_id)
    if invocation.id_short_path != id_short_path or invocation.submodel_id != submodel_id:
        raise NotFoundError("OperationResult", handle_id)

    response_data: dict[str, Any] = {
        "executionState": invocation.execution_state,
    }

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
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/operation-results/{handle_id}/$value",
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
async def get_operation_result_value_only_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    handle_id: str,
    invocation_repo: OperationInvocationRepository = Depends(get_operation_invocation_repo),
    aas_repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get value-only operation result scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    aas_doc = await _load_aas_doc(aas_id, aas_identifier, aas_repo, cache)
    _ensure_submodel_reference(aas_doc, submodel_id)

    invocation = await invocation_repo.get_by_id(handle_id)
    if invocation is None:
        raise NotFoundError("OperationResult", handle_id)
    if invocation.id_short_path != id_short_path or invocation.submodel_id != submodel_id:
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
# SubmodelElement CRUD Endpoints scoped to AAS
# ============================================================================


@router.post(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements",
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
async def post_submodel_element_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    element: dict,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a root-level SubmodelElement within a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    try:
        updated_doc = insert_element(doc, None, element)
    except ElementExistsError as e:
        raise ConflictError("SubmodelElement", e.path)
    except (InvalidPathError, ValueError) as e:
        raise BadRequestError(str(e)) from e

    await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    id_short = element.get("idShort", "")
    return Response(
        content=canonical_bytes(element),
        status_code=201,
        media_type="application/json",
        headers={
            "Location": (
                f"/shells/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short}"
            )
        },
    )


@router.post(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}",
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
async def post_nested_submodel_element_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    element: dict,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a nested SubmodelElement within a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    try:
        updated_doc = insert_element(doc, id_short_path, element)
    except ElementExistsError as e:
        raise ConflictError("SubmodelElement", e.path)
    except InvalidPathError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except ValueError as e:
        raise BadRequestError(str(e)) from e

    await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
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
        headers={
            "Location": (
                f"/shells/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{new_path}"
            )
        },
    )


@router.put(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}",
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
async def put_submodel_element_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    element: dict,
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Replace a SubmodelElement within a Submodel referenced by the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    try:
        updated_doc = replace_element(doc, id_short_path, element)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e)) from e

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    return no_content_response(etag)


@router.patch(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}/$value",
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
async def patch_submodel_element_value_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    payload: Any,
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update only the value of a SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)

    value = payload
    if isinstance(payload, dict) and "value" in payload:
        value = payload["value"]

    try:
        updated_doc = update_element_value(doc, id_short_path, value)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e)) from e

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    return Response(
        content=canonical_bytes(value),
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.patch(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}",
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
async def patch_submodel_element_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    updates: dict,
    if_match: str | None = Header(None, alias="If-Match"),
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Partially update a SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, current_etag = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    check_precondition(if_match, current_etag)

    doc = orjson.loads(doc_bytes)
    try:
        updated_doc = patch_element(doc, id_short_path, updates)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e)) from e

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    updated_element = navigate_id_short_path(updated_doc, id_short_path)
    return Response(
        content=canonical_bytes(updated_element),
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete(
    "/{aas_identifier}/submodels/{submodel_identifier}/submodel-elements/{id_short_path:path}",
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
async def delete_submodel_element_for_shell(
    aas_identifier: str,
    submodel_identifier: str,
    id_short_path: str,
    aas_repo: AasRepository = Depends(get_aas_repo),
    submodel_repo: SubmodelRepository = Depends(get_submodel_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a SubmodelElement scoped to the AAS."""
    aas_id = decode_identifier(aas_identifier)
    submodel_id = decode_identifier(submodel_identifier)

    doc_bytes, _ = await _load_submodel_for_shell(
        aas_id,
        aas_identifier,
        submodel_id,
        submodel_identifier,
        aas_repo,
        submodel_repo,
        cache,
    )

    doc = orjson.loads(doc_bytes)
    try:
        updated_doc = delete_element(doc, id_short_path)
    except ElementNotFoundError:
        raise NotFoundError("SubmodelElement", id_short_path)
    except InvalidPathError as e:
        raise BadRequestError(str(e)) from e

    _, etag, _ = await _persist_submodel_update(
        submodel_id,
        submodel_identifier,
        updated_doc,
        submodel_repo,
        cache,
        session,
    )

    return no_content_response(etag)
