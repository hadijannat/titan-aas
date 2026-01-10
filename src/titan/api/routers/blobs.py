"""Blob storage proxy endpoints for externalized content."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from titan.api.errors import NotFoundError
from titan.persistence.db import get_session
from titan.persistence.tables import BlobAssetTable
from titan.storage.base import BlobMetadata
from titan.storage.factory import get_blob_storage

router = APIRouter(prefix="/blobs", tags=["Blob Storage"])


@router.get("/{blob_id}")
async def get_blob(
    blob_id: str,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream externalized blob content by blob ID."""
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

    headers = {}
    if asset.filename:
        headers["Content-Disposition"] = f'attachment; filename="{asset.filename}"'

    return StreamingResponse(
        storage.stream(metadata),
        media_type=asset.content_type,
        headers=headers,
    )
