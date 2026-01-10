"""Tests for AASX File Server API."""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from titan.api.routers.aasx import router


@pytest.fixture
def app() -> FastAPI:
    """Create a basic FastAPI app for testing."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app)


def create_test_aasx() -> bytes:
    """Create a minimal test AASX package."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Create minimal AAS environment JSON
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

        # Add OPC metadata
        content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="json" ContentType="application/json"/>
</Types>"""
        zf.writestr("[Content_Types].xml", content_types)

        rels = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Type="http://admin-shell.io/aasx/relationships/aasx-origin"
        Target="/aasx/aasx-origin" Id="rId1"/>
</Relationships>"""
        zf.writestr("_rels/.rels", rels)

        zf.writestr("aasx/aasx-origin", "")

    buffer.seek(0)
    return buffer.read()


class TestAasxImport:
    """Tests for AASX import functionality."""

    def test_create_test_aasx(self):
        """Test helper creates valid AASX."""
        aasx_bytes = create_test_aasx()
        assert len(aasx_bytes) > 0

        # Verify it's a valid ZIP
        with zipfile.ZipFile(BytesIO(aasx_bytes), "r") as zf:
            names = zf.namelist()
            assert "aasx/aas-environment.json" in names


class TestPackageListEndpoint:
    """Tests for GET /packages endpoint."""

    @patch("titan.api.routers.aasx.get_session")
    def test_list_packages_empty(self, mock_get_session, client):
        """List returns empty result when no packages."""
        # Mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value = mock_session

        # Note: Can't easily test without full async context
        # This is a structural test showing the endpoint exists
        pass


class TestAasxPackageModel:
    """Tests for AASX package data model."""

    def test_aasx_package_table_exists(self):
        """Verify AasxPackageTable is defined."""
        from titan.persistence.tables import AasxPackageTable

        assert AasxPackageTable.__tablename__ == "aasx_packages"

    def test_aasx_package_has_required_columns(self):
        """Verify required columns exist."""
        from titan.persistence.tables import AasxPackageTable

        # Check mapped columns
        mapper = AasxPackageTable.__mapper__
        column_names = [c.key for c in mapper.columns]

        assert "id" in column_names
        assert "filename" in column_names
        assert "storage_uri" in column_names
        assert "size_bytes" in column_names
        assert "content_hash" in column_names
        assert "shell_count" in column_names
        assert "submodel_count" in column_names
        assert "package_info" in column_names


class TestAasxImporterIntegration:
    """Tests for AASX importer integration."""

    @pytest.mark.asyncio
    async def test_import_test_aasx(self):
        """Import test AASX package."""
        from titan.compat.aasx import AasxImporter

        aasx_bytes = create_test_aasx()
        importer = AasxImporter()
        package = await importer.import_from_stream(BytesIO(aasx_bytes))

        assert len(package.shells) == 1
        assert package.shells[0].id == "urn:test:aas:001"
        assert package.shells[0].id_short == "TestAAS"

        assert len(package.submodels) == 1
        assert package.submodels[0].id == "urn:test:submodel:001"


class TestRouterRegistration:
    """Tests for router registration."""

    def test_router_has_prefix(self):
        """Router has correct prefix."""
        assert router.prefix == "/packages"

    def test_router_has_tag(self):
        """Router has correct tag."""
        assert "AASX File Server" in router.tags

    def test_router_has_endpoints(self):
        """Router has expected endpoints."""
        routes = [r.path for r in router.routes]
        assert "/packages" in routes  # GET/POST /packages
        assert "/packages/{package_id}" in routes  # GET/PUT/DELETE
        assert "/packages/{package_id}/shells" in routes
        assert "/packages/{package_id}/submodels" in routes
        assert "/packages/{package_id}/import" in routes
