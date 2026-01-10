"""Tests for AASX Package Manager."""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import AsyncMock

import pytest

from titan.packages.manager import (
    ConflictResolution,
    ExportOptions,
    ImportResult,
    PackageManager,
    PackageVersion,
)


def create_test_aasx() -> bytes:
    """Create a test AASX package."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Content types
        content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="json" ContentType="application/json"/>
</Types>"""
        zf.writestr("[Content_Types].xml", content_types)

        # Root relationships
        rels = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Type="http://admin-shell.io/aasx/relationships/aasx-origin"
        Target="/aasx/aasx-origin" Id="rId1"/>
</Relationships>"""
        zf.writestr("_rels/.rels", rels)

        zf.writestr("aasx/aasx-origin", "")

        env_json = b"""{
            "assetAdministrationShells": [
                {
                    "id": "urn:test:aas:001",
                    "idShort": "TestAAS",
                    "assetInformation": {
                        "assetKind": "Instance",
                        "globalAssetId": "urn:test:asset:001"
                    }
                }
            ],
            "submodels": [
                {
                    "id": "urn:test:submodel:001",
                    "idShort": "TestSubmodel"
                }
            ],
            "conceptDescriptions": []
        }"""
        zf.writestr("aasx/aas-environment.json", env_json)

    buffer.seek(0)
    return buffer.read()


class TestPackageVersion:
    """Tests for PackageVersion."""

    def test_default_version(self):
        """Default version is 1."""
        version = PackageVersion()
        assert version.version == 1

    def test_version_with_comment(self):
        """Version can have comment."""
        version = PackageVersion(version=2, comment="Updated content")
        assert version.version == 2
        assert version.comment == "Updated content"


class TestImportResult:
    """Tests for ImportResult."""

    def test_total_created(self):
        """Total created sums all created counts."""
        result = ImportResult(
            success=True,
            shells_created=2,
            submodels_created=3,
            concept_descriptions_created=1,
        )
        assert result.total_created == 6

    def test_total_skipped(self):
        """Total skipped sums all skipped counts."""
        result = ImportResult(
            success=True,
            shells_skipped=1,
            submodels_skipped=2,
            concept_descriptions_skipped=3,
        )
        assert result.total_skipped == 6

    def test_to_dict(self):
        """to_dict returns structured response."""
        result = ImportResult(
            success=True,
            shells_created=1,
            submodels_created=2,
        )
        data = result.to_dict()

        assert data["success"] is True
        assert data["shells"]["created"] == 1
        assert data["submodels"]["created"] == 2


class TestPackageManager:
    """Tests for PackageManager."""

    @pytest.mark.asyncio
    async def test_validate_package(self):
        """Validate returns validation result."""
        content = create_test_aasx()
        manager = PackageManager()

        result = await manager.validate(BytesIO(content))

        assert result.valid or len(result.warnings) > 0
        assert result.content_hash is not None

    @pytest.mark.asyncio
    async def test_parse_package(self):
        """Parse extracts shells and submodels."""
        content = create_test_aasx()
        manager = PackageManager()

        package = await manager.parse(BytesIO(content))

        assert len(package.shells) == 1
        assert package.shells[0].id == "urn:test:aas:001"
        assert len(package.submodels) == 1
        assert package.submodels[0].id == "urn:test:submodel:001"

    @pytest.mark.asyncio
    async def test_preview_import_no_conflicts(self):
        """Preview shows items to import without conflicts."""
        content = create_test_aasx()
        manager = PackageManager()

        # Mock repos that return False for exists
        aas_repo = AsyncMock()
        aas_repo.exists = AsyncMock(return_value=False)
        submodel_repo = AsyncMock()
        submodel_repo.exists = AsyncMock(return_value=False)

        preview = await manager.preview_import(
            BytesIO(content),
            aas_repo=aas_repo,
            submodel_repo=submodel_repo,
        )

        assert len(preview["shells"]) == 1
        assert preview["shells"][0]["exists"] is False
        assert preview["conflicts"]["shells"] == 0

    @pytest.mark.asyncio
    async def test_preview_import_with_conflicts(self):
        """Preview detects existing items as conflicts."""
        content = create_test_aasx()
        manager = PackageManager()

        # Mock repos that return True for exists
        aas_repo = AsyncMock()
        aas_repo.exists = AsyncMock(return_value=True)
        submodel_repo = AsyncMock()
        submodel_repo.exists = AsyncMock(return_value=True)

        preview = await manager.preview_import(
            BytesIO(content),
            aas_repo=aas_repo,
            submodel_repo=submodel_repo,
        )

        assert preview["shells"][0]["exists"] is True
        assert preview["conflicts"]["shells"] == 1
        assert preview["conflicts"]["submodels"] == 1

    @pytest.mark.asyncio
    async def test_import_skip_conflicts(self):
        """Import with SKIP resolution skips existing items."""
        content = create_test_aasx()
        manager = PackageManager()

        aas_repo = AsyncMock()
        aas_repo.exists = AsyncMock(return_value=True)
        aas_repo.create = AsyncMock()

        submodel_repo = AsyncMock()
        submodel_repo.exists = AsyncMock(return_value=True)
        submodel_repo.create = AsyncMock()

        result = await manager.import_package(
            BytesIO(content),
            aas_repo=aas_repo,
            submodel_repo=submodel_repo,
            conflict_resolution=ConflictResolution.SKIP,
        )

        assert result.shells_skipped == 1
        assert result.submodels_skipped == 1
        assert result.shells_created == 0
        aas_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_import_overwrite_conflicts(self):
        """Import with OVERWRITE resolution updates existing items."""
        content = create_test_aasx()
        manager = PackageManager()

        aas_repo = AsyncMock()
        aas_repo.exists = AsyncMock(return_value=True)
        aas_repo.update = AsyncMock()

        submodel_repo = AsyncMock()
        submodel_repo.exists = AsyncMock(return_value=True)
        submodel_repo.update = AsyncMock()

        result = await manager.import_package(
            BytesIO(content),
            aas_repo=aas_repo,
            submodel_repo=submodel_repo,
            conflict_resolution=ConflictResolution.OVERWRITE,
        )

        assert result.shells_updated == 1
        assert result.submodels_updated == 1
        aas_repo.update.assert_called_once()
        submodel_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_error_on_conflicts(self):
        """Import with ERROR resolution fails on conflicts."""
        content = create_test_aasx()
        manager = PackageManager()

        aas_repo = AsyncMock()
        aas_repo.exists = AsyncMock(return_value=True)

        submodel_repo = AsyncMock()
        submodel_repo.exists = AsyncMock(return_value=True)

        result = await manager.import_package(
            BytesIO(content),
            aas_repo=aas_repo,
            submodel_repo=submodel_repo,
            conflict_resolution=ConflictResolution.ERROR,
        )

        assert not result.success
        assert result.shells_failed == 1
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_import_partial_shells(self):
        """Import with shell_ids filters to specific shells."""
        content = create_test_aasx()
        manager = PackageManager()

        aas_repo = AsyncMock()
        aas_repo.exists = AsyncMock(return_value=False)
        aas_repo.create = AsyncMock()

        submodel_repo = AsyncMock()
        submodel_repo.exists = AsyncMock(return_value=False)
        submodel_repo.create = AsyncMock()

        result = await manager.import_package(
            BytesIO(content),
            aas_repo=aas_repo,
            submodel_repo=submodel_repo,
            shell_ids=["nonexistent:shell"],  # Won't match
        )

        assert result.shells_created == 0
        aas_repo.create.assert_not_called()
        # Submodels should still be imported
        assert result.submodels_created == 1


class TestExportOptions:
    """Tests for ExportOptions."""

    def test_default_includes_all(self):
        """Default options include all content types."""
        options = ExportOptions()
        assert options.include_shells is True
        assert options.include_submodels is True
        assert options.include_concept_descriptions is True

    def test_selective_export(self):
        """Can configure selective export."""
        options = ExportOptions(
            include_shells=True,
            include_submodels=False,
            shell_ids=["urn:test:aas:001"],
        )
        assert options.shell_ids == ["urn:test:aas:001"]
        assert not options.include_submodels
