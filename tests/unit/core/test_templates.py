"""Unit tests for template instantiation (SSP-003/004 profiles)."""

from __future__ import annotations

import pytest

from titan.core.templates import (
    InstantiationRequest,
    InstantiationResult,
    TemplateInstantiator,
    instantiate_template,
)


@pytest.fixture
def template_doc() -> dict:
    """Create a sample template submodel document."""
    return {
        "id": "urn:template:motor:v1",
        "idShort": "MotorTemplate",
        "kind": "Template",
        "semanticId": {
            "type": "ExternalReference",
            "keys": [{"type": "GlobalReference", "value": "urn:semantic:motor"}],
        },
        "submodelElements": [
            {
                "modelType": "Property",
                "idShort": "MaxSpeed",
                "valueType": "xs:int",
                "value": None,
            },
            {
                "modelType": "Property",
                "idShort": "SerialNumber",
                "valueType": "xs:string",
                "value": None,
            },
            {
                "modelType": "SubmodelElementCollection",
                "idShort": "TechnicalData",
                "value": [
                    {
                        "modelType": "Property",
                        "idShort": "Power",
                        "valueType": "xs:double",
                        "value": None,
                    },
                    {
                        "modelType": "Property",
                        "idShort": "Voltage",
                        "valueType": "xs:double",
                        "value": None,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def instance_doc() -> dict:
    """Create a sample instance submodel document (not a template)."""
    return {
        "id": "urn:instance:motor:001",
        "idShort": "Motor001",
        "kind": "Instance",
        "submodelElements": [
            {
                "modelType": "Property",
                "idShort": "Speed",
                "valueType": "xs:int",
                "value": "1500",
            },
        ],
    }


class TestInstantiationRequest:
    """Tests for InstantiationRequest dataclass."""

    def test_minimal_request(self):
        """Test creating a minimal instantiation request."""
        request = InstantiationRequest(new_id="urn:new:submodel")
        assert request.new_id == "urn:new:submodel"
        assert request.id_short is None
        assert request.value_overrides == {}
        assert request.copy_semantic_id is True

    def test_full_request(self):
        """Test creating a full instantiation request."""
        overrides = {"MaxSpeed": 3000, "SerialNumber": "SN12345"}
        request = InstantiationRequest(
            new_id="urn:new:submodel",
            id_short="MyInstance",
            value_overrides=overrides,
            copy_semantic_id=False,
        )
        assert request.new_id == "urn:new:submodel"
        assert request.id_short == "MyInstance"
        assert request.value_overrides == overrides
        assert request.copy_semantic_id is False


class TestTemplateInstantiator:
    """Tests for TemplateInstantiator class."""

    def test_instantiate_basic(self, template_doc: dict):
        """Test basic template instantiation."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(new_id="urn:instance:motor:001")

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.error is None
        assert result.submodel_doc is not None
        assert result.submodel_doc["id"] == "urn:instance:motor:001"
        assert result.submodel_doc["kind"] == "Instance"
        # Original template should be unchanged
        assert template_doc["kind"] == "Template"

    def test_instantiate_with_id_short_override(self, template_doc: dict):
        """Test instantiation with idShort override."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:motor:001", id_short="Motor001"
        )

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.submodel_doc is not None
        assert result.submodel_doc["idShort"] == "Motor001"

    def test_instantiate_preserves_semantic_id(self, template_doc: dict):
        """Test that semanticId is preserved by default."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:motor:001", copy_semantic_id=True
        )

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.submodel_doc is not None
        assert "semanticId" in result.submodel_doc
        assert result.submodel_doc["semanticId"]["keys"][0]["value"] == "urn:semantic:motor"

    def test_instantiate_removes_semantic_id(self, template_doc: dict):
        """Test that semanticId can be removed during instantiation."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:motor:001", copy_semantic_id=False
        )

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.submodel_doc is not None
        assert "semanticId" not in result.submodel_doc

    def test_instantiate_with_value_overrides(self, template_doc: dict):
        """Test instantiation with value overrides."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:motor:001",
            value_overrides={"MaxSpeed": 3000, "SerialNumber": "SN12345"},
        )

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.submodel_doc is not None

        # Check that values were set
        elements = result.submodel_doc["submodelElements"]
        max_speed = next(e for e in elements if e["idShort"] == "MaxSpeed")
        serial = next(e for e in elements if e["idShort"] == "SerialNumber")

        assert max_speed["value"] == 3000
        assert serial["value"] == "SN12345"

    def test_instantiate_with_nested_value_overrides(self, template_doc: dict):
        """Test instantiation with nested value overrides."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:motor:001",
            value_overrides={"TechnicalData.Power": 750.0, "TechnicalData.Voltage": 380.0},
        )

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.submodel_doc is not None

        # Navigate to nested elements
        elements = result.submodel_doc["submodelElements"]
        tech_data = next(e for e in elements if e["idShort"] == "TechnicalData")
        power = next(e for e in tech_data["value"] if e["idShort"] == "Power")
        voltage = next(e for e in tech_data["value"] if e["idShort"] == "Voltage")

        assert power["value"] == 750.0
        assert voltage["value"] == 380.0

    def test_instantiate_fails_for_non_template(self, instance_doc: dict):
        """Test that instantiation fails for non-template submodels."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(new_id="urn:new:instance")

        result = instantiator.instantiate(instance_doc, request)

        assert result.success is False
        assert "not a template" in result.error.lower()
        assert result.submodel_doc is None

    def test_instantiate_ignores_nonexistent_path(self, template_doc: dict):
        """Test that non-existent paths in overrides are silently ignored."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:motor:001",
            value_overrides={"NonExistent": "value", "MaxSpeed": 3000},
        )

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.submodel_doc is not None

        # Existing path should still work
        elements = result.submodel_doc["submodelElements"]
        max_speed = next(e for e in elements if e["idShort"] == "MaxSpeed")
        assert max_speed["value"] == 3000


class TestPathParsing:
    """Tests for path parsing functionality."""

    def test_parse_simple_path(self):
        """Test parsing a simple path."""
        instantiator = TemplateInstantiator()
        result = instantiator._parse_path("Property")
        assert result == [("Property", None)]

    def test_parse_dotted_path(self):
        """Test parsing a dotted path."""
        instantiator = TemplateInstantiator()
        result = instantiator._parse_path("Collection.Property")
        assert result == [("Collection", None), ("Property", None)]

    def test_parse_path_with_index(self):
        """Test parsing a path with list index."""
        instantiator = TemplateInstantiator()
        result = instantiator._parse_path("List[0]")
        assert result == [("List", 0)]

    def test_parse_complex_path(self):
        """Test parsing a complex path."""
        instantiator = TemplateInstantiator()
        result = instantiator._parse_path("Collection.List[2].Property")
        assert result == [("Collection", None), ("List", 2), ("Property", None)]

    def test_parse_empty_path(self):
        """Test parsing an empty path."""
        instantiator = TemplateInstantiator()
        result = instantiator._parse_path("")
        assert result == []


class TestModuleLevelFunction:
    """Tests for the module-level instantiate_template function."""

    def test_instantiate_template_function(self, template_doc: dict):
        """Test the module-level instantiate_template function."""
        request = InstantiationRequest(new_id="urn:instance:motor:001")
        result = instantiate_template(template_doc, request)

        assert isinstance(result, InstantiationResult)
        assert result.success is True
        assert result.submodel_doc is not None
        assert result.submodel_doc["kind"] == "Instance"


class TestDeepCopyBehavior:
    """Tests verifying that template instantiation uses deep copies."""

    def test_original_template_unchanged(self, template_doc: dict):
        """Test that the original template is not modified."""
        instantiator = TemplateInstantiator()
        original_id = template_doc["id"]
        original_kind = template_doc["kind"]

        request = InstantiationRequest(
            new_id="urn:instance:motor:001",
            value_overrides={"MaxSpeed": 3000},
        )
        result = instantiator.instantiate(template_doc, request)

        # Original should be unchanged
        assert template_doc["id"] == original_id
        assert template_doc["kind"] == original_kind

        # Instance should have new values
        assert result.submodel_doc is not None
        assert result.submodel_doc["id"] == "urn:instance:motor:001"
        assert result.submodel_doc["kind"] == "Instance"

    def test_nested_elements_independently_modified(self, template_doc: dict):
        """Test that modifying nested elements doesn't affect template."""
        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:motor:001",
            value_overrides={"TechnicalData.Power": 750.0},
        )
        result = instantiator.instantiate(template_doc, request)

        # Modify the instance result
        result.submodel_doc["submodelElements"][0]["value"] = "MODIFIED"

        # Template should be unchanged
        original_elements = template_doc["submodelElements"]
        assert original_elements[0]["value"] is None


class TestListElementHandling:
    """Tests for SubmodelElementList handling in templates."""

    def test_instantiate_with_list_elements(self):
        """Test instantiation of template with SubmodelElementList."""
        template_doc = {
            "id": "urn:template:sensors:v1",
            "idShort": "SensorsTemplate",
            "kind": "Template",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "Sensors",
                    "typeValueListElement": "Property",
                    "value": [
                        {
                            "modelType": "Property",
                            "idShort": "Sensor0",
                            "valueType": "xs:double",
                            "value": None,
                        },
                        {
                            "modelType": "Property",
                            "idShort": "Sensor1",
                            "valueType": "xs:double",
                            "value": None,
                        },
                    ],
                },
            ],
        }

        instantiator = TemplateInstantiator()
        request = InstantiationRequest(
            new_id="urn:instance:sensors:001",
            value_overrides={"Sensors[0]": 25.5, "Sensors[1]": 30.2},
        )

        result = instantiator.instantiate(template_doc, request)

        assert result.success is True
        assert result.submodel_doc is not None

        # Check list elements were updated
        sensors = result.submodel_doc["submodelElements"][0]
        assert sensors["value"][0]["value"] == 25.5
        assert sensors["value"][1]["value"] == 30.2
