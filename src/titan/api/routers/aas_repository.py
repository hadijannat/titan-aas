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
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.errors import (
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
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url, encode_id_to_b64url
from titan.core.model import AssetAdministrationShell
from titan.core.projection import ProjectionModifiers, apply_projection
from titan.events import EventType, get_event_bus, publish_aas_deleted, publish_aas_event
from titan.persistence.db import get_session
from titan.persistence.repositories import AasRepository

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


@router.get("")
async def get_all_shells(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    level: LevelParam = None,
    extent: ExtentParam = None,
    content: ContentParam = None,
    repo: AasRepository = Depends(get_aas_repo),
) -> Response:
    """Get all Asset Administration Shells.

    Returns a paginated list of all AAS in the repository.
    Supports cursor-based pagination for consistent results across pages.
    """
    if is_fast_path(request):
        # Fast path: Use zero-copy SQL-level pagination
        paged_result = await repo.list_paged_zero_copy(limit=limit, cursor=cursor)
        return Response(
            content=paged_result.response_bytes,
            media_type="application/json",
        )
    else:
        # Slow path: Need to apply projections, so fetch individual items
        results = await repo.list_all(limit=limit, offset=0)

        items = []
        for doc_bytes, etag in results:
            doc = orjson.loads(doc_bytes)
            modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
            items.append(apply_projection(doc, modifiers))

        # Build paginated response (no cursor for slow path with offset)
        response_data = {
            "result": items,
            "paging_metadata": {"cursor": None},
        }

        return json_bytes_response(canonical_bytes(response_data))


@router.post("", status_code=201)
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
    return Response(
        content=doc_bytes,
        status_code=201,
        media_type="application/json",
        headers={"ETag": f'"{etag}"', "Location": f"/shells/{identifier_b64}"},
    )


@router.get("/{aas_identifier}")
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
    # Decode identifier
    try:
        identifier = decode_id_from_b64url(aas_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(aas_identifier)

    # Fast path: try cache first
    if is_fast_path(request):
        cached = await cache.get_aas(aas_identifier)
        if cached:
            doc_bytes, etag = cached

            # Check If-None-Match
            if if_none_match and if_none_match.strip('"') == etag:
                return Response(status_code=304)

            return Response(
                content=doc_bytes,
                media_type="application/json",
                headers={"ETag": f'"{etag}"'},
            )

    # Cache miss or slow path - get from database
    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("AssetAdministrationShell", identifier)

    doc_bytes, etag = result

    # Update cache on miss
    await cache.set_aas(aas_identifier, doc_bytes, etag)

    # Check If-None-Match
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    if is_fast_path(request):
        # Fast path - return bytes directly
        return Response(
            content=doc_bytes,
            media_type="application/json",
            headers={"ETag": f'"{etag}"'},
        )
    else:
        # Slow path - apply projections
        doc = orjson.loads(doc_bytes)
        modifiers = ProjectionModifiers(level=level, extent=extent, content=content)
        projected = apply_projection(doc, modifiers)
        return Response(
            content=canonical_bytes(projected),
            media_type="application/json",
            headers={"ETag": f'"{etag}"'},
        )


@router.put("/{aas_identifier}")
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
    # Decode identifier
    try:
        identifier = decode_id_from_b64url(aas_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(aas_identifier)

    # Check If-Match precondition
    if if_match:
        current = await repo.get_bytes_by_id(identifier)
        if current:
            _, current_etag = current
            if if_match.strip('"') != current_etag:
                raise PreconditionFailedError()

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

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete("/{aas_identifier}", status_code=204)
async def delete_shell_by_id(
    aas_identifier: str,
    repo: AasRepository = Depends(get_aas_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete an Asset Administration Shell.

    The identifier must be Base64URL encoded.
    """
    # Decode identifier
    try:
        identifier = decode_id_from_b64url(aas_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(aas_identifier)

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
