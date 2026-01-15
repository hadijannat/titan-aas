"""Helpers for File/Blob attachment downloads."""

from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response, StreamingResponse

from titan.api.errors import BadRequestError, NotFoundError
from titan.persistence.tables import BlobAssetTable
from titan.storage.base import BlobMetadata
from titan.storage.factory import get_blob_storage


def _content_disposition(filename: str | None) -> dict[str, str]:
    if not filename:
        return {}
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


async def _stream_blob_by_id(blob_id: str, session: AsyncSession) -> StreamingResponse:
    stmt = select(BlobAssetTable).where(BlobAssetTable.id == blob_id)
    result = await session.execute(stmt)
    asset = result.scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Blob", blob_id)

    storage = get_blob_storage()
    metadata = BlobMetadata(
        id=asset.id,
        submodel_id=asset.submodel_id,
        id_short_path=asset.id_short_path,
        storage_type=asset.storage_type,
        storage_uri=asset.storage_uri,
        content_type=asset.content_type,
        filename=asset.filename,
        size_bytes=asset.size_bytes,
        content_hash=asset.content_hash,
    )

    headers = _content_disposition(asset.filename)
    return StreamingResponse(
        storage.stream(metadata),
        media_type=asset.content_type,
        headers=headers,
    )


def _decode_data_uri(value: str) -> tuple[bytes, str] | None:
    if not value.startswith("data:") or ";base64," not in value:
        return None
    header, b64 = value.split(",", 1)
    content_type = header[5:].split(";", 1)[0] or "application/octet-stream"
    return base64.b64decode(b64, validate=True), content_type


def _bytes_response(content: bytes, content_type: str, filename: str | None) -> Response:
    headers = _content_disposition(filename)
    return Response(content=content, media_type=content_type, headers=headers)


def apply_attachment_payload(
    element: dict[str, object],
    content: bytes,
    content_type: str | None,
) -> None:
    """Update a File/Blob element with attachment content.

    For Blob elements, store raw base64 content in "value".
    For File elements, store a base64 data URI in "value".
    """
    if not content:
        raise BadRequestError("Attachment content is empty")

    model_type = element.get("modelType")
    resolved_type = content_type or element.get("contentType") or "application/octet-stream"

    if model_type == "Blob":
        element["contentType"] = resolved_type
        element["value"] = base64.b64encode(content).decode("ascii")
        return

    if model_type == "File":
        element["contentType"] = resolved_type
        b64 = base64.b64encode(content).decode("ascii")
        element["value"] = f"data:{resolved_type};base64,{b64}"
        return

    raise BadRequestError("Attachment is only supported for File or Blob elements")


def clear_attachment_payload(element: dict[str, object]) -> None:
    """Clear the attachment value for a File/Blob element."""
    model_type = element.get("modelType")
    if model_type not in {"Blob", "File"}:
        raise BadRequestError("Attachment is only supported for File or Blob elements")
    element["value"] = None


async def build_attachment_response(
    value: str,
    content_type: str | None,
    session: AsyncSession,
    filename: str | None = None,
) -> Response:
    """Build response for attachment endpoint from element value."""
    if value.startswith("/blobs/"):
        blob_id = value[len("/blobs/") :]
        return await _stream_blob_by_id(blob_id, session)

    data_uri = _decode_data_uri(value)
    if data_uri is not None:
        content_bytes, inferred_type = data_uri
        return _bytes_response(content_bytes, content_type or inferred_type, filename)

    if value.startswith("http://") or value.startswith("https://"):
        return Response(status_code=302, headers={"Location": value})

    try:
        content_bytes = base64.b64decode(value, validate=True)
        return _bytes_response(
            content_bytes,
            content_type or "application/octet-stream",
            filename,
        )
    except Exception as exc:
        raise BadRequestError("Attachment value is not downloadable") from exc
