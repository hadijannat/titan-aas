"""Package version comparison and diff generation.

Provides functionality to compare two package versions and generate diffs:
- Structural comparison (shells, submodels, concept descriptions)
- JSON Patch format diff generation (RFC 6902)
- Supplementary file change detection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan.compat.aasx import AasxImporter
from titan.persistence.tables import AasxPackageTable

logger = logging.getLogger(__name__)


@dataclass
class PackageComparison:
    """Result of comparing two package versions.

    Provides a high-level summary of differences between versions.
    """

    shells_added: list[str] = field(default_factory=list)
    shells_removed: list[str] = field(default_factory=list)
    shells_modified: list[str] = field(default_factory=list)
    submodels_added: list[str] = field(default_factory=list)
    submodels_removed: list[str] = field(default_factory=list)
    submodels_modified: list[str] = field(default_factory=list)
    concept_descriptions_added: list[str] = field(default_factory=list)
    concept_descriptions_removed: list[str] = field(default_factory=list)
    supplementary_files_changed: bool = False

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes between versions."""
        return (
            len(self.shells_added) > 0
            or len(self.shells_removed) > 0
            or len(self.shells_modified) > 0
            or len(self.submodels_added) > 0
            or len(self.submodels_removed) > 0
            or len(self.submodels_modified) > 0
            or len(self.concept_descriptions_added) > 0
            or len(self.concept_descriptions_removed) > 0
            or self.supplementary_files_changed
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hasChanges": self.has_changes,
            "shellsAdded": self.shells_added,
            "shellsRemoved": self.shells_removed,
            "shellsModified": self.shells_modified,
            "submodelsAdded": self.submodels_added,
            "submodelsRemoved": self.submodels_removed,
            "submodelsModified": self.submodels_modified,
            "conceptDescriptionsAdded": self.concept_descriptions_added,
            "conceptDescriptionsRemoved": self.concept_descriptions_removed,
            "supplementaryFilesChanged": self.supplementary_files_changed,
        }


class PackageDiffer:
    """Compares package versions and generates diffs."""

    def __init__(self) -> None:
        self.importer = AasxImporter()

    async def compare(
        self,
        session: AsyncSession,
        package_id: str,
        version1: int,
        version2: int,
    ) -> PackageComparison:
        """Compare two package versions.

        Args:
            session: Database session
            package_id: ID of any package in the version chain
            version1: First version number
            version2: Second version number

        Returns:
            PackageComparison with structural differences

        Raises:
            ValueError: If versions not found
        """
        # Get both version packages
        pkg1, pkg2 = await self._get_version_packages(session, package_id, version1, version2)

        # Retrieve and parse both packages
        from titan.api.routers.aasx import _retrieve_package

        content1 = await _retrieve_package(pkg1.storage_uri)
        content2 = await _retrieve_package(pkg2.storage_uri)

        parsed1 = await self.importer.import_from_stream(BytesIO(content1))
        parsed2 = await self.importer.import_from_stream(BytesIO(content2))

        # Compare structures
        comparison = PackageComparison()

        # Compare shells
        shells1 = {shell.id for shell in parsed1.shells}
        shells2 = {shell.id for shell in parsed2.shells}

        comparison.shells_added = list(shells2 - shells1)
        comparison.shells_removed = list(shells1 - shells2)

        # Check for modified shells (same ID but different content)
        common_shells = shells1 & shells2
        for shell_id in common_shells:
            shell1 = next(s for s in parsed1.shells if s.id == shell_id)
            shell2 = next(s for s in parsed2.shells if s.id == shell_id)
            if self._shells_differ(shell1, shell2):
                comparison.shells_modified.append(shell_id)

        # Compare submodels
        submodels1 = {sm.id for sm in parsed1.submodels}
        submodels2 = {sm.id for sm in parsed2.submodels}

        comparison.submodels_added = list(submodels2 - submodels1)
        comparison.submodels_removed = list(submodels1 - submodels2)

        # Check for modified submodels
        common_submodels = submodels1 & submodels2
        for sm_id in common_submodels:
            sm1 = next(s for s in parsed1.submodels if s.id == sm_id)
            sm2 = next(s for s in parsed2.submodels if s.id == sm_id)
            if self._submodels_differ(sm1, sm2):
                comparison.submodels_modified.append(sm_id)

        # Compare concept descriptions
        cds1 = {cd.id for cd in parsed1.concept_descriptions}
        cds2 = {cd.id for cd in parsed2.concept_descriptions}

        comparison.concept_descriptions_added = list(cds2 - cds1)
        comparison.concept_descriptions_removed = list(cds1 - cds2)

        # Check supplementary files (simple count comparison)
        files1 = len(parsed1.supplementary_files) if parsed1.supplementary_files else 0
        files2 = len(parsed2.supplementary_files) if parsed2.supplementary_files else 0
        comparison.supplementary_files_changed = files1 != files2

        logger.info(
            f"Compared package versions {version1} vs {version2}: "
            f"{len(comparison.shells_added)} shells added, "
            f"{len(comparison.submodels_modified)} submodels modified"
        )

        return comparison

    async def diff(
        self,
        session: AsyncSession,
        package_id: str,
        version1: int,
        version2: int,
    ) -> list[dict[str, Any]]:
        """Generate JSON Patch diff between two versions.

        Args:
            session: Database session
            package_id: ID of any package in the version chain
            version1: First version number (base)
            version2: Second version number (target)

        Returns:
            List of JSON Patch operations (RFC 6902)

        Raises:
            ValueError: If versions not found
        """
        # Get both version packages
        pkg1, pkg2 = await self._get_version_packages(session, package_id, version1, version2)

        # Retrieve and parse both packages
        from titan.api.routers.aasx import _retrieve_package

        content1 = await _retrieve_package(pkg1.storage_uri)
        content2 = await _retrieve_package(pkg2.storage_uri)

        parsed1 = await self.importer.import_from_stream(BytesIO(content1))
        parsed2 = await self.importer.import_from_stream(BytesIO(content2))

        # Generate JSON Patch operations
        operations: list[dict[str, Any]] = []

        # Diff shells
        shells1_map = {s.id: s for s in parsed1.shells}
        shells2_map = {s.id: s for s in parsed2.shells}

        # Added shells
        for shell_id in shells2_map.keys() - shells1_map.keys():
            operations.append(
                {
                    "op": "add",
                    "path": "/assetAdministrationShells/-",
                    "value": {"id": shell_id, "idShort": shells2_map[shell_id].id_short},
                }
            )

        # Removed shells
        for shell_id in shells1_map.keys() - shells2_map.keys():
            # Find index
            idx = next(i for i, s in enumerate(parsed1.shells) if s.id == shell_id)
            operations.append(
                {
                    "op": "remove",
                    "path": f"/assetAdministrationShells/{idx}",
                }
            )

        # Modified shells (simplified - just report as replace)
        for shell_id in shells1_map.keys() & shells2_map.keys():
            if self._shells_differ(shells1_map[shell_id], shells2_map[shell_id]):
                idx = next(i for i, s in enumerate(parsed1.shells) if s.id == shell_id)
                operations.append(
                    {
                        "op": "replace",
                        "path": f"/assetAdministrationShells/{idx}",
                        "value": {"id": shell_id, "idShort": shells2_map[shell_id].id_short},
                    }
                )

        # Diff submodels (similar logic)
        submodels1_map = {s.id: s for s in parsed1.submodels}
        submodels2_map = {s.id: s for s in parsed2.submodels}

        # Added submodels
        for sm_id in submodels2_map.keys() - submodels1_map.keys():
            operations.append(
                {
                    "op": "add",
                    "path": "/submodels/-",
                    "value": {"id": sm_id, "idShort": submodels2_map[sm_id].id_short},
                }
            )

        # Removed submodels
        for sm_id in submodels1_map.keys() - submodels2_map.keys():
            idx = next(i for i, s in enumerate(parsed1.submodels) if s.id == sm_id)
            operations.append(
                {
                    "op": "remove",
                    "path": f"/submodels/{idx}",
                }
            )

        # Modified submodels
        for sm_id in submodels1_map.keys() & submodels2_map.keys():
            if self._submodels_differ(submodels1_map[sm_id], submodels2_map[sm_id]):
                idx = next(i for i, s in enumerate(parsed1.submodels) if s.id == sm_id)
                operations.append(
                    {
                        "op": "replace",
                        "path": f"/submodels/{idx}",
                        "value": {"id": sm_id, "idShort": submodels2_map[sm_id].id_short},
                    }
                )

        logger.info(
            f"Generated {len(operations)} JSON Patch operations "
            f"for versions {version1} vs {version2}"
        )

        return operations

    async def _get_version_packages(
        self,
        session: AsyncSession,
        package_id: str,
        version1: int,
        version2: int,
    ) -> tuple[AasxPackageTable, AasxPackageTable]:
        """Retrieve package records for two versions.

        Args:
            session: Database session
            package_id: ID of any package in the version chain
            version1: First version number
            version2: Second version number

        Returns:
            Tuple of (package1, package2)

        Raises:
            ValueError: If either version not found
        """
        # Start from package_id and traverse to find all packages in chain
        stmt = select(AasxPackageTable).where(AasxPackageTable.id == package_id)
        result = await session.execute(stmt)
        current = result.scalar_one_or_none()

        if not current:
            raise ValueError(f"Package not found: {package_id}")

        # Traverse backward to root and collect all packages
        visited: dict[int, AasxPackageTable] = {current.version: current}
        while current.previous_version_id:
            stmt = select(AasxPackageTable).where(
                AasxPackageTable.id == current.previous_version_id
            )
            result = await session.execute(stmt)
            current = result.scalar_one_or_none()
            if not current:
                break
            visited[current.version] = current

        # Find the requested versions
        pkg1 = visited.get(version1)
        pkg2 = visited.get(version2)

        if not pkg1:
            raise ValueError(f"Version {version1} not found in package chain")
        if not pkg2:
            raise ValueError(f"Version {version2} not found in package chain")

        return pkg1, pkg2

    def _shells_differ(self, shell1: Any, shell2: Any) -> bool:
        """Check if two shells have different content."""
        # Simple comparison - in production, would do deep comparison
        return bool(
            shell1.id_short != shell2.id_short
            or shell1.description != shell2.description
            or shell1.asset_information != shell2.asset_information
        )

    def _submodels_differ(self, sm1: Any, sm2: Any) -> bool:
        """Check if two submodels have different content."""
        # Simple comparison - in production, would do deep comparison
        return bool(
            sm1.id_short != sm2.id_short
            or sm1.description != sm2.description
            or sm1.semantic_id != sm2.semantic_id
            or len(sm1.submodel_elements or []) != len(sm2.submodel_elements or [])
        )
