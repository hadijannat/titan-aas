"""AASX File Server API router.

Implements IDTA-01002 Part 2 AASX File Server endpoints:
- GET    /packages                     - List all AASX packages
- POST   /packages                     - Upload AASX package
- GET    /packages/{packageId}         - Download AASX package
- PUT    /packages/{packageId}         - Update AASX package
- DELETE /packages/{packageId}         - Delete AASX package
- GET    /packages/{packageId}/shells  - List shells in package
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.api.errors import ConflictError, NotFoundError
from titan.api.pagination import CursorParam, LimitParam, DEFAULT_LIMIT
from titan.compat.aasx import AasxImporter, AasxExporter
from titan.persistence.db import get_session
from titan.persistence.tables import AasxPackageTable
from titan.storage.factory import get_blob_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/packages", tags=["AASX File Server"])


async def _store_package(content: bytes, filename: str) -> tuple[str, str, int]:
    """Store package content in blob storage.

    Returns:
        Tuple of (storage_uri, content_hash, size_bytes)
    """
    storage = get_blob_storage()
    content_hash = hashlib.sha256(content).hexdigest()
    package_id = str(uuid4())

    # Store using a dedicated path for AASX packages
    metadata = await storage.store(
        submodel_id="aasx-packages",
        id_short_path=package_id,
        content=content,
        content_type="application/asset-administration-shell-package",
        filename=filename,
    )

    return metadata.storage_uri, content_hash, len(content)


async def _retrieve_package(storage_uri: str) -> bytes:
    """Retrieve package content from blob storage."""
    from titan.storage.base import BlobMetadata

    storage = get_blob_storage()
    metadata = BlobMetadata(storage_uri=storage_uri)
    return await storage.retrieve(metadata)


async def _delete_package_file(storage_uri: str) -> None:
    """Delete package file from blob storage."""
    from titan.storage.base import BlobMetadata

    storage = get_blob_storage()
    metadata = BlobMetadata(storage_uri=storage_uri)
    await storage.delete(metadata)


@router.get("")
async def get_all_packages(
    limit: LimitParam = DEFAULT_LIMIT,
    cursor: CursorParam = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get all AASX packages.

    Returns a paginated list of package metadata.
    """
    stmt = select(AasxPackageTable).order_by(AasxPackageTable.created_at.desc())

    if cursor:
        stmt = stmt.where(AasxPackageTable.created_at < cursor)

    stmt = stmt.limit(limit + 1)  # Fetch one extra to determine if there's a next page

    result = await session.execute(stmt)
    packages = list(result.scalars().all())

    # Determine next cursor
    next_cursor = None
    if len(packages) > limit:
        packages = packages[:limit]
        next_cursor = packages[-1].created_at.isoformat() if packages else None

    items = [
        {
            "packageId": pkg.id,
            "filename": pkg.filename,
            "sizeBytes": pkg.size_bytes,
            "shellCount": pkg.shell_count,
            "submodelCount": pkg.submodel_count,
            "conceptDescriptionCount": pkg.concept_description_count,
            "createdAt": pkg.created_at.isoformat(),
            "updatedAt": pkg.updated_at.isoformat(),
        }
        for pkg in packages
    ]

    return {
        "result": items,
        "paging_metadata": {"cursor": next_cursor},
    }


@router.post("", status_code=201)
async def upload_package(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Upload a new AASX package.

    The package is parsed to extract metadata about contained shells and submodels.
    """
    # Read file content
    content = await file.read()
    filename = file.filename or "package.aasx"

    # Parse package to extract metadata
    importer = AasxImporter()
    try:
        package = await importer.import_from_stream(BytesIO(content))
    except ValueError as e:
        from titan.api.errors import BadRequestError
        raise BadRequestError(str(e))

    # Store package in blob storage
    storage_uri, content_hash, size_bytes = await _store_package(content, filename)

    # Extract shell and submodel IDs for metadata
    shell_ids = [shell.id for shell in package.shells]
    submodel_ids = [sm.id for sm in package.submodels]
    concept_description_ids = [cd.id for cd in package.concept_descriptions]

    # Create database record
    package_record = AasxPackageTable(
        id=str(uuid4()),
        filename=filename,
        storage_uri=storage_uri,
        size_bytes=size_bytes,
        content_hash=content_hash,
        shell_count=len(package.shells),
        submodel_count=len(package.submodels),
        concept_description_count=len(package.concept_descriptions),
        package_info={
            "shellIds": shell_ids,
            "submodelIds": submodel_ids,
            "conceptDescriptionIds": concept_description_ids,
        },
    )

    session.add(package_record)
    await session.commit()
    await session.refresh(package_record)

    logger.info(
        f"Uploaded AASX package {package_record.id}: "
        f"{len(package.shells)} shells, {len(package.submodels)} submodels"
    )

    return {
        "packageId": package_record.id,
        "filename": package_record.filename,
        "sizeBytes": package_record.size_bytes,
        "shellCount": package_record.shell_count,
        "submodelCount": package_record.submodel_count,
        "conceptDescriptionCount": package_record.concept_description_count,
        "createdAt": package_record.created_at.isoformat(),
    }


@router.get("/{package_id}")
async def download_package(
    package_id: str,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Download an AASX package by ID."""
    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    # Retrieve content from blob storage
    content = await _retrieve_package(package.storage_uri)

    return StreamingResponse(
        iter([content]),
        media_type="application/asset-administration-shell-package",
        headers={
            "Content-Disposition": f'attachment; filename="{package.filename}"',
            "Content-Length": str(package.size_bytes),
        },
    )


@router.put("/{package_id}")
async def update_package(
    package_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update an existing AASX package."""
    # Check if package exists
    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    # Read new content
    content = await file.read()
    filename = file.filename or package.filename

    # Parse new package
    importer = AasxImporter()
    try:
        parsed = await importer.import_from_stream(BytesIO(content))
    except ValueError as e:
        from titan.api.errors import BadRequestError
        raise BadRequestError(str(e))

    # Delete old file from storage
    await _delete_package_file(package.storage_uri)

    # Store new package
    storage_uri, content_hash, size_bytes = await _store_package(content, filename)

    # Extract metadata
    shell_ids = [shell.id for shell in parsed.shells]
    submodel_ids = [sm.id for sm in parsed.submodels]
    concept_description_ids = [cd.id for cd in parsed.concept_descriptions]

    # Update record
    package.filename = filename
    package.storage_uri = storage_uri
    package.size_bytes = size_bytes
    package.content_hash = content_hash
    package.shell_count = len(parsed.shells)
    package.submodel_count = len(parsed.submodels)
    package.concept_description_count = len(parsed.concept_descriptions)
    package.metadata = {
        "shellIds": shell_ids,
        "submodelIds": submodel_ids,
        "conceptDescriptionIds": concept_description_ids,
    }

    await session.commit()
    await session.refresh(package)

    logger.info(f"Updated AASX package {package_id}")

    return {
        "packageId": package.id,
        "filename": package.filename,
        "sizeBytes": package.size_bytes,
        "shellCount": package.shell_count,
        "submodelCount": package.submodel_count,
        "conceptDescriptionCount": package.concept_description_count,
        "updatedAt": package.updated_at.isoformat(),
    }


@router.delete("/{package_id}", status_code=204)
async def delete_package(
    package_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an AASX package."""
    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    # Delete from blob storage
    await _delete_package_file(package.storage_uri)

    # Delete from database
    delete_stmt = delete(AasxPackageTable).where(AasxPackageTable.id == package_id)
    await session.execute(delete_stmt)
    await session.commit()

    logger.info(f"Deleted AASX package {package_id}")


@router.get("/{package_id}/shells")
async def get_package_shells(
    package_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all shells contained in an AASX package."""
    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    # Parse package to get shell details
    content = await _retrieve_package(package.storage_uri)
    importer = AasxImporter()
    parsed = await importer.import_from_stream(BytesIO(content))

    shells = [
        {
            "id": shell.id,
            "idShort": shell.id_short,
            "assetKind": shell.asset_information.asset_kind.value if shell.asset_information else None,
            "globalAssetId": shell.asset_information.global_asset_id if shell.asset_information else None,
        }
        for shell in parsed.shells
    ]

    return {"result": shells}


@router.get("/{package_id}/submodels")
async def get_package_submodels(
    package_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all submodels contained in an AASX package."""
    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    # Parse package to get submodel details
    content = await _retrieve_package(package.storage_uri)
    importer = AasxImporter()
    parsed = await importer.import_from_stream(BytesIO(content))

    submodels = [
        {
            "id": sm.id,
            "idShort": sm.id_short,
            "semanticId": _extract_semantic_id(sm),
            "kind": sm.kind.value if sm.kind else None,
        }
        for sm in parsed.submodels
    ]

    return {"result": submodels}


@router.post("/{package_id}/import", status_code=201)
async def import_package_contents(
    package_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Import shells and submodels from package into the repository.

    This creates the actual AAS and Submodel resources from the package.
    """
    from titan.persistence.repositories import AasRepository, SubmodelRepository

    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    # Parse package
    content = await _retrieve_package(package.storage_uri)
    importer = AasxImporter()
    parsed = await importer.import_from_stream(BytesIO(content))

    aas_repo = AasRepository(session)
    submodel_repo = SubmodelRepository(session)

    created_shells = 0
    created_submodels = 0
    skipped_shells = 0
    skipped_submodels = 0

    # Import shells
    for shell in parsed.shells:
        if await aas_repo.exists(shell.id):
            skipped_shells += 1
            continue
        await aas_repo.create(shell)
        created_shells += 1

    # Import submodels
    for submodel in parsed.submodels:
        if await submodel_repo.exists(submodel.id):
            skipped_submodels += 1
            continue
        await submodel_repo.create(submodel)
        created_submodels += 1

    await session.commit()

    logger.info(
        f"Imported from package {package_id}: "
        f"{created_shells} shells, {created_submodels} submodels"
    )

    return {
        "packageId": package_id,
        "shellsCreated": created_shells,
        "shellsSkipped": skipped_shells,
        "submodelsCreated": created_submodels,
        "submodelsSkipped": skipped_submodels,
    }


def _extract_semantic_id(submodel) -> str | None:
    """Extract semantic ID string from submodel."""
    if not submodel.semantic_id:
        return None
    if submodel.semantic_id.keys:
        return submodel.semantic_id.keys[0].value
    return None
