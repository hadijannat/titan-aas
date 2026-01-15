"""Tests for ConceptDescription model following IDTA-01001 Part 1."""

import pytest

from titan.core.model import ConceptDescription, Key, KeyTypes, Reference, ReferenceTypes


class TestConceptDescriptionBasic:
    """Basic ConceptDescription model tests."""

    def test_minimal_concept_description(self):
        """Create a ConceptDescription with only required fields."""
        cd = ConceptDescription(model_type="ConceptDescription", id="urn:example:cd:1")

        assert cd.id == "urn:example:cd:1"
        assert cd.id_short is None
        assert cd.description is None
        assert cd.display_name is None
        assert cd.category is None
        assert cd.administration is None
        assert cd.is_case_of is None

    def test_concept_description_with_id_short(self):
        """Create a ConceptDescription with idShort."""
        cd = ConceptDescription(
            model_type="ConceptDescription",
            id="urn:example:cd:2",
            id_short="Temperature",
        )

        assert cd.id == "urn:example:cd:2"
        assert cd.id_short == "Temperature"

    def test_concept_description_with_description(self):
        """Create a ConceptDescription with multi-language description."""
        cd = ConceptDescription(
            model_type="ConceptDescription",
            id="urn:example:cd:3",
            id_short="Temperature",
            description=[
                {"language": "en", "text": "Measured temperature in Celsius"},
                {"language": "de", "text": "Gemessene Temperatur in Celsius"},
            ],
        )

        assert cd.id == "urn:example:cd:3"
        assert len(cd.description) == 2
        # LangStringTextType is a Pydantic model with language and text attributes
        assert cd.description[0].language == "en"
        assert cd.description[1].language == "de"

    def test_concept_description_with_display_name(self):
        """Create a ConceptDescription with display name."""
        cd = ConceptDescription(
            model_type="ConceptDescription",
            id="urn:example:cd:4",
            display_name=[
                {"language": "en", "text": "Temperature"},
                {"language": "de", "text": "Temperatur"},
            ],
        )

        assert cd.display_name is not None
        assert len(cd.display_name) == 2


class TestConceptDescriptionIsCaseOf:
    """Tests for isCaseOf references."""

    def test_is_case_of_single_reference(self):
        """ConceptDescription with a single isCaseOf reference."""
        cd = ConceptDescription(
            model_type="ConceptDescription",
            id="urn:example:cd:temp",
            id_short="Temperature",
            is_case_of=[
                Reference(
                    type=ReferenceTypes.EXTERNAL_REFERENCE,
                    keys=[
                        Key(
                            type=KeyTypes.GLOBAL_REFERENCE,
                            value="http://admin-shell.io/DataSpecificationTemplates/IEC61360",
                        )
                    ],
                )
            ],
        )

        assert cd.is_case_of is not None
        assert len(cd.is_case_of) == 1
        assert cd.is_case_of[0].type == ReferenceTypes.EXTERNAL_REFERENCE

    def test_is_case_of_multiple_references(self):
        """ConceptDescription with multiple isCaseOf references."""
        cd = ConceptDescription(
            model_type="ConceptDescription",
            id="urn:example:cd:multi",
            id_short="MultiReference",
            is_case_of=[
                Reference(
                    type=ReferenceTypes.EXTERNAL_REFERENCE,
                    keys=[Key(type=KeyTypes.GLOBAL_REFERENCE, value="urn:external:ref:1")],
                ),
                Reference(
                    type=ReferenceTypes.EXTERNAL_REFERENCE,
                    keys=[Key(type=KeyTypes.GLOBAL_REFERENCE, value="urn:external:ref:2")],
                ),
            ],
        )

        assert len(cd.is_case_of) == 2


class TestConceptDescriptionSerialization:
    """Tests for ConceptDescription serialization."""

    def test_serialization_uses_aliases(self):
        """Serialization should use camelCase aliases."""
        cd = ConceptDescription(
            model_type="ConceptDescription",
            id="urn:example:cd:alias",
            id_short="AliasTest",
            display_name=[{"language": "en", "text": "Alias"}],
            is_case_of=[
                Reference(
                    type=ReferenceTypes.EXTERNAL_REFERENCE,
                    keys=[Key(type=KeyTypes.GLOBAL_REFERENCE, value="urn:ref:1")],
                )
            ],
        )

        data = cd.model_dump(mode="json", by_alias=True, exclude_none=True)

        # Should use camelCase aliases
        assert "idShort" in data
        assert "displayName" in data
        assert "isCaseOf" in data

        # Should NOT use snake_case
        assert "id_short" not in data
        assert "display_name" not in data
        assert "is_case_of" not in data

    def test_serialization_excludes_none(self):
        """Serialization should exclude None values."""
        cd = ConceptDescription(model_type="ConceptDescription", id="urn:example:cd:minimal")

        data = cd.model_dump(mode="json", by_alias=True, exclude_none=True)

        assert "id" in data
        # None values should be excluded
        assert "idShort" not in data
        assert "description" not in data
        assert "displayName" not in data
        assert "category" not in data
        assert "isCaseOf" not in data

    def test_deserialization_from_alias(self):
        """Deserialization should accept camelCase aliases."""
        data = {
            "id": "urn:example:cd:deser",
            "idShort": "DeserTest",
            "displayName": [{"language": "en", "text": "Test"}],
            "isCaseOf": [
                {
                    "type": "ExternalReference",
                    "keys": [{"type": "GlobalReference", "value": "urn:ref:deser"}],
                }
            ],
        }

        cd = ConceptDescription.model_validate(data | {"modelType": "ConceptDescription"})

        assert cd.id == "urn:example:cd:deser"
        assert cd.id_short == "DeserTest"
        assert cd.display_name is not None
        assert cd.is_case_of is not None


class TestConceptDescriptionValidation:
    """Tests for ConceptDescription validation."""

    def test_id_is_required(self):
        """ID is a required field."""
        with pytest.raises(Exception):
            ConceptDescription()  # type: ignore

    def test_invalid_id_short_pattern(self):
        """idShort must match the pattern constraint."""
        # idShort cannot start with a number
        with pytest.raises(Exception):
            ConceptDescription(
                model_type="ConceptDescription",
                id="urn:example:cd:invalid",
                id_short="123Invalid",
            )

    def test_extra_fields_forbidden(self):
        """Extra fields should be rejected (strict mode)."""
        with pytest.raises(Exception):
            ConceptDescription(
                model_type="ConceptDescription",
                id="urn:example:cd:extra",
                unknown_field="value",  # type: ignore
            )
