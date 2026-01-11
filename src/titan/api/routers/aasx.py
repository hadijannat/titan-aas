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

from titan.api.errors import NotFoundError
from titan.api.pagination import DEFAULT_LIMIT, CursorParam, LimitParam
from titan.compat.aasx import AasxImporter
from titan.persistence.db import get_session
from titan.persistence.tables import AasxPackageTable
from titan.security.deps import require_permission
from titan.security.rbac import Permission
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


@router.get(
    "",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
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


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(require_permission(Permission.CREATE_AAS))],
)
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


@router.get(
    "/{package_id}",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
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


@router.put(
    "/{package_id}",
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
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
    package.package_info = {
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


@router.delete(
    "/{package_id}",
    status_code=204,
    dependencies=[Depends(require_permission(Permission.DELETE_AAS))],
)
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


@router.get(
    "/{package_id}/shells",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
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

    shells = []
    for shell in parsed.shells:
        asset_info = shell.asset_information
        shells.append(
            {
                "id": shell.id,
                "idShort": shell.id_short,
                "assetKind": asset_info.asset_kind.value if asset_info else None,
                "globalAssetId": asset_info.global_asset_id if asset_info else None,
            }
        )

    return {"result": shells}


@router.get(
    "/{package_id}/submodels",
    dependencies=[Depends(require_permission(Permission.READ_SUBMODEL))],
)
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


@router.post(
    "/{package_id}/validate",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def validate_package(
    package_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Validate an AASX package for OPC compliance.

    Returns validation results including errors and warnings.
    """
    from titan.packages.validator import OpcValidator

    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    content = await _retrieve_package(package.storage_uri)
    validator = OpcValidator()
    validation = await validator.validate(BytesIO(content))

    return {
        "packageId": package_id,
        "valid": validation.valid,
        "fileCount": validation.file_count,
        "totalSize": validation.total_size,
        "contentHash": validation.content_hash,
        "errors": [
            {"code": i.code, "message": i.message, "location": i.location}
            for i in validation.errors
        ],
        "warnings": [
            {"code": i.code, "message": i.message, "location": i.location}
            for i in validation.warnings
        ],
    }


@router.post(
    "/{package_id}/preview",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def preview_package_import(
    package_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Preview what would happen if package contents are imported.

    Shows which shells/submodels would be created vs skipped due to conflicts.
    """
    from titan.packages.manager import PackageManager
    from titan.persistence.repositories import AasRepository, SubmodelRepository

    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    content = await _retrieve_package(package.storage_uri)
    manager = PackageManager()

    aas_repo = AasRepository(session)
    submodel_repo = SubmodelRepository(session)

    preview = await manager.preview_import(
        BytesIO(content),
        aas_repo=aas_repo,
        submodel_repo=submodel_repo,
    )

    return {
        "packageId": package_id,
        **preview,
    }


@router.post(
    "/{package_id}/import",
    status_code=201,
    dependencies=[Depends(require_permission(Permission.UPDATE_AAS))],
)
async def import_package_contents(
    package_id: str,
    conflict_resolution: str = "skip",
    shell_ids: list[str] | None = None,
    submodel_ids: list[str] | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Import shells and submodels from package into the repository.

    Supports:
    - conflict_resolution: "skip" (default), "overwrite", "error", or "rename"
    - shell_ids: Optional list of specific shell IDs to import
    - submodel_ids: Optional list of specific submodel IDs to import
    """
    from titan.packages.manager import ConflictResolution, PackageManager
    from titan.persistence.repositories import AasRepository, SubmodelRepository

    stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
    result = await session.execute(stmt)
    package = result.scalar_one_or_none()

    if package is None:
        raise NotFoundError("AasxPackage", package_id)

    # Map conflict resolution string to enum
    try:
        resolution = ConflictResolution(conflict_resolution.lower())
    except ValueError:
        from titan.api.errors import BadRequestError

        raise BadRequestError(
            f"Invalid conflict_resolution: {conflict_resolution}. "
            "Use 'skip', 'overwrite', 'error', or 'rename'."
        )

    content = await _retrieve_package(package.storage_uri)
    manager = PackageManager()

    aas_repo = AasRepository(session)
    submodel_repo = SubmodelRepository(session)

    import_result = await manager.import_package(
        stream=BytesIO(content),
        aas_repo=aas_repo,
        submodel_repo=submodel_repo,
        conflict_resolution=resolution,
        shell_ids=shell_ids,
        submodel_ids=submodel_ids,
    )

    await session.commit()

    logger.info(
        f"Imported from package {package_id}: "
        f"{import_result.shells_created} shells created, "
        f"{import_result.submodels_created} submodels created"
    )

    return {
        "packageId": package_id,
        **import_result.to_dict(),
    }


def _extract_semantic_id(submodel) -> str | None:
    """Extract semantic ID string from submodel."""
    if not submodel.semantic_id:
        return None
    if submodel.semantic_id.keys:
        return submodel.semantic_id.keys[0].value
    return None


@router.post(
    "/export-xml",
    dependencies=[Depends(require_permission(Permission.READ_AAS))],
)
async def export_xml(
    shell_ids: list[str] | None = None,
    submodel_ids: list[str] | None = None,
    include_concept_descriptions: bool = True,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Export AAS content to AASX package with XML serialization.

    Creates an AASX package containing the specified shells and submodels,
    serialized as XML (IDTA-01001 Part 1) instead of JSON.

    Args:
        shell_ids: Optional list of shell IDs to export (None = all)
        submodel_ids: Optional list of submodel IDs to export (None = all)
        include_concept_descriptions: Include concept descriptions (default: True)
        session: Database session

    Returns:
        AASX package as application/octet-stream

    Raises:
        NotFoundError: If no entities found to export
    """
    from titan.compat.aasx import AasxExporter
    from titan.persistence.repositories import (
        AasRepository,
        ConceptDescriptionRepository,
        SubmodelRepository,
    )

    aas_repo = AasRepository(session)
    submodel_repo = SubmodelRepository(session)
    cd_repo = ConceptDescriptionRepository(session)

    # Fetch shells
    shells = []
    if shell_ids:
        for shell_id in shell_ids:
            shell = await aas_repo.get(shell_id)
            if shell:
                shells.append(shell)
    else:
        # Get all shells if no IDs specified
        all_shells = await aas_repo.get_all(limit=1000)  # Reasonable limit
        shells = all_shells

    # Fetch submodels
    submodels = []
    if submodel_ids:
        for sm_id in submodel_ids:
            sm = await submodel_repo.get(sm_id)
            if sm:
                submodels.append(sm)
    else:
        # Get all submodels if no IDs specified
        all_submodels = await submodel_repo.get_all(limit=1000)
        submodels = all_submodels

    # Fetch concept descriptions if requested
    concept_descriptions = []
    if include_concept_descriptions:
        all_cds = await cd_repo.get_all(limit=1000)
        concept_descriptions = all_cds

    # Check if we have anything to export
    if not shells and not submodels:
        raise NotFoundError("No entities found to export")

    # Export to AASX with XML serialization
    exporter = AasxExporter()
    stream = await exporter.export_to_stream(
        shells=shells,
        submodels=submodels,
        output_stream=BytesIO(),
        concept_descriptions=concept_descriptions if concept_descriptions else None,
        use_json=False,  # Use XML serialization
    )

    stream.seek(0)

    # Generate filename
    filename = "export.aasx"
    if shell_ids and len(shell_ids) == 1:
        # Use shell idShort if exporting single shell
        shell = shells[0] if shells else None
        if shell and shell.id_short:
            filename = f"{shell.id_short}.aasx"
    elif submodel_ids and len(submodel_ids) == 1:
        # Use submodel idShort if exporting single submodel
        sm = submodels[0] if submodels else None
        if sm and sm.id_short:
            filename = f"{sm.id_short}.aasx"

    return StreamingResponse(
        stream,
        media_type="application/asset-administration-shell-package",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
