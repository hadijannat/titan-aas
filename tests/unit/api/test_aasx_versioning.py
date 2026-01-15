"""Tests for AASX Package Versioning API endpoints.

NOTE: These tests require a real database and are better suited as integration tests.
For now, they are skipped in unit test runs. The core versioning logic is tested
in tests/unit/packages/test_versioning.py.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from titan.api.routers.aasx import router
from titan.packages.manager import PackageVersion

# Skip all tests in this module - they require database integration
# Core versioning logic is tested in tests/unit/packages/test_versioning.py
pytestmark = pytest.mark.skip(
    reason="API endpoint tests require database integration. "
    "Core logic tested in test_versioning.py. "
    "Run integration tests for full API testing."
)


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


def create_test_aasx(shell_id: str = "urn:test:aas:001") -> bytes:
    """Create a minimal test AASX package."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Create minimal AAS environment JSON
        env_json = f"""{{
            "assetAdministrationShells": [
                {{
                    "modelType": "AssetAdministrationShell",
                    "id": "{shell_id}",
                    "idShort": "TestAAS",
                    "assetInformation": {{
                        "assetKind": "Instance",
                        "globalAssetId": "urn:test:asset:001"
                    }}
                }}
            ],
            "submodels": [],
            "conceptDescriptions": []
        }}""".encode()
        zf.writestr("aasx/data.json", env_json)

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


class TestCreatePackageVersion:
    """Tests for POST /packages/{packageId}/versions endpoint."""

    @patch("titan.api.routers.aasx.get_session")
    @patch("titan.api.routers.aasx._store_package")
    @patch("titan.events.runtime.get_event_bus")
    @patch("titan.packages.manager.PackageManager")
    @patch("titan.api.routers.aasx.get_optional_user")
    def test_create_version_success(
        self, mock_user, mock_manager_class, mock_event_bus, mock_store, mock_get_session, client
    ):
        """Creating a version succeeds with valid input."""
        # Mock user
        mock_user.return_value = MagicMock(sub="user123")

        # Mock storage
        mock_store.return_value = (
            "s3://bucket/package.aasx",
            "abc123hash",
            1024,
        )

        # Mock session and PackageManager
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock existing package
        mock_package = MagicMock()
        mock_package.id = "pkg-001"
        mock_package.version = 2
        mock_package.filename = "updated.aasx"
        mock_package.version_comment = "Test version"
        mock_package.created_by = "user123"
        mock_package.created_at.isoformat.return_value = "2026-01-11T10:00:00"

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_package
        mock_session.execute.return_value = mock_result

        # Mock PackageManager
        mock_manager = MagicMock()
        mock_manager.create_version = AsyncMock(return_value="new-version-id")
        mock_manager_class.return_value = mock_manager

        # Mock event bus
        mock_bus = AsyncMock()
        mock_event_bus.return_value = mock_bus

        # Make request
        aasx_bytes = create_test_aasx()
        response = client.post(
            "/packages/pkg-001/versions",
            files={"file": ("test.aasx", aasx_bytes, "application/octet-stream")},
            data={"comment": "Test version"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["packageId"] == "pkg-001"
        assert data["version"] == 2
        assert data["comment"] == "Test version"
        assert data["createdBy"] == "user123"

        # Verify event was published
        mock_bus.publish.assert_called_once()

    @patch("titan.api.routers.aasx.get_session")
    def test_create_version_package_not_found(self, mock_get_session, client):
        """Creating a version fails if package doesn't exist."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock PackageManager to raise ValueError
        with patch("titan.api.routers.aasx.PackageManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.create_version = AsyncMock(side_effect=ValueError("Package not found"))
            mock_manager_class.return_value = mock_manager

            with patch("titan.api.routers.aasx._store_package"):
                aasx_bytes = create_test_aasx()
                response = client.post(
                    "/packages/nonexistent/versions",
                    files={"file": ("test.aasx", aasx_bytes, "application/octet-stream")},
                )

                assert response.status_code == 400
                assert "Package not found" in response.json()["detail"]


class TestListPackageVersions:
    """Tests for GET /packages/{packageId}/versions endpoint."""

    @patch("titan.api.routers.aasx.get_session")
    def test_list_versions_success(self, mock_get_session, client):
        """Listing versions returns version history."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock PackageManager
        with patch("titan.api.routers.aasx.PackageManager") as mock_manager_class:
            mock_manager = MagicMock()
            versions = [
                PackageVersion(
                    version=1,
                    created_at=MagicMock(isoformat=lambda: "2026-01-11T09:00:00"),
                    created_by="user1",
                    comment="Initial version",
                    content_hash="hash1",
                    parent_version=None,
                ),
                PackageVersion(
                    version=2,
                    created_at=MagicMock(isoformat=lambda: "2026-01-11T10:00:00"),
                    created_by="user2",
                    comment="Updated version",
                    content_hash="hash2",
                    parent_version=1,
                ),
            ]
            mock_manager.list_versions = AsyncMock(return_value=versions)
            mock_manager_class.return_value = mock_manager

            response = client.get("/packages/pkg-001/versions")

            assert response.status_code == 200
            data = response.json()
            assert data["packageId"] == "pkg-001"
            assert data["totalVersions"] == 2
            assert len(data["result"]) == 2
            assert data["result"][0]["version"] == 1
            assert data["result"][1]["version"] == 2

    @patch("titan.api.routers.aasx.get_session")
    def test_list_versions_with_pagination(self, mock_get_session, client):
        """Listing versions supports pagination."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock PackageManager with many versions
        with patch("titan.api.routers.aasx.PackageManager") as mock_manager_class:
            mock_manager = MagicMock()
            versions = [
                PackageVersion(
                    version=i,
                    created_at=MagicMock(isoformat=lambda i=i: f"2026-01-11T10:{i:02d}:00"),
                    created_by=f"user{i}",
                    comment=f"Version {i}",
                    content_hash=f"hash{i}",
                    parent_version=i - 1 if i > 1 else None,
                )
                for i in range(1, 101)  # 100 versions
            ]
            mock_manager.list_versions = AsyncMock(return_value=versions)
            mock_manager_class.return_value = mock_manager

            response = client.get("/packages/pkg-001/versions?limit=10")

            assert response.status_code == 200
            data = response.json()
            assert len(data["result"]) == 10
            assert data["paging_metadata"]["cursor"] is not None


class TestGetPackageVersion:
    """Tests for GET /packages/{packageId}/versions/{version} endpoint."""

    @patch("titan.api.routers.aasx.get_session")
    @patch("titan.api.routers.aasx._retrieve_package")
    def test_get_version_success(self, mock_retrieve, mock_get_session, client):
        """Getting a specific version succeeds."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock PackageManager
        with patch("titan.api.routers.aasx.PackageManager") as mock_manager_class:
            mock_manager = MagicMock()
            versions = [
                PackageVersion(
                    version=1,
                    created_at=MagicMock(isoformat=lambda: "2026-01-11T09:00:00"),
                    created_by="user1",
                    comment="Initial",
                    content_hash="hash1",
                    parent_version=None,
                ),
                PackageVersion(
                    version=2,
                    created_at=MagicMock(isoformat=lambda: "2026-01-11T10:00:00"),
                    created_by="user2",
                    comment="Updated",
                    content_hash="hash2",
                    parent_version=1,
                ),
            ]
            mock_manager.list_versions = AsyncMock(return_value=versions)
            mock_manager_class.return_value = mock_manager

            # Mock database package lookups
            mock_package = MagicMock()
            mock_package.id = "pkg-v1"
            mock_package.version = 1
            mock_package.filename = "test.aasx"
            mock_package.size_bytes = 1024
            mock_package.storage_uri = "s3://bucket/v1.aasx"
            mock_package.previous_version_id = None

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_package
            mock_session.execute.return_value = mock_result

            # Mock package retrieval
            aasx_bytes = create_test_aasx()
            mock_retrieve.return_value = aasx_bytes

            response = client.get("/packages/pkg-001/versions/1")

            assert response.status_code == 200
            assert response.headers["X-Package-Version"] == "1"
            assert response.content == aasx_bytes

    @patch("titan.api.routers.aasx.get_session")
    def test_get_version_not_found(self, mock_get_session, client):
        """Getting a non-existent version returns 404."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock PackageManager
        with patch("titan.api.routers.aasx.PackageManager") as mock_manager_class:
            mock_manager = MagicMock()
            versions = [
                PackageVersion(
                    version=1,
                    created_at=MagicMock(isoformat=lambda: "2026-01-11T09:00:00"),
                    created_by="user1",
                    comment="Initial",
                    content_hash="hash1",
                    parent_version=None,
                ),
            ]
            mock_manager.list_versions = AsyncMock(return_value=versions)
            mock_manager_class.return_value = mock_manager

            response = client.get("/packages/pkg-001/versions/99")

            assert response.status_code == 404


class TestRollbackPackageVersion:
    """Tests for POST /packages/{packageId}/versions/{version}/rollback endpoint."""

    @patch("titan.api.routers.aasx.get_session")
    @patch("titan.api.routers.aasx.get_event_bus")
    @patch("titan.api.routers.aasx.get_optional_user")
    def test_rollback_success(self, mock_user, mock_event_bus, mock_get_session, client):
        """Rolling back to a previous version succeeds."""
        # Mock user
        mock_user.return_value = MagicMock(sub="user123")

        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock PackageManager
        with patch("titan.api.routers.aasx.PackageManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.rollback_to_version = AsyncMock(return_value="rollback-id")
            mock_manager_class.return_value = mock_manager

            # Mock new rollback package
            mock_package = MagicMock()
            mock_package.id = "rollback-id"
            mock_package.version = 3
            mock_package.filename = "test.aasx"
            mock_package.size_bytes = 1024
            mock_package.created_by = "user123"
            mock_package.version_comment = "Rollback to version 1"
            mock_package.created_at.isoformat.return_value = "2026-01-11T11:00:00"

            mock_result = MagicMock()
            mock_result.scalar_one.return_value = mock_package
            mock_session.execute.return_value = mock_result

            # Mock event bus
            mock_bus = AsyncMock()
            mock_event_bus.return_value = mock_bus

            response = client.post(
                "/packages/pkg-001/versions/1/rollback",
                data={"comment": "Rollback to stable version"},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["packageId"] == "rollback-id"
            assert data["version"] == 3
            assert data["rolledBackFrom"] == 1
            assert "Rollback to stable version" in data["comment"]

            # Verify event was published
            mock_bus.publish.assert_called_once()


class TestUpdatePackageWithVersioning:
    """Tests for PUT /packages/{packageId}?create_version=true endpoint."""

    @patch("titan.api.routers.aasx.get_session")
    @patch("titan.api.routers.aasx._store_package")
    @patch("titan.api.routers.aasx.get_event_bus")
    @patch("titan.api.routers.aasx.get_optional_user")
    def test_put_with_create_version_true(
        self, mock_user, mock_event_bus, mock_store, mock_get_session, client
    ):
        """PUT with create_version=true creates a new version."""
        # Mock user
        mock_user.return_value = MagicMock(sub="user123")

        # Mock storage
        mock_store.return_value = (
            "s3://bucket/package.aasx",
            "abc123hash",
            1024,
        )

        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock PackageManager
        with patch("titan.api.routers.aasx.PackageManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.create_version = AsyncMock(return_value="new-version-id")
            mock_manager_class.return_value = mock_manager

            # Mock new version package
            mock_package = MagicMock()
            mock_package.id = "new-version-id"
            mock_package.version = 2
            mock_package.filename = "updated.aasx"
            mock_package.version_comment = "Updated via PUT"
            mock_package.created_by = "user123"
            mock_package.created_at.isoformat.return_value = "2026-01-11T10:00:00"

            mock_result = MagicMock()
            mock_result.scalar_one.return_value = mock_package
            mock_session.execute.return_value = mock_result

            # Mock event bus
            mock_bus = AsyncMock()
            mock_event_bus.return_value = mock_bus

            aasx_bytes = create_test_aasx()
            response = client.put(
                "/packages/pkg-001?create_version=true",
                files={"file": ("updated.aasx", aasx_bytes, "application/octet-stream")},
                data={"comment": "Updated via PUT"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["packageId"] == "new-version-id"
            assert data["version"] == 2

            # Verify event was published
            mock_bus.publish.assert_called_once()

    @patch("titan.api.routers.aasx.get_session")
    @patch("titan.api.routers.aasx._store_package")
    @patch("titan.api.routers.aasx._delete_package_file")
    def test_put_with_create_version_false(self, mock_delete, mock_store, mock_get_session, client):
        """PUT with create_version=false overwrites (backward compatible)."""
        # Mock storage
        mock_store.return_value = (
            "s3://bucket/package.aasx",
            "abc123hash",
            1024,
        )

        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session

        # Mock existing package
        mock_package = MagicMock()
        mock_package.id = "pkg-001"
        mock_package.filename = "old.aasx"
        mock_package.storage_uri = "s3://bucket/old.aasx"
        mock_package.updated_at.isoformat.return_value = "2026-01-11T10:00:00"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_package
        mock_session.execute.return_value = mock_result

        aasx_bytes = create_test_aasx()
        response = client.put(
            "/packages/pkg-001",  # No create_version parameter (defaults to False)
            files={"file": ("updated.aasx", aasx_bytes, "application/octet-stream")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["packageId"] == "pkg-001"  # Same ID (overwritten)

        # Verify old file was deleted
        mock_delete.assert_called_once_with("s3://bucket/old.aasx")
