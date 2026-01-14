"""Shared FastAPI dependencies and utilities for Titan-AAS routers.

Provides reusable components to reduce boilerplate across API endpoints:
- Base64URL identifier decoding
- ETag header validation
- Common response builders
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, Path, Response

from titan.api.errors import InvalidBase64UrlError, PreconditionFailedError
from titan.core.ids import InvalidBase64Url, decode_id_from_b64url

# =============================================================================
# Base64URL Identifier Decoding Dependencies
# =============================================================================


def decode_identifier(raw_id: str) -> str:
    """Decode a Base64URL encoded identifier.

    Args:
        raw_id: Base64URL encoded identifier from URL path

    Returns:
        Decoded identifier string

    Raises:
        InvalidBase64UrlError: If the identifier is not valid Base64URL
    """
    try:
        return decode_id_from_b64url(raw_id)
    except InvalidBase64Url:
        raise InvalidBase64UrlError(raw_id)


def decoded_aas_id(
    aas_identifier: Annotated[str, Path(description="Base64URL encoded AAS identifier")],
) -> str:
    """FastAPI dependency to decode AAS identifier from path."""
    return decode_identifier(aas_identifier)


def decoded_submodel_id(
    submodel_identifier: Annotated[str, Path(description="Base64URL encoded Submodel identifier")],
) -> str:
    """FastAPI dependency to decode Submodel identifier from path."""
    return decode_identifier(submodel_identifier)


def decoded_cd_id(
    cd_identifier: Annotated[
        str, Path(description="Base64URL encoded ConceptDescription identifier")
    ],
) -> str:
    """FastAPI dependency to decode ConceptDescription identifier from path."""
    return decode_identifier(cd_identifier)


# =============================================================================
# ETag Header Utilities
# =============================================================================


def check_not_modified(
    if_none_match: str | None,
    etag: str,
) -> Response | None:
    """Check If-None-Match header and return 304 if resource unchanged.

    Args:
        if_none_match: Value of If-None-Match header (may include quotes)
        etag: Current ETag of the resource

    Returns:
        304 Response if ETags match, None otherwise
    """
    if if_none_match and if_none_match.strip('"') == etag:
        return Response(status_code=304)
    return None


def check_precondition(
    if_match: str | None,
    current_etag: str,
) -> None:
    """Check If-Match header and raise 412 if precondition fails.

    Args:
        if_match: Value of If-Match header (may include quotes)
        current_etag: Current ETag of the resource

    Raises:
        PreconditionFailedError: If ETags don't match
    """
    if if_match and if_match.strip('"') != current_etag:
        raise PreconditionFailedError()


# =============================================================================
# Response Builders
# =============================================================================


def json_response_with_etag(
    content: bytes,
    etag: str,
    status_code: int = 200,
    location: str | None = None,
) -> Response:
    """Build a JSON response with ETag header.

    Args:
        content: JSON bytes to return
        etag: ETag value (will be quoted)
        status_code: HTTP status code (default 200)
        location: Optional Location header for 201 responses

    Returns:
        FastAPI Response with proper headers
    """
    headers = {"ETag": f'"{etag}"'}
    if location:
        headers["Location"] = location
    return Response(
        content=content,
        status_code=status_code,
        media_type="application/json",
        headers=headers,
    )


def no_content_response(etag: str) -> Response:
    """Build a 204 No Content response with ETag header.

    Args:
        etag: ETag value (will be quoted)

    Returns:
        FastAPI Response with 204 status and ETag header
    """
    return Response(
        status_code=204,
        headers={"ETag": f'"{etag}"'},
    )


# Type aliases for cleaner router signatures
IfNoneMatchHeader = Annotated[str | None, Header(alias="If-None-Match")]
IfMatchHeader = Annotated[str | None, Header(alias="If-Match")]
