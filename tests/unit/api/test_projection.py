"""Tests for IDTA projection modifiers."""

from titan.core.projection import (
    ProjectionModifiers,
    apply_projection,
    extract_value,
    navigate_id_short_path,
)


class TestProjectionModifiers:
    """Test ProjectionModifiers class."""

    def test_defaults(self) -> None:
        """Default modifiers are deep, withBlobValue, normal."""
        mods = ProjectionModifiers()
        assert mods.level == "deep"
        assert mods.extent == "withBlobValue"
        assert mods.content == "normal"
        assert mods.is_deep is True
        assert mods.is_core is False
        assert mods.include_blob_value is True

    def test_core_level(self) -> None:
        """Core level modifier."""
        mods = ProjectionModifiers(level="core")
        assert mods.is_core is True
        assert mods.is_deep is False

    def test_without_blob_value(self) -> None:
        """withoutBlobValue extent modifier."""
        mods = ProjectionModifiers(extent="withoutBlobValue")
        assert mods.include_blob_value is False

    def test_metadata_content(self) -> None:
        """Metadata content modifier."""
        mods = ProjectionModifiers(content="metadata")
        assert mods.content == "metadata"


class TestApplyProjection:
    """Test apply_projection function."""

    def test_no_modifiers_returns_original(self) -> None:
        """No modifiers returns payload unchanged."""
        payload = {"idShort": "test", "value": "123"}
        result = apply_projection(payload, None)
        assert result == payload

    def test_metadata_projection_strips_values(self) -> None:
        """Metadata projection removes value fields."""
        payload = {
            "modelType": "Property",
            "idShort": "temperature",
            "semanticId": {"type": "ExternalReference", "keys": []},
            "value": "25.5",
            "valueType": "xs:double",
        }
        mods = ProjectionModifiers(content="metadata")
        result = apply_projection(payload, mods)

        assert "idShort" in result
        assert "semanticId" in result
        assert "modelType" in result
        assert "value" not in result
        assert "valueType" not in result

    def test_value_projection_strips_metadata(self) -> None:
        """Value projection removes metadata fields."""
        payload = {
            "modelType": "Property",
            "idShort": "temperature",
            "semanticId": {"type": "ExternalReference", "keys": []},
            "value": "25.5",
            "valueType": "xs:double",
        }
        mods = ProjectionModifiers(content="value")
        result = apply_projection(payload, mods)

        assert "value" in result
        assert "valueType" in result
        assert "modelType" in result
        assert "idShort" not in result
        assert "semanticId" not in result

    def test_core_level_removes_nested(self) -> None:
        """Core level removes nested submodelElements."""
        payload = {
            "modelType": "Submodel",
            "id": "urn:example:submodel:1",
            "idShort": "Test",
            "submodelElements": [
                {"modelType": "Property", "idShort": "p1"},
            ],
        }
        mods = ProjectionModifiers(level="core")
        result = apply_projection(payload, mods)

        assert "id" in result
        assert "idShort" in result
        assert "submodelElements" not in result

    def test_without_blob_value_strips_blob(self) -> None:
        """withoutBlobValue strips Blob values."""
        payload = {
            "modelType": "Blob",
            "idShort": "thumbnail",
            "contentType": "image/png",
            "value": "base64encoded...",
        }
        mods = ProjectionModifiers(extent="withoutBlobValue")
        result = apply_projection(payload, mods)

        assert "idShort" in result
        assert "contentType" in result
        assert "value" not in result

    def test_nested_collection_projection(self) -> None:
        """Projection applies to nested collections."""
        payload = {
            "modelType": "SubmodelElementCollection",
            "idShort": "address",
            "value": [
                {
                    "modelType": "Property",
                    "idShort": "street",
                    "value": "Main St",
                    "valueType": "xs:string",
                    "semanticId": {"type": "ExternalReference", "keys": []},
                },
            ],
        }
        mods = ProjectionModifiers(content="value")
        result = apply_projection(payload, mods)

        assert "value" in result
        nested = result["value"][0]
        assert "value" in nested
        assert "valueType" in nested
        assert "semanticId" not in nested


class TestNavigateIdShortPath:
    """Test navigate_id_short_path function."""

    def test_empty_path_returns_root(self) -> None:
        """Empty path returns the payload itself."""
        payload = {"idShort": "test"}
        result = navigate_id_short_path(payload, "")
        assert result == payload

    def test_single_element(self) -> None:
        """Navigate to single element by idShort."""
        payload = {
            "submodelElements": [
                {"idShort": "temperature", "value": "25"},
                {"idShort": "humidity", "value": "60"},
            ]
        }
        result = navigate_id_short_path(payload, "temperature")
        assert result is not None
        assert result["idShort"] == "temperature"

    def test_nested_path(self) -> None:
        """Navigate nested path with dots."""
        payload = {
            "submodelElements": [
                {
                    "idShort": "address",
                    "value": [
                        {"idShort": "street", "value": "Main St"},
                        {"idShort": "city", "value": "Boston"},
                    ],
                }
            ]
        }
        result = navigate_id_short_path(payload, "address.city")
        assert result is not None
        assert result["idShort"] == "city"
        assert result["value"] == "Boston"

    def test_index_navigation(self) -> None:
        """Navigate to element by index."""
        payload = {
            "submodelElements": [
                {
                    "idShort": "measurements",
                    "value": [
                        {"idShort": "m0", "value": "1.0"},
                        {"idShort": "m1", "value": "2.0"},
                        {"idShort": "m2", "value": "3.0"},
                    ],
                }
            ]
        }
        result = navigate_id_short_path(payload, "measurements[1]")
        assert result is not None
        assert result["idShort"] == "m1"

    def test_not_found_returns_none(self) -> None:
        """Missing element returns None."""
        payload = {"submodelElements": [{"idShort": "exists"}]}
        result = navigate_id_short_path(payload, "missing")
        assert result is None

    def test_index_out_of_bounds(self) -> None:
        """Out of bounds index returns None."""
        payload = {"submodelElements": [{"idShort": "list", "value": [{"idShort": "aa"}]}]}
        result = navigate_id_short_path(payload, "list[99]")
        assert result is None


class TestExtractValue:
    """Test extract_value function."""

    def test_property_value(self) -> None:
        """Extract value from Property."""
        element = {"modelType": "Property", "value": "25.5"}
        assert extract_value(element) == "25.5"

    def test_range_value(self) -> None:
        """Extract value from Range."""
        element = {"modelType": "Range", "min": "-40", "max": "85"}
        result = extract_value(element)
        assert result == {"min": "-40", "max": "85"}

    def test_collection_value(self) -> None:
        """Extract value from SubmodelElementCollection."""
        element = {
            "modelType": "SubmodelElementCollection",
            "value": [
                {"modelType": "Property", "value": "a"},
                {"modelType": "Property", "value": "b"},
            ],
        }
        result = extract_value(element)
        assert result == ["a", "b"]

    def test_entity_value(self) -> None:
        """Extract value from Entity."""
        element = {
            "modelType": "Entity",
            "entityType": "SelfManagedEntity",
            "globalAssetId": "urn:example:asset:1",
        }
        result = extract_value(element)
        assert result["entityType"] == "SelfManagedEntity"
        assert result["globalAssetId"] == "urn:example:asset:1"

    def test_unknown_type_returns_none(self) -> None:
        """Unknown modelType returns None."""
        element = {"modelType": "UnknownType", "value": "test"}
        assert extract_value(element) is None
