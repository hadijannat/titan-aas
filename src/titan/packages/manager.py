"""AASX Package Manager.

Handles package lifecycle including:
- Version tracking
- Import with conflict resolution
- Export with selective content
- Package metadata
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import Any, BinaryIO
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.compat.aasx import AasxExporter, AasxImporter, AasxPackage
from titan.core.model import AssetAdministrationShell, ConceptDescription, Submodel
from titan.packages.validator import OpcValidator, ValidationLevel, ValidationResult
from titan.persistence.tables import AasxPackageTable

logger = logging.getLogger(__name__)


class ConflictResolution(Enum):
    """How to handle conflicts during import."""

    SKIP = "skip"  # Skip existing items
    OVERWRITE = "overwrite"  # Replace existing items
    ERROR = "error"  # Raise error on conflict
    RENAME = "rename"  # Import with modified ID


@dataclass
class PackageVersion:
    """Version metadata for a package."""

    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    created_by: str | None = None
    comment: str | None = None
    content_hash: str | None = None
    parent_version: int | None = None


@dataclass
class ImportResult:
    """Result of a package import operation."""

    success: bool
    shells_created: int = 0
    shells_updated: int = 0
    shells_skipped: int = 0
    shells_failed: int = 0
    submodels_created: int = 0
    submodels_updated: int = 0
    submodels_skipped: int = 0
    submodels_failed: int = 0
    concept_descriptions_created: int = 0
    concept_descriptions_updated: int = 0
    concept_descriptions_skipped: int = 0
    concept_descriptions_failed: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_created(self) -> int:
        """Total items created."""
        return self.shells_created + self.submodels_created + self.concept_descriptions_created

    @property
    def total_skipped(self) -> int:
        """Total items skipped."""
        return self.shells_skipped + self.submodels_skipped + self.concept_descriptions_skipped

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "success": self.success,
            "shells": {
                "created": self.shells_created,
                "updated": self.shells_updated,
                "skipped": self.shells_skipped,
                "failed": self.shells_failed,
            },
            "submodels": {
                "created": self.submodels_created,
                "updated": self.submodels_updated,
                "skipped": self.submodels_skipped,
                "failed": self.submodels_failed,
            },
            "conceptDescriptions": {
                "created": self.concept_descriptions_created,
                "updated": self.concept_descriptions_updated,
                "skipped": self.concept_descriptions_skipped,
                "failed": self.concept_descriptions_failed,
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class ExportOptions:
    """Options for exporting packages."""

    include_shells: bool = True
    include_submodels: bool = True
    include_concept_descriptions: bool = True
    shell_ids: list[str] | None = None  # None = all
    submodel_ids: list[str] | None = None  # None = all
    use_json: bool = True
    validate_output: bool = True


class PackageManager:
    """Manages AASX package lifecycle."""

    def __init__(
        self,
        validation_level: ValidationLevel = ValidationLevel.STANDARD,
    ) -> None:
        """Initialize package manager.

        Args:
            validation_level: How strictly to validate packages
        """
        self.validation_level = validation_level
        self._importer = AasxImporter()
        self._exporter = AasxExporter()
        self._validator = OpcValidator(level=validation_level)

    async def validate(self, stream: BinaryIO) -> ValidationResult:
        """Validate a package without importing.

        Args:
            stream: Binary stream containing AASX data

        Returns:
            ValidationResult with issues and metadata
        """
        return await self._validator.validate(stream)

    async def parse(self, stream: BinaryIO) -> AasxPackage:
        """Parse a package without persisting.

        Args:
            stream: Binary stream containing AASX data

        Returns:
            Parsed AasxPackage
        """
        return await self._importer.import_from_stream(stream)

    async def preview_import(
        self,
        stream: BinaryIO,
        aas_repo: Any | None = None,
        submodel_repo: Any | None = None,
    ) -> dict[str, Any]:
        """Preview what would happen if package is imported.

        Args:
            stream: Binary stream containing AASX data
            aas_repo: Optional AAS repository for conflict detection
            submodel_repo: Optional Submodel repository for conflict detection

        Returns:
            Preview information including conflicts
        """
        package = await self._importer.import_from_stream(stream)

        shell_info = []
        for shell in package.shells:
            info = {
                "id": shell.id,
                "idShort": shell.id_short,
                "exists": False,
            }
            if aas_repo:
                info["exists"] = await aas_repo.exists(shell.id)
            shell_info.append(info)

        submodel_info = []
        for sm in package.submodels:
            info = {
                "id": sm.id,
                "idShort": sm.id_short,
                "exists": False,
            }
            if submodel_repo:
                info["exists"] = await submodel_repo.exists(sm.id)
            submodel_info.append(info)

        cd_info = []
        for cd in package.concept_descriptions:
            cd_info.append(
                {
                    "id": cd.id,
                    "idShort": cd.id_short,
                }
            )

        return {
            "shells": shell_info,
            "submodels": submodel_info,
            "conceptDescriptions": cd_info,
            "supplementaryFiles": list(package.supplementary_files.keys()),
            "conflicts": {
                "shells": sum(1 for s in shell_info if s.get("exists")),
                "submodels": sum(1 for s in submodel_info if s.get("exists")),
            },
        }

    async def import_package(
        self,
        stream: BinaryIO,
        aas_repo: Any,
        submodel_repo: Any,
        conflict_resolution: ConflictResolution = ConflictResolution.SKIP,
        shell_ids: list[str] | None = None,
        submodel_ids: list[str] | None = None,
    ) -> ImportResult:
        """Import package contents with conflict handling.

        Args:
            stream: Binary stream containing AASX data
            aas_repo: AAS repository for persistence
            submodel_repo: Submodel repository for persistence
            conflict_resolution: How to handle existing items
            shell_ids: Optional list of shell IDs to import (None = all)
            submodel_ids: Optional list of submodel IDs to import (None = all)

        Returns:
            ImportResult with counts and errors
        """
        result = ImportResult(success=True)

        try:
            package = await self._importer.import_from_stream(stream)
        except Exception as e:
            result.success = False
            result.errors.append(f"Failed to parse package: {e}")
            return result

        # Import shells
        for shell in package.shells:
            # Filter if specific IDs requested
            if shell_ids is not None and shell.id not in shell_ids:
                continue

            try:
                exists = await aas_repo.exists(shell.id)

                if exists:
                    if conflict_resolution == ConflictResolution.SKIP:
                        result.shells_skipped += 1
                        continue
                    elif conflict_resolution == ConflictResolution.ERROR:
                        result.shells_failed += 1
                        result.errors.append(f"Shell already exists: {shell.id}")
                        continue
                    elif conflict_resolution == ConflictResolution.OVERWRITE:
                        await aas_repo.update(shell.id, shell)
                        result.shells_updated += 1
                    elif conflict_resolution == ConflictResolution.RENAME:
                        # Generate new ID
                        shell.id = f"{shell.id}_imported_{datetime.now().timestamp():.0f}"
                        await aas_repo.create(shell)
                        result.shells_created += 1
                else:
                    await aas_repo.create(shell)
                    result.shells_created += 1

            except Exception as e:
                result.shells_failed += 1
                result.errors.append(f"Failed to import shell {shell.id}: {e}")

        # Import submodels
        for submodel in package.submodels:
            # Filter if specific IDs requested
            if submodel_ids is not None and submodel.id not in submodel_ids:
                continue

            try:
                exists = await submodel_repo.exists(submodel.id)

                if exists:
                    if conflict_resolution == ConflictResolution.SKIP:
                        result.submodels_skipped += 1
                        continue
                    elif conflict_resolution == ConflictResolution.ERROR:
                        result.submodels_failed += 1
                        result.errors.append(f"Submodel already exists: {submodel.id}")
                        continue
                    elif conflict_resolution == ConflictResolution.OVERWRITE:
                        await submodel_repo.update(submodel.id, submodel)
                        result.submodels_updated += 1
                    elif conflict_resolution == ConflictResolution.RENAME:
                        submodel.id = f"{submodel.id}_imported_{datetime.now().timestamp():.0f}"
                        await submodel_repo.create(submodel)
                        result.submodels_created += 1
                else:
                    await submodel_repo.create(submodel)
                    result.submodels_created += 1

            except Exception as e:
                result.submodels_failed += 1
                result.errors.append(f"Failed to import submodel {submodel.id}: {e}")

        if result.errors:
            result.success = False

        logger.info(
            f"Import complete: {result.shells_created} shells, "
            f"{result.submodels_created} submodels created; "
            f"{result.shells_skipped} shells, {result.submodels_skipped} submodels skipped"
        )

        return result

    async def export_to_stream(
        self,
        shells: list[AssetAdministrationShell],
        submodels: list[Submodel],
        concept_descriptions: list[ConceptDescription] | None = None,
        supplementary_files: dict[str, bytes] | None = None,
        options: ExportOptions | None = None,
    ) -> BytesIO:
        """Export AAS content to an AASX package in memory.

        Args:
            shells: AAS shells to include
            submodels: Submodels to include
            concept_descriptions: Concept descriptions to include
            supplementary_files: Additional files to include
            options: Export options

        Returns:
            BytesIO containing the AASX package
        """
        options = options or ExportOptions()

        # Filter content based on options
        if options.shell_ids:
            shells = [s for s in shells if s.id in options.shell_ids]
        if options.submodel_ids:
            submodels = [s for s in submodels if s.id in options.submodel_ids]

        output = BytesIO()
        await self._exporter.export_to_stream(
            shells=shells if options.include_shells else [],
            submodels=submodels if options.include_submodels else [],
            output_stream=output,
            concept_descriptions=concept_descriptions
            if options.include_concept_descriptions
            else None,
            supplementary_files=supplementary_files,
            use_json=options.use_json,
        )

        if options.validate_output:
            output.seek(0)
            validation = await self._validator.validate(output)
            if not validation.valid:
                logger.warning(f"Exported package has validation issues: {validation.errors}")
            output.seek(0)

        return output

    async def create_version(
        self,
        session: AsyncSession,
        package_id: str,
        new_content: bytes,
        filename: str,
        storage_uri: str,
        created_by: str | None = None,
        comment: str | None = None,
    ) -> str:
        """Create a new version of an existing package.

        This snapshots the current package state and creates a new version
        with updated content. The new version links back to the previous version.

        Args:
            session: Database session
            package_id: ID of the package to version
            new_content: New package content bytes
            filename: Filename for the new version
            storage_uri: Storage URI for the new content
            created_by: User creating this version
            comment: Description of changes in this version

        Returns:
            ID of the new version package

        Raises:
            ValueError: If package not found
        """
        # Get current package
        stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
        result = await session.execute(stmt)
        current = result.scalar_one_or_none()

        if not current:
            raise ValueError(f"Package not found: {package_id}")

        # Calculate content hash
        content_hash = hashlib.sha256(new_content).hexdigest()

        # Create new version
        new_id = str(uuid4())
        new_package = AasxPackageTable(
            id=new_id,
            filename=filename,
            storage_uri=storage_uri,
            size_bytes=len(new_content),
            content_hash=content_hash,
            version=current.version + 1,
            version_comment=comment,
            created_by=created_by,
            previous_version_id=package_id,
            # Copy counts from current (will be updated during import if needed)
            shell_count=current.shell_count,
            submodel_count=current.submodel_count,
            concept_description_count=current.concept_description_count,
            package_info=current.package_info,
        )

        session.add(new_package)
        await session.commit()

        logger.info(
            f"Created version {new_package.version} of package {package_id} "
            f"(new ID: {new_id}, comment: {comment})"
        )

        return new_id

    async def list_versions(
        self,
        session: AsyncSession,
        package_id: str,
    ) -> list[PackageVersion]:
        """Get version history for a package.

        Returns all versions in the version chain, from oldest to newest.

        Args:
            session: Database session
            package_id: ID of any package in the version chain

        Returns:
            List of PackageVersion objects, oldest first
        """
        # Find the root of the version chain (package with no previous_version_id)
        current_id = package_id
        root_id = package_id

        while True:
            stmt = select(AasxPackageTable).where(AasxPackageTable.id == current_id)
            result = await session.execute(stmt)
            package = result.scalar_one_or_none()

            if not package:
                break

            if package.previous_version_id:
                current_id = package.previous_version_id
                root_id = current_id
            else:
                break

        # Now traverse forward from root to build version list
        versions: list[PackageVersion] = []
        current_id = root_id

        while current_id:
            stmt = select(AasxPackageTable).where(AasxPackageTable.id == current_id)
            result = await session.execute(stmt)
            package = result.scalar_one_or_none()

            if not package:
                break

            versions.append(
                PackageVersion(
                    version=package.version,
                    created_at=package.created_at,
                    created_by=package.created_by,
                    comment=package.version_comment,
                    content_hash=package.content_hash,
                    parent_version=package.version - 1 if package.previous_version_id else None,
                )
            )

            # Find next version (package that references current as previous)
            stmt = select(AasxPackageTable).where(
                AasxPackageTable.previous_version_id == current_id
            )
            result = await session.execute(stmt)
            next_package = result.scalar_one_or_none()

            current_id = next_package.id if next_package else None

        return versions

    async def rollback_to_version(
        self,
        session: AsyncSession,
        package_id: str,
        target_version: int,
    ) -> str:
        """Rollback to a previous version.

        Creates a new version that is a copy of the target version's content.
        This preserves history rather than deleting newer versions.

        Args:
            session: Database session
            package_id: ID of any package in the version chain
            target_version: Version number to rollback to

        Returns:
            ID of the new rollback version

        Raises:
            ValueError: If package or target version not found
        """
        # Find all versions in the chain
        versions_meta = await self.list_versions(session, package_id)

        if not versions_meta:
            raise ValueError(f"No versions found for package {package_id}")

        # Find the target version
        target_found = False
        for v in versions_meta:
            if v.version == target_version:
                target_found = True
                break

        if not target_found:
            raise ValueError(
                f"Version {target_version} not found. "
                f"Available versions: {[v.version for v in versions_meta]}"
            )

        # Get the actual database record for the target version
        # We need to find it by traversing the chain
        current_id = package_id
        root_id = package_id

        # Find root first
        while True:
            stmt = select(AasxPackageTable).where(AasxPackageTable.id == current_id)
            result = await session.execute(stmt)
            package = result.scalar_one_or_none()

            if not package:
                break

            if package.previous_version_id:
                current_id = package.previous_version_id
                root_id = current_id
            else:
                break

        # Traverse forward to find target version
        current_id = root_id
        target_package = None

        while current_id:
            stmt = select(AasxPackageTable).where(AasxPackageTable.id == current_id)
            result = await session.execute(stmt)
            package = result.scalar_one_or_none()

            if not package:
                break

            if package.version == target_version:
                target_package = package
                break

            # Find next version
            stmt = select(AasxPackageTable).where(
                AasxPackageTable.previous_version_id == current_id
            )
            result = await session.execute(stmt)
            next_package = result.scalar_one_or_none()

            current_id = next_package.id if next_package else None

        if not target_package:
            raise ValueError(f"Could not find package record for version {target_version}")

        # Get the latest version to determine new version number
        stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
        result = await session.execute(stmt)
        latest = result.scalar_one_or_none()

        if not latest:
            raise ValueError(f"Package not found: {package_id}")

        # Create rollback version
        # Note: This creates a new DB record but should reference the same storage_uri
        # In a production system, you might want to copy the blob content
        new_id = str(uuid4())
        rollback_package = AasxPackageTable(
            id=new_id,
            filename=target_package.filename,
            storage_uri=target_package.storage_uri,  # Reuse same storage
            size_bytes=target_package.size_bytes,
            content_hash=target_package.content_hash,
            version=latest.version + 1,
            version_comment=f"Rollback to version {target_version}",
            created_by=None,  # Could add a parameter for this
            previous_version_id=package_id,
            shell_count=target_package.shell_count,
            submodel_count=target_package.submodel_count,
            concept_description_count=target_package.concept_description_count,
            package_info=target_package.package_info,
        )

        session.add(rollback_package)
        await session.commit()

        logger.info(
            f"Rolled back to version {target_version} for package chain starting at {package_id}. "
            f"New version {rollback_package.version} created with ID {new_id}"
        )

        return new_id
