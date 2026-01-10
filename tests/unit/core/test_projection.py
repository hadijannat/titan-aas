"""Tests for IDTA projection modifiers.

Tests the $metadata, $reference, $path, and $value projections
per IDTA-01002 Part 2.
"""

from __future__ import annotations

from titan.core.projection import (
    ProjectionModifiers,
    apply_projection,
    extract_metadata,
    extract_path,
    extract_reference,
    extract_reference_for_aas,
    extract_value,
    navigate_id_short_path,
)


class TestExtractValue:
    """Tests for $value extraction."""

    def test_extract_property_value(self) -> None:
        """Extract value from Property element."""
        element = {
            "modelType": "Property",
            "idShort": "Temperature",
            "valueType": "xs:double",
            "value": "25.5",
        }
        assert extract_value(element) == "25.5"

    def test_extract_range_value(self) -> None:
        """Extract value from Range element."""
        element = {
            "modelType": "Range",
            "idShort": "TemperatureRange",
            "valueType": "xs:double",
            "min": "10.0",
            "max": "50.0",
        }
        result = extract_value(element)
        assert result == {"min": "10.0", "max": "50.0"}

    def test_extract_collection_value(self) -> None:
        """Extract nested values from SubmodelElementCollection."""
        element = {
            "modelType": "SubmodelElementCollection",
            "idShort": "Measurements",
            "value": [
                {"modelType": "Property", "idShort": "Temp", "value": "25"},
                {"modelType": "Property", "idShort": "Pressure", "value": "101.3"},
            ],
        }
        result = extract_value(element)
        assert result == ["25", "101.3"]

    def test_extract_entity_value(self) -> None:
        """Extract value from Entity element."""
        element = {
            "modelType": "Entity",
            "idShort": "Motor",
            "entityType": "SelfManagedEntity",
            "globalAssetId": "urn:example:asset:motor-001",
        }
        result = extract_value(element)
        assert result["entityType"] == "SelfManagedEntity"
        assert result["globalAssetId"] == "urn:example:asset:motor-001"


class TestExtractMetadata:
    """Tests for $metadata extraction."""

    def test_extract_property_metadata(self) -> None:
        """Extract metadata from Property element (no value)."""
        element = {
            "modelType": "Property",
            "idShort": "Temperature",
            "valueType": "xs:double",
            "value": "25.5",
            "semanticId": {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": "0173-1#02-AAB994#007"}],
            },
        }
        result = extract_metadata(element)

        assert result["modelType"] == "Property"
        assert result["idShort"] == "Temperature"
        assert result["semanticId"]["type"] == "ExternalReference"
        assert "value" not in result
        assert "valueType" not in result

    def test_extract_collection_metadata(self) -> None:
        """Extract metadata recursively from collection."""
        element = {
            "modelType": "SubmodelElementCollection",
            "idShort": "Measurements",
            "value": [
                {
                    "modelType": "Property",
                    "idShort": "Temp",
                    "value": "25",
                    "valueType": "xs:double",
                },
            ],
        }
        result = extract_metadata(element)

        assert result["modelType"] == "SubmodelElementCollection"
        assert result["idShort"] == "Measurements"
        assert len(result["value"]) == 1
        assert result["value"][0]["modelType"] == "Property"
        assert result["value"][0]["idShort"] == "Temp"
        assert "value" not in result["value"][0] or result["value"][0].get("value") == []

    def test_extract_submodel_metadata(self) -> None:
        """Extract metadata from Submodel (preserves id, kind)."""
        doc = {
            "id": "urn:example:submodel:tech-data",
            "idShort": "TechnicalData",
            "kind": "Instance",
            "semanticId": {
                "type": "ExternalReference",
                "keys": [
                    {
                        "type": "GlobalReference",
                        "value": "https://admin-shell.io/ZVEI/TechnicalData/1/2",
                    }
                ],
            },
            "submodelElements": [
                {
                    "modelType": "Property",
                    "idShort": "MaxPayload",
                    "value": "16.0",
                },
            ],
        }
        result = extract_metadata(doc)

        assert result["id"] == "urn:example:submodel:tech-data"
        assert result["idShort"] == "TechnicalData"
        assert result["kind"] == "Instance"
        assert len(result["submodelElements"]) == 1
        assert result["submodelElements"][0]["idShort"] == "MaxPayload"


class TestExtractReference:
    """Tests for $reference extraction."""

    def test_extract_element_reference(self) -> None:
        """Extract reference for a SubmodelElement."""
        element = {
            "modelType": "Property",
            "idShort": "Temperature",
            "value": "25.5",
        }
        result = extract_reference(
            element,
            submodel_id="urn:example:submodel:001",
            id_short_path="Temperature",
        )

        assert result["type"] == "ModelReference"
        assert len(result["keys"]) == 2
        assert result["keys"][0] == {"type": "Submodel", "value": "urn:example:submodel:001"}
        assert result["keys"][1] == {"type": "Property", "value": "Temperature"}

    def test_extract_nested_element_reference(self) -> None:
        """Extract reference for nested element with dot path."""
        element = {
            "modelType": "Property",
            "idShort": "SerialNumber",
            "value": "ABC-123",
        }
        result = extract_reference(
            element,
            submodel_id="urn:example:submodel:nameplate",
            id_short_path="Identification.SerialNumber",
        )

        assert result["type"] == "ModelReference"
        assert result["keys"][0]["value"] == "urn:example:submodel:nameplate"
        assert result["keys"][1]["value"] == "Identification.SerialNumber"

    def test_extract_submodel_reference(self) -> None:
        """Extract reference for Submodel itself (no id_short_path)."""
        element = {
            "id": "urn:example:submodel:001",
            "idShort": "TechnicalData",
        }
        result = extract_reference(element, submodel_id="urn:example:submodel:001")

        assert result["type"] == "ModelReference"
        assert len(result["keys"]) == 1
        assert result["keys"][0] == {"type": "Submodel", "value": "urn:example:submodel:001"}


class TestExtractReferenceForAas:
    """Tests for AAS $reference extraction."""

    def test_extract_aas_reference(self) -> None:
        """Extract reference for an AAS."""
        aas = {
            "id": "urn:example:aas:robot-001",
            "idShort": "RobotArm",
            "assetInformation": {"assetKind": "Instance"},
        }
        result = extract_reference_for_aas(aas)

        assert result["type"] == "ModelReference"
        assert len(result["keys"]) == 1
        assert result["keys"][0] == {
            "type": "AssetAdministrationShell",
            "value": "urn:example:aas:robot-001",
        }


class TestExtractPath:
    """Tests for $path extraction."""

    def test_extract_simple_path(self) -> None:
        """Extract path for simple element."""
        element = {
            "modelType": "Property",
            "idShort": "Temperature",
        }
        result = extract_path(element, "Temperature")

        assert result == {"idShortPath": "Temperature"}

    def test_extract_nested_path(self) -> None:
        """Extract path for nested element."""
        element = {
            "modelType": "Property",
            "idShort": "SerialNumber",
        }
        result = extract_path(element, "Identification.SerialNumber")

        assert result == {"idShortPath": "Identification.SerialNumber"}

    def test_extract_indexed_path(self) -> None:
        """Extract path with index notation."""
        element = {
            "modelType": "Property",
            "idShort": "Value",
        }
        result = extract_path(element, "Measurements[0].Value")

        assert result == {"idShortPath": "Measurements[0].Value"}


class TestNavigateIdShortPath:
    """Tests for idShortPath navigation."""

    def test_navigate_simple_path(self) -> None:
        """Navigate to top-level element."""
        doc = {
            "submodelElements": [
                {"modelType": "Property", "idShort": "Temperature", "value": "25"},
                {"modelType": "Property", "idShort": "Pressure", "value": "101"},
            ]
        }
        result = navigate_id_short_path(doc, "Temperature")

        assert result is not None
        assert result["idShort"] == "Temperature"
        assert result["value"] == "25"

    def test_navigate_nested_path(self) -> None:
        """Navigate to nested element via dot notation."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Identification",
                    "value": [
                        {"modelType": "Property", "idShort": "SerialNumber", "value": "ABC-123"},
                    ],
                }
            ]
        }
        result = navigate_id_short_path(doc, "Identification.SerialNumber")

        assert result is not None
        assert result["idShort"] == "SerialNumber"
        assert result["value"] == "ABC-123"

    def test_navigate_indexed_path(self) -> None:
        """Navigate using index notation."""
        doc = {
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "Measurements",
                    "value": [
                        {"modelType": "Property", "idShort": "V1", "value": "10"},
                        {"modelType": "Property", "idShort": "V2", "value": "20"},
                    ],
                }
            ]
        }
        result = navigate_id_short_path(doc, "Measurements[1]")

        assert result is not None
        assert result["idShort"] == "V2"
        assert result["value"] == "20"

    def test_navigate_not_found(self) -> None:
        """Return None for non-existent path."""
        doc = {"submodelElements": []}
        result = navigate_id_short_path(doc, "NonExistent")

        assert result is None


class TestProjectionModifiers:
    """Tests for ProjectionModifiers class."""

    def test_default_modifiers(self) -> None:
        """Default modifiers are deep, withBlobValue, normal."""
        mods = ProjectionModifiers()

        assert mods.level == "deep"
        assert mods.extent == "withBlobValue"
        assert mods.content == "normal"
        assert mods.is_deep is True
        assert mods.is_core is False
        assert mods.include_blob_value is True

    def test_core_level(self) -> None:
        """Core level strips nested elements."""
        mods = ProjectionModifiers(level="core")

        assert mods.is_core is True
        assert mods.is_deep is False

    def test_without_blob_value(self) -> None:
        """Extent modifier controls blob inclusion."""
        mods = ProjectionModifiers(extent="withoutBlobValue")

        assert mods.include_blob_value is False


class TestApplyProjection:
    """Tests for apply_projection function."""

    def test_core_level_strips_nested(self) -> None:
        """Core level removes submodelElements."""
        payload = {
            "id": "urn:example:submodel:001",
            "idShort": "Test",
            "submodelElements": [
                {"modelType": "Property", "idShort": "P1"},
            ],
        }
        mods = ProjectionModifiers(level="core")
        result = apply_projection(payload, mods)

        assert "id" in result
        assert "idShort" in result
        assert "submodelElements" not in result

    def test_without_blob_value(self) -> None:
        """WithoutBlobValue strips blob values."""
        payload = {
            "submodelElements": [
                {"modelType": "Blob", "idShort": "Image", "value": "base64data"},
                {"modelType": "Property", "idShort": "Name", "value": "test"},
            ],
        }
        mods = ProjectionModifiers(extent="withoutBlobValue")
        result = apply_projection(payload, mods)

        # Blob value should be stripped
        blob = result["submodelElements"][0]
        assert "value" not in blob
        # Property value should remain
        prop = result["submodelElements"][1]
        assert prop["value"] == "test"

    def test_none_modifiers_returns_original(self) -> None:
        """None modifiers returns unchanged payload."""
        payload = {"id": "test", "value": "123"}
        result = apply_projection(payload, None)

        assert result == payload
