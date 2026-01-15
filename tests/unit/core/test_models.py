"""Tests for AAS domain models.

Tests validation, serialization, and discriminated union behavior
for the IDTA-01001 Part 1 v3.1.2 metamodel.
"""

import pytest
from pydantic import ValidationError

from titan.core.model import (
    # Enums
    AasSubmodelElements,
    # Administrative
    AssetAdministrationShell,
    AssetInformation,
    AssetKind,
    Blob,
    Capability,
    DataSpecificationIec61360,
    DataTypeDefXsd,
    EmbeddedDataSpecification,
    Entity,
    EntityType,
    File,
    # Core types
    Key,
    KeyTypes,
    LangStringPreferredNameType,
    # Lang strings
    LangStringTextType,
    ModellingKind,
    MultiLanguageProperty,
    # SubmodelElements
    Property,
    Range,
    Reference,
    ReferenceElement,
    ReferenceTypes,
    RelationshipElement,
    # Containers
    Submodel,
    SubmodelElementCollection,
    SubmodelElementList,
)
from titan.core.model.submodel_elements import SubmodelElementUnion


class TestReference:
    """Test Reference model."""

    def test_external_reference(self) -> None:
        """External reference with single key."""
        ref = Reference(
            type=ReferenceTypes.EXTERNAL_REFERENCE,
            keys=[Key(type=KeyTypes.GLOBAL_REFERENCE, value="https://example.com")],
        )
        assert ref.is_external
        assert not ref.is_model_reference

    def test_model_reference(self) -> None:
        """Model reference with multiple keys."""
        ref = Reference(
            type=ReferenceTypes.MODEL_REFERENCE,
            keys=[
                Key(type=KeyTypes.SUBMODEL, value="urn:example:submodel:1"),
                Key(type=KeyTypes.PROPERTY, value="temperature"),
            ],
        )
        assert ref.is_model_reference
        assert not ref.is_external

    def test_reference_requires_at_least_one_key(self) -> None:
        """Reference must have at least one key."""
        with pytest.raises(ValidationError):
            Reference(type=ReferenceTypes.EXTERNAL_REFERENCE, keys=[])


class TestProperty:
    """Test Property SubmodelElement."""

    def test_basic_property(self) -> None:
        """Basic property with string value."""
        prop = Property(
            model_type="Property",
            idShort="temperature",
            valueType=DataTypeDefXsd.XS_DOUBLE,
            value="25.5",
        )
        assert prop.id_short == "temperature"
        assert prop.value_type == DataTypeDefXsd.XS_DOUBLE
        assert prop.value == "25.5"
        assert prop.model_type == "Property"

    def test_property_with_semantic_id(self) -> None:
        """Property with semantic identifier."""
        prop = Property(
            model_type="Property",
            idShort="serialNumber",
            valueType=DataTypeDefXsd.XS_STRING,
            value="ABC-12345",
            semanticId=Reference(
                type=ReferenceTypes.EXTERNAL_REFERENCE,
                keys=[Key(type=KeyTypes.GLOBAL_REFERENCE, value="0173-1#02-AAM556#002")],
            ),
        )
        assert prop.semantic_id is not None
        assert prop.semantic_id.keys[0].value == "0173-1#02-AAM556#002"

    def test_property_serializes_with_alias(self) -> None:
        """Property serializes with camelCase aliases."""
        prop = Property(
            model_type="Property",
            idShort="test",
            valueType=DataTypeDefXsd.XS_STRING,
        )
        data = prop.model_dump(by_alias=True, exclude_none=True)
        assert "modelType" in data
        assert "valueType" in data
        assert "idShort" in data
        assert data["modelType"] == "Property"


class TestMultiLanguageProperty:
    """Test MultiLanguageProperty SubmodelElement."""

    def test_basic_multi_lang_property(self) -> None:
        """Multi-language property with values."""
        prop = MultiLanguageProperty(
            model_type="MultiLanguageProperty",
            idShort="description",
            value=[
                LangStringTextType(language="en", text="Description"),
                LangStringTextType(language="de", text="Beschreibung"),
            ],
        )
        assert prop.model_type == "MultiLanguageProperty"
        assert len(prop.value) == 2


class TestRange:
    """Test Range SubmodelElement."""

    def test_range_with_min_max(self) -> None:
        """Range with min and max values."""
        rng = Range(
            model_type="Range",
            idShort="operatingTemp", valueType=DataTypeDefXsd.XS_DOUBLE, min="-40", max="85"
        )
        assert rng.min == "-40"
        assert rng.max == "85"
        assert rng.model_type == "Range"


class TestBlob:
    """Test Blob SubmodelElement."""

    def test_blob_with_content(self) -> None:
        """Blob with base64 content."""
        blob = Blob(
            model_type="Blob",
            idShort="thumbnail",
            contentType="image/png",
            value="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        )
        assert blob.content_type == "image/png"
        assert blob.model_type == "Blob"


class TestFile:
    """Test File SubmodelElement."""

    def test_file_with_path(self) -> None:
        """File with path reference."""
        file = File(
            model_type="File",
            idShort="manual", contentType="application/pdf", value="/aasx/documentation/manual.pdf"
        )
        assert file.content_type == "application/pdf"
        assert file.model_type == "File"


class TestSubmodelElementCollection:
    """Test SubmodelElementCollection."""

    def test_collection_with_elements(self) -> None:
        """Collection containing nested elements."""
        collection = SubmodelElementCollection(
            model_type="SubmodelElementCollection",
            idShort="address",
            value=[
                Property(
                    model_type="Property",
                    idShort="street",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="Main St",
                ),
                Property(
                    model_type="Property",
                    idShort="city",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="Boston",
                ),
                Property(
                    model_type="Property",
                    idShort="zip",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="02101",
                ),
            ],
        )
        assert collection.model_type == "SubmodelElementCollection"
        assert len(collection.value) == 3

    def test_nested_collections(self) -> None:
        """Collections can be nested."""
        inner = SubmodelElementCollection(
            model_type="SubmodelElementCollection",
            idShort="inner",
            value=[
                Property(model_type="Property", idShort="prop", valueType=DataTypeDefXsd.XS_STRING)
            ],
        )
        outer = SubmodelElementCollection(
            model_type="SubmodelElementCollection",
            idShort="outer",
            value=[inner],
        )
        assert outer.value[0].model_type == "SubmodelElementCollection"


class TestSubmodelElementList:
    """Test SubmodelElementList."""

    def test_list_of_properties(self) -> None:
        """List containing properties."""
        lst = SubmodelElementList(
            model_type="SubmodelElementList",
            idShort="measurements",
            typeValueListElement=AasSubmodelElements.PROPERTY,
            valueTypeListElement=DataTypeDefXsd.XS_DOUBLE,
            orderRelevant=True,
            value=[
                Property(
                    model_type="Property",
                    idShort="m1",
                    valueType=DataTypeDefXsd.XS_DOUBLE,
                    value="1.0",
                ),
                Property(
                    model_type="Property",
                    idShort="m2",
                    valueType=DataTypeDefXsd.XS_DOUBLE,
                    value="2.0",
                ),
            ],
        )
        assert lst.model_type == "SubmodelElementList"
        assert lst.order_relevant is True


class TestEntity:
    """Test Entity SubmodelElement."""

    def test_self_managed_entity(self) -> None:
        """Self-managed entity with global asset ID."""
        entity = Entity(
            model_type="Entity",
            idShort="motor",
            entityType=EntityType.SELF_MANAGED_ENTITY,
            globalAssetId="https://example.com/assets/motor-001",
        )
        assert entity.entity_type == EntityType.SELF_MANAGED_ENTITY
        assert entity.model_type == "Entity"


class TestDiscriminatedUnion:
    """Test discriminated union for SubmodelElements."""

    def test_discriminator_resolves_property(self) -> None:
        """Discriminator correctly identifies Property."""
        data = {
            "modelType": "Property",
            "idShort": "test",
            "valueType": "xs:string",
            "value": "hello",
        }
        # Parse through a container that uses the union
        from pydantic import TypeAdapter

        adapter = TypeAdapter(SubmodelElementUnion)
        element = adapter.validate_python(data)
        assert isinstance(element, Property)
        assert element.value == "hello"

    def test_discriminator_resolves_collection(self) -> None:
        """Discriminator correctly identifies SubmodelElementCollection."""
        data = {
            "modelType": "SubmodelElementCollection",
            "idShort": "test",
            "value": [{"modelType": "Property", "idShort": "p1", "valueType": "xs:string"}],
        }
        from pydantic import TypeAdapter

        adapter = TypeAdapter(SubmodelElementUnion)
        element = adapter.validate_python(data)
        assert isinstance(element, SubmodelElementCollection)

    def test_all_element_types_have_model_type(self) -> None:
        """All SubmodelElement types have modelType field."""
        elements = [
            Property(model_type="Property", idShort="p", valueType=DataTypeDefXsd.XS_STRING),
            MultiLanguageProperty(model_type="MultiLanguageProperty", idShort="mlp"),
            Range(model_type="Range", idShort="r", valueType=DataTypeDefXsd.XS_DOUBLE),
            Blob(model_type="Blob", idShort="b", contentType="application/octet-stream"),
            File(model_type="File", idShort="f", contentType="text/plain"),
            ReferenceElement(model_type="ReferenceElement", idShort="re"),
            RelationshipElement(
                model_type="RelationshipElement",
                idShort="rel",
                first=Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value="x")],
                ),
                second=Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value="y")],
                ),
            ),
            SubmodelElementCollection(model_type="SubmodelElementCollection", idShort="sec"),
            SubmodelElementList(
                model_type="SubmodelElementList",
                idShort="sel",
                typeValueListElement=AasSubmodelElements.PROPERTY,
                valueTypeListElement=DataTypeDefXsd.XS_STRING,
            ),
            Entity(model_type="Entity", idShort="e", entityType=EntityType.CO_MANAGED_ENTITY),
            Capability(model_type="Capability", idShort="cap"),
        ]
        for elem in elements:
            data = elem.model_dump(by_alias=True)
            assert "modelType" in data
            assert data["modelType"] == elem.model_type


class TestSubmodel:
    """Test Submodel container."""

    def test_basic_submodel(self) -> None:
        """Basic submodel with elements."""
        sm = Submodel(
            model_type="Submodel",
            id="https://example.com/submodels/technical-data",
            idShort="TechnicalData",
            kind=ModellingKind.INSTANCE,
            submodelElements=[
                Property(
                    model_type="Property",
                    idShort="weight",
                    valueType=DataTypeDefXsd.XS_DOUBLE,
                    value="2.5",
                ),
                Property(
                    model_type="Property",
                    idShort="height",
                    valueType=DataTypeDefXsd.XS_DOUBLE,
                    value="10.0",
                ),
            ],
        )
        assert sm.id == "https://example.com/submodels/technical-data"
        assert len(sm.submodel_elements) == 2

    def test_submodel_serialization(self) -> None:
        """Submodel serializes correctly with aliases."""
        sm = Submodel(
            model_type="Submodel",
            id="urn:example:submodel:1",
            submodelElements=[
                Property(
                    model_type="Property",
                    idShort="p1",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="test",
                )
            ],
        )
        data = sm.model_dump(by_alias=True, exclude_none=True)
        assert "submodelElements" in data
        assert data["submodelElements"][0]["modelType"] == "Property"


class TestAssetAdministrationShell:
    """Test AssetAdministrationShell container."""

    def test_basic_aas(self) -> None:
        """Basic AAS with asset information."""
        aas = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="https://example.com/aas/1",
            idShort="ExampleAAS",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE, globalAssetId="https://example.com/assets/product-001"
            ),
        )
        assert aas.id == "https://example.com/aas/1"
        assert aas.asset_information.asset_kind == AssetKind.INSTANCE

    def test_aas_with_submodel_refs(self) -> None:
        """AAS with submodel references."""
        aas = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="https://example.com/aas/1",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE, globalAssetId="https://example.com/assets/1"
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value="https://example.com/submodels/1")],
                )
            ],
        )
        assert len(aas.submodels) == 1


class TestHasDataSpecification:
    """Test HasDataSpecification mixin (Titan-only feature)."""

    def test_property_with_data_specification(self) -> None:
        """Property can have embedded data specifications."""
        prop = Property(
            model_type="Property",
            idShort="voltage",
            valueType=DataTypeDefXsd.XS_DOUBLE,
            value="230",
            embeddedDataSpecifications=[
                EmbeddedDataSpecification(
                    dataSpecification=Reference(
                        type=ReferenceTypes.EXTERNAL_REFERENCE,
                        keys=[
                            Key(
                                type=KeyTypes.GLOBAL_REFERENCE,
                                value="https://admin-shell.io/aas/3/0/RC02/DataSpecificationIec61360",
                            )
                        ],
                    ),
                    dataSpecificationContent=DataSpecificationIec61360(
                        model_type="DataSpecificationIec61360",
                        preferredName=[
                            LangStringPreferredNameType(language="en", text="Voltage"),
                            LangStringPreferredNameType(language="de", text="Spannung"),
                        ]
                    ),
                )
            ],
        )
        assert len(prop.embedded_data_specifications) == 1
        spec = prop.embedded_data_specifications[0]
        assert len(spec.data_specification_content.preferred_name) == 2


class TestStrictMode:
    """Test strict mode validation."""

    def test_extra_fields_forbidden(self) -> None:
        """Extra fields are not allowed."""
        with pytest.raises(ValidationError):
            Property(
                model_type="Property",
                idShort="test",
                valueType=DataTypeDefXsd.XS_STRING,
                unknownField="should fail",  # type: ignore
            )

    def test_invalid_id_short_pattern(self) -> None:
        """idShort must match pattern ^[a-zA-Z_][a-zA-Z0-9_]*$."""
        with pytest.raises(ValidationError):
            Property(
                model_type="Property",
                idShort="123invalid",  # Can't start with number
                valueType=DataTypeDefXsd.XS_STRING,
            )


class TestCanonicalSerialization:
    """Test canonical JSON serialization."""

    def test_model_dump_excludes_none(self) -> None:
        """model_dump with exclude_none removes null fields."""
        prop = Property(
            model_type="Property",
            idShort="test",
            valueType=DataTypeDefXsd.XS_STRING,
        )
        data = prop.model_dump(by_alias=True, exclude_none=True)
        assert "value" not in data  # None value excluded
        assert "semanticId" not in data

    def test_model_dump_uses_aliases(self) -> None:
        """model_dump with by_alias uses camelCase."""
        prop = Property(
            model_type="Property",
            idShort="testProp",
            valueType=DataTypeDefXsd.XS_STRING,
        )
        data = prop.model_dump(by_alias=True)
        assert "idShort" in data
        assert "valueType" in data
        assert "modelType" in data
