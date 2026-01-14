"""Unit tests for template instantiation API models and logic."""

from __future__ import annotations

import pytest

from titan.api.routers.submodel_repository import InstantiateTemplateRequest


class TestInstantiateTemplateRequestModel:
    """Tests for InstantiateTemplateRequest Pydantic model."""

    def test_minimal_request(self):
        """Test minimal request with only required fields."""
        request = InstantiateTemplateRequest(new_id="urn:test:id")
        assert request.new_id == "urn:test:id"
        assert request.id_short is None
        assert request.value_overrides is None
        assert request.copy_semantic_id is True

    def test_full_request(self):
        """Test request with all fields."""
        request = InstantiateTemplateRequest(
            new_id="urn:test:id",
            id_short="TestInstance",
            value_overrides={"Prop1": 100, "Prop2": "value"},
            copy_semantic_id=False,
        )
        assert request.new_id == "urn:test:id"
        assert request.id_short == "TestInstance"
        assert request.value_overrides == {"Prop1": 100, "Prop2": "value"}
        assert request.copy_semantic_id is False

    def test_missing_new_id_fails(self):
        """Test that missing new_id raises validation error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            InstantiateTemplateRequest()  # type: ignore

    def test_empty_string_new_id(self):
        """Test that empty string new_id is accepted."""
        # Empty string is technically valid per Pydantic
        request = InstantiateTemplateRequest(new_id="")
        assert request.new_id == ""

    def test_nested_value_overrides(self):
        """Test value overrides with nested paths."""
        request = InstantiateTemplateRequest(
            new_id="urn:test:id",
            value_overrides={
                "Collection.Property": 42,
                "List[0]": "first",
                "Deep.Nested.Path": True,
            },
        )
        assert request.value_overrides == {
            "Collection.Property": 42,
            "List[0]": "first",
            "Deep.Nested.Path": True,
        }

    def test_complex_value_types_in_overrides(self):
        """Test value overrides with various JSON types."""
        request = InstantiateTemplateRequest(
            new_id="urn:test:id",
            value_overrides={
                "IntProp": 42,
                "FloatProp": 3.14,
                "StringProp": "hello",
                "BoolProp": True,
                "NullProp": None,
                "ListProp": [1, 2, 3],
                "DictProp": {"nested": "value"},
            },
        )
        assert request.value_overrides["IntProp"] == 42
        assert request.value_overrides["FloatProp"] == 3.14
        assert request.value_overrides["StringProp"] == "hello"
        assert request.value_overrides["BoolProp"] is True
        assert request.value_overrides["NullProp"] is None
        assert request.value_overrides["ListProp"] == [1, 2, 3]
        assert request.value_overrides["DictProp"] == {"nested": "value"}

    def test_copy_semantic_id_default(self):
        """Test copy_semantic_id defaults to True."""
        request = InstantiateTemplateRequest(new_id="urn:test:id")
        assert request.copy_semantic_id is True

    def test_copy_semantic_id_explicit_false(self):
        """Test copy_semantic_id can be set to False."""
        request = InstantiateTemplateRequest(new_id="urn:test:id", copy_semantic_id=False)
        assert request.copy_semantic_id is False

    def test_model_json_schema(self):
        """Test the model generates valid JSON schema."""
        schema = InstantiateTemplateRequest.model_json_schema()
        assert "properties" in schema
        assert "new_id" in schema["properties"]
        assert "id_short" in schema["properties"]
        assert "value_overrides" in schema["properties"]
        assert "copy_semantic_id" in schema["properties"]
        # new_id should be required
        assert "new_id" in schema.get("required", [])

    def test_model_from_json(self):
        """Test model can be created from JSON-like dict."""
        data = {
            "new_id": "urn:test:id",
            "id_short": "MyInstance",
            "value_overrides": {"Speed": 100},
            "copy_semantic_id": False,
        }
        request = InstantiateTemplateRequest.model_validate(data)
        assert request.new_id == "urn:test:id"
        assert request.id_short == "MyInstance"
        assert request.value_overrides == {"Speed": 100}
        assert request.copy_semantic_id is False
