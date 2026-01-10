"""AASX Package Manager.

Handles package lifecycle including:
- Version tracking
- Import with conflict resolution
- Export with selective content
- Package metadata
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import Any, BinaryIO

from titan.compat.aasx import AasxExporter, AasxImporter, AasxPackage
from titan.core.model import AssetAdministrationShell, ConceptDescription, Submodel
from titan.packages.validator import OpcValidator, ValidationLevel, ValidationResult

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
