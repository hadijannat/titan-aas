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

import orjson
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.deps import (
    check_not_modified,
    check_precondition,
    decode_identifier,
    json_response_with_etag,
    no_content_response,
)
from titan.api.errors import (
    ConflictError,
    NotFoundError,
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
from titan.core.ids import encode_id_to_b64url
from titan.core.model import AssetAdministrationShell
from titan.core.projection import ProjectionModifiers, apply_projection, extract_reference_for_aas
from titan.events import EventType, get_event_bus, publish_aas_deleted, publish_aas_event
from titan.persistence.db import get_session
from titan.persistence.repositories import AasRepository
from titan.security.deps import require_permission
from titan.security.rbac import Permission

router = APIRouter(prefix="/shells", tags=["AAS Repository"])


# Dependency to get repository
async def get_aas_repo(
    session: AsyncSession = Depends(get_session),
) -> AasRepository:
    """Get AAS repository instance."""
    return AasRepository(session)


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

    # Check If-Match precondition
    if if_match:
        current = await repo.get_bytes_by_id(identifier)
        if current:
            _, current_etag = current
            check_precondition(if_match, current_etag)

    # Update in database
    result = await repo.update(identifier, aas)
    if result is None:
        raise NotFoundError("AssetAdministrationShell", identifier)

    doc_bytes, etag = result
    await session.commit()

    # Update cache
    await cache.set_aas(aas_identifier, doc_bytes, etag)

    # Publish event for real-time subscribers
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
