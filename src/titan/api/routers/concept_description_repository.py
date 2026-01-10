"""Concept Description Repository API router.

Implements IDTA-01002 Part 2 Concept Description endpoints:
- GET    /concept-descriptions                       - List all ConceptDescriptions
- POST   /concept-descriptions                       - Create ConceptDescription
- GET    /concept-descriptions/{cdIdentifier}        - Get ConceptDescription
- PUT    /concept-descriptions/{cdIdentifier}        - Update ConceptDescription
- DELETE /concept-descriptions/{cdIdentifier}        - Delete ConceptDescription

All identifiers in path segments are Base64URL encoded per IDTA spec.
"""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.errors import (
    ConflictError,
    InvalidBase64UrlError,
    NotFoundError,
    PreconditionFailedError,
)
from titan.api.pagination import DEFAULT_LIMIT, CursorParam, LimitParam
from titan.api.responses import json_bytes_response
from titan.cache import RedisCache, get_redis
from titan.core.canonicalize import canonical_bytes
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url, encode_id_to_b64url
from titan.core.model import ConceptDescription
from titan.events import EventType, get_event_bus, publish_concept_description_event
from titan.persistence.db import get_session
from titan.persistence.repositories import ConceptDescriptionRepository

router = APIRouter(prefix="/concept-descriptions", tags=["Concept Description Repository"])


async def get_concept_description_repo(
    session: AsyncSession = Depends(get_session),
) -> ConceptDescriptionRepository:
    """Get ConceptDescription repository instance."""
    return ConceptDescriptionRepository(session)


async def get_cache() -> RedisCache:
    """Get Redis cache instance."""
    redis = await get_redis()
    return RedisCache(redis)


def _reference_contains_value(refs: list[dict[str, object]] | None, value: str) -> bool:
    """Check if any reference contains a key with a matching value."""
    if not refs:
        return False
    for ref in refs:
        keys = ref.get("keys")
        if not isinstance(keys, list):
            continue
        for key in keys:
            if isinstance(key, dict) and key.get("value") == value:
                return True
    return False


def _data_spec_contains_value(specs: list[dict[str, object]] | None, value: str) -> bool:
    """Check embeddedDataSpecifications for a matching dataSpecification reference."""
    if not specs:
        return False
    for spec in specs:
        ref = spec.get("dataSpecification")
        if isinstance(ref, dict) and _reference_contains_value([ref], value):
            return True
    return False


@router.get("")
async def get_all_concept_descriptions(
    request: Request,
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    id_short: str | None = Query(None, alias="idShort"),
    is_case_of: str | None = Query(None, alias="isCaseOf"),
    data_spec_ref: str | None = Query(None, alias="dataSpecificationRef"),
    repo: ConceptDescriptionRepository = Depends(get_concept_description_repo),
) -> Response:
    """Get all ConceptDescriptions.

    Returns a paginated list of all ConceptDescriptions in the repository.
    Supports cursor-based pagination for consistent results across pages.
    """
    decoded_is_case_of = None
    decoded_data_spec = None

    if is_case_of:
        try:
            decoded_is_case_of = decode_id_from_b64url(is_case_of)
        except InvalidBase64Url:
            raise InvalidBase64UrlError(is_case_of)

    if data_spec_ref:
        try:
            decoded_data_spec = decode_id_from_b64url(data_spec_ref)
        except InvalidBase64Url:
            raise InvalidBase64UrlError(data_spec_ref)

    if not any([id_short, decoded_is_case_of, decoded_data_spec]):
        paged_result = await repo.list_paged_zero_copy(
            limit=limit,
            cursor=cursor,
            is_case_of=decoded_is_case_of,
        )
        return Response(
            content=paged_result.response_bytes,
            media_type="application/json",
        )

    # Slow path: apply filters in Python (no cursor for filtered responses)
    results = await repo.list_all(limit=limit, offset=0)
    items: list[dict[str, object]] = []
    for doc_bytes, _ in results:
        doc = orjson.loads(doc_bytes)
        if id_short and doc.get("idShort") != id_short:
            continue
        if decoded_is_case_of and not _reference_contains_value(
            doc.get("isCaseOf"), decoded_is_case_of
        ):
            continue
        if decoded_data_spec and not _data_spec_contains_value(
            doc.get("embeddedDataSpecifications"), decoded_data_spec
        ):
            continue
        items.append(doc)

    response_data = {
        "result": items,
        "paging_metadata": {"cursor": None},
    }

    return json_bytes_response(canonical_bytes(response_data))


@router.post("", status_code=201)
async def post_concept_description(
    concept_description: ConceptDescription,
    repo: ConceptDescriptionRepository = Depends(get_concept_description_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new ConceptDescription."""
    if await repo.exists(concept_description.id):
        raise ConflictError("ConceptDescription", concept_description.id)

    doc_bytes, etag = await repo.create(concept_description)
    await session.commit()

    identifier_b64 = encode_id_to_b64url(concept_description.id)
    await cache.set_concept_description(identifier_b64, doc_bytes, etag)

    await publish_concept_description_event(
        event_bus=get_event_bus(),
        event_type=EventType.CREATED,
        identifier=concept_description.id,
        identifier_b64=identifier_b64,
        doc_bytes=doc_bytes,
        etag=etag,
    )

    return Response(
        content=doc_bytes,
        status_code=201,
        media_type="application/json",
        headers={
            "ETag": f'"{etag}"',
            "Location": f"/concept-descriptions/{identifier_b64}",
        },
    )


@router.get("/{cd_identifier}")
async def get_concept_description_by_id(
    cd_identifier: str,
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    repo: ConceptDescriptionRepository = Depends(get_concept_description_repo),
    cache: RedisCache = Depends(get_cache),
) -> Response:
    """Get a specific ConceptDescription by identifier."""
    try:
        identifier = decode_id_from_b64url(cd_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(cd_identifier)

    cached = await cache.get_concept_description(cd_identifier)
    if cached:
        doc_bytes, etag = cached
        if if_none_match and if_none_match.strip('"') == etag:
            return Response(status_code=304)
        return Response(
            content=doc_bytes,
            media_type="application/json",
            headers={"ETag": f'"{etag}"'},
        )

    result = await repo.get_bytes_by_id(identifier)
    if result is None:
        raise NotFoundError("ConceptDescription", identifier)

    doc_bytes, etag = result
    await cache.set_concept_description(cd_identifier, doc_bytes, etag)

    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.put("/{cd_identifier}")
async def put_concept_description_by_id(
    cd_identifier: str,
    concept_description: ConceptDescription,
    if_match: str | None = Header(None, alias="If-Match"),
    repo: ConceptDescriptionRepository = Depends(get_concept_description_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Update an existing ConceptDescription."""
    try:
        identifier = decode_id_from_b64url(cd_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(cd_identifier)

    if if_match:
        current = await repo.get_bytes_by_id(identifier)
        if current:
            _, current_etag = current
            if if_match.strip('"') != current_etag:
                raise PreconditionFailedError()

    result = await repo.update(identifier, concept_description)
    if result is None:
        raise NotFoundError("ConceptDescription", identifier)

    doc_bytes, etag = result
    await session.commit()

    await cache.set_concept_description(cd_identifier, doc_bytes, etag)

    await publish_concept_description_event(
        event_bus=get_event_bus(),
        event_type=EventType.UPDATED,
        identifier=identifier,
        identifier_b64=cd_identifier,
        doc_bytes=doc_bytes,
        etag=etag,
    )

    return Response(
        content=doc_bytes,
        media_type="application/json",
        headers={"ETag": f'"{etag}"'},
    )


@router.delete("/{cd_identifier}", status_code=204)
async def delete_concept_description_by_id(
    cd_identifier: str,
    repo: ConceptDescriptionRepository = Depends(get_concept_description_repo),
    cache: RedisCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a ConceptDescription."""
    try:
        identifier = decode_id_from_b64url(cd_identifier)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(cd_identifier)

    deleted = await repo.delete(identifier)
    if not deleted:
        raise NotFoundError("ConceptDescription", identifier)

    await session.commit()
    await cache.delete_concept_description(cd_identifier)

    await publish_concept_description_event(
        event_bus=get_event_bus(),
        event_type=EventType.DELETED,
        identifier=identifier,
        identifier_b64=cd_identifier,
        doc_bytes=None,
        etag=None,
    )

    return Response(status_code=204)
