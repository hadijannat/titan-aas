"""Tests for AASX package versioning functionality."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from titan.packages.manager import PackageManager, PackageVersion
from titan.persistence.tables import AasxPackageTable


class TestPackageVersioning:
    """Test package versioning functionality."""

    async def test_create_version(self) -> None:
        """Test creating a new version of a package."""
        manager = PackageManager()

        # Mock session and current package
        session = AsyncMock()
        current_pkg = AasxPackageTable(
            id="pkg-001",
            filename="test-v1.aasx",
            storage_uri="blob://test/v1",
            size_bytes=1024,
            content_hash="abc123",
            version=1,
            shell_count=2,
            submodel_count=3,
            concept_description_count=1,
            package_info={"test": "data"},
        )

        # Mock the SELECT query
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = current_pkg
        session.execute.return_value = mock_result

        new_content = b"updated content"
        await manager.create_version(
            session=session,
            package_id="pkg-001",
            new_content=new_content,
            filename="test-v2.aasx",
            storage_uri="blob://test/v2",
            created_by="test-user",
            comment="Updated shells",
        )

        # Verify new version was created with correct parameters
        session.add.assert_called_once()
        new_package = session.add.call_args[0][0]
        assert isinstance(new_package, AasxPackageTable)
        assert new_package.version == 2
        assert new_package.previous_version_id == "pkg-001"
        assert new_package.version_comment == "Updated shells"
        assert new_package.created_by == "test-user"
        assert new_package.filename == "test-v2.aasx"

        session.commit.assert_called_once()

    async def test_create_version_not_found(self) -> None:
        """Test creating version of non-existent package."""
        manager = PackageManager()

        session = AsyncMock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Package not found"):
            await manager.create_version(
                session=session,
                package_id="nonexistent",
                new_content=b"content",
                filename="test.aasx",
                storage_uri="blob://test",
            )

    async def test_list_versions_single(self) -> None:
        """Test listing versions with single version."""
        manager = PackageManager()

        session = AsyncMock()
        pkg = AasxPackageTable(
            id="pkg-001",
            filename="test.aasx",
            storage_uri="blob://test",
            size_bytes=1024,
            content_hash="abc123",
            version=1,
            previous_version_id=None,
            version_comment="Initial version",
            created_by="user1",
            created_at=datetime(2026, 1, 1),
            shell_count=0,
            submodel_count=0,
            concept_description_count=0,
            package_info={},
        )

        # Mock finding root (no previous version)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = pkg
        session.execute.return_value = mock_result

        # For forward traversal, return None for next version
        def execute_side_effect(*args):
            result = Mock()
            if "previous_version_id =" in str(args[0]):
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = pkg
            return result

        session.execute.side_effect = execute_side_effect

        versions = await manager.list_versions(session, "pkg-001")

        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].content_hash == "abc123"
        assert versions[0].parent_version is None

    async def test_rollback_validation(self) -> None:
        """Test rollback validation with non-existent version."""
        manager = PackageManager()

        session = AsyncMock()

        # Mock list_versions to return empty list
        manager.list_versions = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="No versions found"):
            await manager.rollback_to_version(
                session=session, package_id="pkg-001", target_version=1
            )

    async def test_rollback_invalid_version(self) -> None:
        """Test rollback to non-existent version number."""
        manager = PackageManager()

        session = AsyncMock()

        # Mock list_versions to return v1 and v2
        manager.list_versions = AsyncMock(
            return_value=[
                PackageVersion(version=1, created_at=datetime.now()),
                PackageVersion(version=2, created_at=datetime.now()),
            ]
        )

        with pytest.raises(ValueError, match="Version 99 not found"):
            await manager.rollback_to_version(
                session=session, package_id="pkg-001", target_version=99
            )

    async def test_version_increment_logic(self) -> None:
        """Test that version numbers increment correctly."""
        manager = PackageManager()

        session = AsyncMock()
        v1 = AasxPackageTable(
            id="pkg-001",
            filename="v1.aasx",
            storage_uri="blob://v1",
            size_bytes=100,
            content_hash="hash1",
            version=1,
            previous_version_id=None,
            shell_count=0,
            submodel_count=0,
            concept_description_count=0,
            package_info={},
        )

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = v1
        session.execute.return_value = mock_result

        # Create v2
        new_id = await manager.create_version(
            session=session,
            package_id="pkg-001",
            new_content=b"v2",
            filename="v2.aasx",
            storage_uri="blob://v2",
        )

        # Verify version incremented to 2
        new_package = session.add.call_args[0][0]
        assert new_package.version == 2

        # Now mock v2 as current and create v3
        v2 = AasxPackageTable(
            id=new_id,
            filename="v2.aasx",
            storage_uri="blob://v2",
            size_bytes=100,
            content_hash="hash2",
            version=2,
            previous_version_id="pkg-001",
            shell_count=0,
            submodel_count=0,
            concept_description_count=0,
            package_info={},
        )

        mock_result2 = Mock()
        mock_result2.scalar_one_or_none.return_value = v2
        session.execute.return_value = mock_result2

        await manager.create_version(
            session=session,
            package_id=new_id,
            new_content=b"v3",
            filename="v3.aasx",
            storage_uri="blob://v3",
        )

        # Verify version incremented to 3
        new_package_v3 = session.add.call_args[0][0]
        assert new_package_v3.version == 3

    async def test_version_metadata_preservation(self) -> None:
        """Test that package metadata is preserved in versions."""
        manager = PackageManager()

        session = AsyncMock()
        original = AasxPackageTable(
            id="pkg-001",
            filename="original.aasx",
            storage_uri="blob://original",
            size_bytes=1024,
            content_hash="hash1",
            version=1,
            shell_count=5,
            submodel_count=10,
            concept_description_count=3,
            package_info={"key": "value"},
        )

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = original
        session.execute.return_value = mock_result

        await manager.create_version(
            session=session,
            package_id="pkg-001",
            new_content=b"new",
            filename="new.aasx",
            storage_uri="blob://new",
            created_by="alice",
            comment="Updated",
        )

        # Verify metadata was preserved
        new_package = session.add.call_args[0][0]
        assert new_package.shell_count == 5
        assert new_package.submodel_count == 10
        assert new_package.concept_description_count == 3
        assert new_package.package_info == {"key": "value"}

        # Verify version-specific fields are new
        assert new_package.created_by == "alice"
        assert new_package.version_comment == "Updated"
        assert new_package.version == 2
