"""Tests for AASX package import/export."""

import zipfile
from io import BytesIO

import pytest

from titan.compat.aasx import (
    AasxExporter,
    AasxImporter,
    AasxPackage,
)
from titan.core.model import (
    AssetAdministrationShell,
    AssetInformation,
    AssetKind,
    ConceptDescription,
    Property,
    Submodel,
)


class TestAasxPackage:
    """Tests for AasxPackage dataclass."""

    def test_empty_package(self):
        """Create an empty AASX package."""
        package = AasxPackage()

        assert package.shells == []
        assert package.submodels == []
        assert package.concept_descriptions == []
        assert package.supplementary_files == {}
        assert package.metadata == {}

    def test_package_with_content(self):
        """Create a package with shells, submodels, and CDs."""
        shell = AssetAdministrationShell(
            id="urn:aas:1",
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:asset:1",
            ),
        )
        submodel = Submodel(id="urn:sm:1")
        cd = ConceptDescription(id="urn:cd:1")

        package = AasxPackage(
            shells=[shell],
            submodels=[submodel],
            concept_descriptions=[cd],
        )

        assert len(package.shells) == 1
        assert len(package.submodels) == 1
        assert len(package.concept_descriptions) == 1


class TestAasxExporter:
    """Tests for AasxExporter."""

    @pytest.mark.asyncio
    async def test_export_empty_package_json(self):
        """Export an empty package to JSON."""
        exporter = AasxExporter()
        buffer = await exporter.export_to_stream(
            shells=[],
            submodels=[],
            use_json=True,
        )

        # Verify it's a valid ZIP file
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as zf:
            names = zf.namelist()
            # IDTA Part 5 allows both "data.json" and "aas-environment.json"
            # We use "data.json" for BaSyx compatibility
            assert "aasx/data.json" in names
            assert "[Content_Types].xml" in names
            assert "_rels/.rels" in names

    @pytest.mark.asyncio
    async def test_export_empty_package_xml(self):
        """Export an empty package to XML."""
        exporter = AasxExporter()
        buffer = await exporter.export_to_stream(
            shells=[],
            submodels=[],
            use_json=False,  # Use XML
        )

        # Verify it's a valid ZIP file with XML content
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as zf:
            names = zf.namelist()
            # IDTA Part 5 allows both "data.xml" and "aas-environment.xml"
            # We use "data.xml" for BaSyx compatibility
            assert "aasx/data.xml" in names

    @pytest.mark.asyncio
    async def test_export_with_shells_json(self):
        """Export package with shells to JSON."""
        shell = AssetAdministrationShell(
            id="urn:aas:export:1",
            id_short="ExportTest",
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:asset:export:1",
            ),
        )

        exporter = AasxExporter()
        buffer = await exporter.export_to_stream(
            shells=[shell],
            submodels=[],
            use_json=True,
        )

        # Verify content
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as zf:
            content = zf.read("aasx/data.json")
            assert b"urn:aas:export:1" in content
            assert b"ExportTest" in content

    @pytest.mark.asyncio
    async def test_export_with_concept_descriptions(self):
        """Export package with concept descriptions."""
        cd = ConceptDescription(
            id="urn:cd:export:1",
            id_short="ExportCD",
            description=[{"language": "en", "text": "Export test CD"}],
        )

        exporter = AasxExporter()
        buffer = await exporter.export_to_stream(
            shells=[],
            submodels=[],
            concept_descriptions=[cd],
            use_json=True,
        )

        # Verify content includes CD
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as zf:
            content = zf.read("aasx/data.json")
            assert b"urn:cd:export:1" in content
            assert b"ExportCD" in content


class TestAasxImporter:
    """Tests for AasxImporter."""

    @pytest.mark.asyncio
    async def test_import_json_package(self):
        """Import a JSON AASX package."""
        # First export
        shell = AssetAdministrationShell(
            id="urn:aas:import:1",
            id_short="ImportTest",
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:asset:import:1",
            ),
        )

        exporter = AasxExporter()
        buffer = await exporter.export_to_stream([shell], [], use_json=True)

        # Then import
        importer = AasxImporter()
        buffer.seek(0)
        package = await importer.import_from_stream(buffer)

        assert len(package.shells) == 1
        assert package.shells[0].id == "urn:aas:import:1"
        assert package.shells[0].id_short == "ImportTest"

    @pytest.mark.asyncio
    async def test_import_xml_package(self):
        """Import an XML AASX package."""
        # First export as XML
        shell = AssetAdministrationShell(
            id="urn:aas:xml:1",
            id_short="XmlTest",
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:asset:xml:1",
            ),
        )

        exporter = AasxExporter()
        buffer = await exporter.export_to_stream([shell], [], use_json=False)

        # Then import
        importer = AasxImporter()
        buffer.seek(0)
        package = await importer.import_from_stream(buffer)

        assert len(package.shells) == 1
        assert package.shells[0].id == "urn:aas:xml:1"

    @pytest.mark.asyncio
    async def test_import_invalid_zip_raises(self):
        """Importing invalid ZIP should raise ValueError."""
        importer = AasxImporter()
        buffer = BytesIO(b"not a zip file")

        with pytest.raises(ValueError, match="Invalid AASX package"):
            await importer.import_from_stream(buffer)


class TestAasxRoundTrip:
    """Tests for AASX round-trip (export -> import)."""

    @pytest.mark.asyncio
    async def test_json_roundtrip_full_environment(self):
        """Full environment round-trip with JSON."""
        shell = AssetAdministrationShell(
            id="urn:aas:rt:1",
            id_short="RoundtripAAS",
            asset_information=AssetInformation(
                asset_kind=AssetKind.TYPE,
                global_asset_id="urn:asset:rt:1",
            ),
        )

        submodel = Submodel(
            id="urn:sm:rt:1",
            id_short="RoundtripSubmodel",
            submodel_elements=[
                Property(
                    id_short="RoundtripProp",
                    value_type="xs:string",
                    value="roundtrip-value",
                ),
            ],
        )

        cd = ConceptDescription(
            id="urn:cd:rt:1",
            id_short="RoundtripCD",
        )

        exporter = AasxExporter()
        buffer = await exporter.export_to_stream(
            shells=[shell],
            submodels=[submodel],
            concept_descriptions=[cd],
            use_json=True,
        )

        importer = AasxImporter()
        buffer.seek(0)
        package = await importer.import_from_stream(buffer)

        assert len(package.shells) == 1
        assert len(package.submodels) == 1
        assert len(package.concept_descriptions) == 1

        assert package.shells[0].id == "urn:aas:rt:1"
        assert package.submodels[0].id == "urn:sm:rt:1"
        assert package.concept_descriptions[0].id == "urn:cd:rt:1"

    @pytest.mark.asyncio
    async def test_xml_roundtrip_full_environment(self):
        """Full environment round-trip with XML."""
        shell = AssetAdministrationShell(
            id="urn:aas:xml:rt:1",
            id_short="XmlRoundtripAAS",
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:asset:xml:rt:1",
            ),
        )

        submodel = Submodel(
            id="urn:sm:xml:rt:1",
            id_short="XmlRoundtripSubmodel",
        )

        cd = ConceptDescription(
            id="urn:cd:xml:rt:1",
            id_short="XmlRoundtripCD",
        )

        exporter = AasxExporter()
        buffer = await exporter.export_to_stream(
            shells=[shell],
            submodels=[submodel],
            concept_descriptions=[cd],
            use_json=False,  # Use XML
        )

        importer = AasxImporter()
        buffer.seek(0)
        package = await importer.import_from_stream(buffer)

        assert len(package.shells) == 1
        assert len(package.submodels) == 1
        assert len(package.concept_descriptions) == 1

        assert package.shells[0].id == "urn:aas:xml:rt:1"
        assert package.submodels[0].id == "urn:sm:xml:rt:1"
        assert package.concept_descriptions[0].id == "urn:cd:xml:rt:1"
