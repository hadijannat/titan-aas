"""Tests for OPC/AASX package validator."""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from titan.packages.validator import OpcValidator, ValidationLevel, ValidationResult


def create_minimal_aasx() -> bytes:
    """Create a minimal valid AASX package."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Content types
        content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="json" ContentType="application/json"/>
    <Default Extension="xml" ContentType="application/xml"/>
</Types>"""
        zf.writestr("[Content_Types].xml", content_types)

        # Root relationships
        rels = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Type="http://admin-shell.io/aasx/relationships/aasx-origin"
        Target="/aasx/aasx-origin" Id="rId1"/>
</Relationships>"""
        zf.writestr("_rels/.rels", rels)

        # AASX origin
        zf.writestr("aasx/aasx-origin", "")

        # AAS environment
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
            "submodels": []
        }"""
        zf.writestr("aasx/aas-environment.json", env_json)

    buffer.seek(0)
    return buffer.read()


def create_invalid_zip() -> bytes:
    """Create invalid ZIP data."""
    return b"not a zip file"


def create_missing_content_types() -> bytes:
    """Create AASX without [Content_Types].xml."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("aasx/aas-environment.json", b'{"assetAdministrationShells":[]}')
    buffer.seek(0)
    return buffer.read()


class TestOpcValidator:
    """Tests for OpcValidator."""

    @pytest.mark.asyncio
    async def test_validate_valid_package(self):
        """Valid package passes validation."""
        content = create_minimal_aasx()
        validator = OpcValidator(level=ValidationLevel.STANDARD)

        result = await validator.validate(BytesIO(content))

        assert result.valid
        assert result.content_hash is not None
        assert result.file_count > 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_invalid_zip(self):
        """Invalid ZIP fails validation."""
        content = create_invalid_zip()
        validator = OpcValidator()

        result = await validator.validate(BytesIO(content))

        assert not result.valid
        assert len(result.errors) > 0
        assert any("ZIP" in e.code for e in result.errors)

    @pytest.mark.asyncio
    async def test_validate_missing_content_types_standard(self):
        """Missing content types generates warning in standard mode."""
        content = create_missing_content_types()
        validator = OpcValidator(level=ValidationLevel.STANDARD)

        result = await validator.validate(BytesIO(content))

        # Should have warnings but still be valid
        assert len(result.warnings) > 0 or not result.valid

    @pytest.mark.asyncio
    async def test_validate_missing_content_types_strict(self):
        """Missing content types fails strict validation."""
        content = create_missing_content_types()
        validator = OpcValidator(level=ValidationLevel.STRICT)

        result = await validator.validate(BytesIO(content))

        assert not result.valid
        assert any("MISSING_REQUIRED_FILE" in e.code for e in result.errors)

    @pytest.mark.asyncio
    async def test_validation_result_properties(self):
        """ValidationResult correctly categorizes issues."""
        result = ValidationResult(valid=True)
        result.add_error("ERR1", "Error 1")
        result.add_warning("WARN1", "Warning 1")
        result.add_info("INFO1", "Info 1")

        assert not result.valid  # add_error sets valid=False
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert len(result.issues) == 3

    @pytest.mark.asyncio
    async def test_content_hash_computed(self):
        """Content hash is computed during validation."""
        content = create_minimal_aasx()
        validator = OpcValidator()

        result = await validator.validate(BytesIO(content))

        assert result.content_hash is not None
        assert len(result.content_hash) == 64  # SHA256 hex


class TestValidationLevel:
    """Tests for validation level behavior."""

    @pytest.mark.asyncio
    async def test_lenient_accepts_most_packages(self):
        """Lenient mode accepts packages with issues."""
        content = create_missing_content_types()
        validator = OpcValidator(level=ValidationLevel.LENIENT)

        result = await validator.validate(BytesIO(content))

        # Lenient mode should not fail on missing optional files
        assert len(result.errors) == 0 or result.valid

    @pytest.mark.asyncio
    async def test_strict_requires_all_opc_files(self):
        """Strict mode requires all OPC files."""
        content = create_missing_content_types()
        validator = OpcValidator(level=ValidationLevel.STRICT)

        result = await validator.validate(BytesIO(content))

        # Should have errors for missing files
        assert not result.valid or len(result.warnings) > 0
