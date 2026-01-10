"""Tests for GraphQL schema definitions."""

import pytest
import strawberry

from titan.graphql.schema import (
    AdministrativeInfo,
    AssetInformation,
    AssetKind,
    Blob,
    File,
    Key,
    KeyType,
    LangString,
    ModellingKind,
    MultiLanguageProperty,
    PageInfo,
    Property,
    Qualifier,
    Range,
    Reference,
    Shell,
    ShellConnection,
    ShellInput,
    Submodel,
    SubmodelConnection,
    SubmodelElementCollection,
    SubmodelInput,
    schema,
)


class TestEnums:
    """Tests for GraphQL enum types."""

    def test_modelling_kind_values(self) -> None:
        """ModellingKind has correct values."""
        assert ModellingKind.TEMPLATE.value == "Template"
        assert ModellingKind.INSTANCE.value == "Instance"

    def test_asset_kind_values(self) -> None:
        """AssetKind has correct values."""
        assert AssetKind.TYPE.value == "Type"
        assert AssetKind.INSTANCE.value == "Instance"
        assert AssetKind.NOT_APPLICABLE.value == "NotApplicable"

    def test_key_type_values(self) -> None:
        """KeyType has correct values."""
        assert KeyType.ASSET_ADMINISTRATION_SHELL.value == "AssetAdministrationShell"
        assert KeyType.SUBMODEL.value == "Submodel"
        assert KeyType.CONCEPT_DESCRIPTION.value == "ConceptDescription"
        assert KeyType.GLOBAL_REFERENCE.value == "GlobalReference"
        assert KeyType.SUBMODEL_ELEMENT.value == "SubmodelElement"


class TestBasicTypes:
    """Tests for basic GraphQL types."""

    def test_key_creation(self) -> None:
        """Key type can be created."""
        key = Key(type=KeyType.SUBMODEL, value="urn:example:submodel:1")

        assert key.type == KeyType.SUBMODEL
        assert key.value == "urn:example:submodel:1"

    def test_reference_creation(self) -> None:
        """Reference type can be created."""
        ref = Reference(
            type="ModelReference",
            keys=[Key(type=KeyType.SUBMODEL, value="urn:example:1")],
        )

        assert ref.type == "ModelReference"
        assert len(ref.keys) == 1

    def test_lang_string_creation(self) -> None:
        """LangString type can be created."""
        ls = LangString(language="en", text="Hello")

        assert ls.language == "en"
        assert ls.text == "Hello"

    def test_administrative_info_creation(self) -> None:
        """AdministrativeInfo type can be created."""
        info = AdministrativeInfo(version="1.0", revision="A")

        assert info.version == "1.0"
        assert info.revision == "A"

    def test_administrative_info_defaults(self) -> None:
        """AdministrativeInfo has default None values."""
        info = AdministrativeInfo()

        assert info.version is None
        assert info.revision is None

    def test_qualifier_creation(self) -> None:
        """Qualifier type can be created."""
        qual = Qualifier(type="Required", value_type="xs:boolean", value="true")

        assert qual.type == "Required"
        assert qual.value_type == "xs:boolean"
        assert qual.value == "true"


class TestAssetInformation:
    """Tests for AssetInformation type."""

    def test_creation_with_required_fields(self) -> None:
        """AssetInformation with required fields only."""
        info = AssetInformation(asset_kind=AssetKind.INSTANCE)

        assert info.asset_kind == AssetKind.INSTANCE
        assert info.global_asset_id is None

    def test_creation_with_all_fields(self) -> None:
        """AssetInformation with all fields."""
        info = AssetInformation(
            asset_kind=AssetKind.TYPE,
            global_asset_id="urn:example:asset:1",
            specific_asset_ids=["id1", "id2"],
            asset_type="Machine",
        )

        assert info.asset_kind == AssetKind.TYPE
        assert info.global_asset_id == "urn:example:asset:1"
        assert info.specific_asset_ids == ["id1", "id2"]
        assert info.asset_type == "Machine"


class TestSubmodelElements:
    """Tests for SubmodelElement types."""

    def test_property_creation(self) -> None:
        """Property element can be created."""
        prop = Property(
            id_short="Temperature",
            value_type="xs:double",
            value="25.5",
        )

        assert prop.id_short == "Temperature"
        assert prop.model_type == "Property"
        assert prop.value_type == "xs:double"
        assert prop.value == "25.5"

    def test_multi_language_property_creation(self) -> None:
        """MultiLanguageProperty element can be created."""
        mlp = MultiLanguageProperty(
            id_short="Description",
            value=[
                LangString(language="en", text="A description"),
                LangString(language="de", text="Eine Beschreibung"),
            ],
        )

        assert mlp.id_short == "Description"
        assert mlp.model_type == "MultiLanguageProperty"
        assert len(mlp.value) == 2

    def test_range_creation(self) -> None:
        """Range element can be created."""
        rng = Range(
            id_short="OperatingTemperature",
            value_type="xs:double",
            min="0",
            max="100",
        )

        assert rng.id_short == "OperatingTemperature"
        assert rng.model_type == "Range"
        assert rng.min == "0"
        assert rng.max == "100"

    def test_blob_creation(self) -> None:
        """Blob element can be created."""
        blob = Blob(
            id_short="Thumbnail",
            content_type="image/png",
            value="iVBORw0KGgo=",
        )

        assert blob.id_short == "Thumbnail"
        assert blob.model_type == "Blob"
        assert blob.content_type == "image/png"

    def test_file_creation(self) -> None:
        """File element can be created."""
        file = File(
            id_short="Manual",
            content_type="application/pdf",
            value="/manuals/device.pdf",
        )

        assert file.id_short == "Manual"
        assert file.model_type == "File"
        assert file.content_type == "application/pdf"

    def test_collection_creation(self) -> None:
        """SubmodelElementCollection can be created."""
        collection = SubmodelElementCollection(
            id_short="Identification",
            value=[
                Property(id_short="SerialNumber", value_type="xs:string", value="123"),
            ],
        )

        assert collection.id_short == "Identification"
        assert collection.model_type == "SubmodelElementCollection"
        assert len(collection.value) == 1


class TestSubmodel:
    """Tests for Submodel type."""

    def test_creation_with_required_fields(self) -> None:
        """Submodel with required fields only."""
        sm = Submodel(id="urn:example:submodel:1")

        assert sm.id == "urn:example:submodel:1"
        assert sm.id_short is None

    def test_creation_with_all_fields(self) -> None:
        """Submodel with all fields."""
        sm = Submodel(
            id="urn:example:submodel:1",
            id_short="TechnicalData",
            description=[LangString(language="en", text="Technical specs")],
            kind=ModellingKind.INSTANCE,
            administration=AdministrativeInfo(version="1.0"),
            submodel_elements=[
                Property(id_short="Weight", value_type="xs:double", value="5.5"),
            ],
        )

        assert sm.id == "urn:example:submodel:1"
        assert sm.id_short == "TechnicalData"
        assert len(sm.description) == 1
        assert sm.kind == ModellingKind.INSTANCE
        assert sm.administration.version == "1.0"
        assert len(sm.submodel_elements) == 1


class TestShell:
    """Tests for Shell type."""

    def test_creation_with_required_fields(self) -> None:
        """Shell with required fields only."""
        shell = Shell(
            id="urn:example:aas:1",
            asset_information=AssetInformation(asset_kind=AssetKind.INSTANCE),
        )

        assert shell.id == "urn:example:aas:1"
        assert shell.asset_information.asset_kind == AssetKind.INSTANCE

    def test_creation_with_all_fields(self) -> None:
        """Shell with all fields."""
        shell = Shell(
            id="urn:example:aas:1",
            id_short="MyShell",
            description=[LangString(language="en", text="An AAS")],
            asset_information=AssetInformation(
                asset_kind=AssetKind.INSTANCE,
                global_asset_id="urn:example:asset:1",
            ),
            administration=AdministrativeInfo(version="2.0"),
        )

        assert shell.id == "urn:example:aas:1"
        assert shell.id_short == "MyShell"
        assert len(shell.description) == 1
        assert shell.asset_information.global_asset_id == "urn:example:asset:1"


class TestPagination:
    """Tests for pagination types."""

    def test_page_info_creation(self) -> None:
        """PageInfo can be created."""
        info = PageInfo(
            has_next_page=True,
            has_previous_page=False,
            start_cursor="abc123",
            end_cursor="xyz789",
        )

        assert info.has_next_page is True
        assert info.has_previous_page is False
        assert info.start_cursor == "abc123"
        assert info.end_cursor == "xyz789"

    def test_shell_connection_creation(self) -> None:
        """ShellConnection can be created."""
        conn = ShellConnection(
            edges=[],
            page_info=PageInfo(has_next_page=False, has_previous_page=False),
            total_count=0,
        )

        assert conn.edges == []
        assert conn.total_count == 0

    def test_submodel_connection_creation(self) -> None:
        """SubmodelConnection can be created."""
        conn = SubmodelConnection(
            edges=[],
            page_info=PageInfo(has_next_page=False, has_previous_page=False),
            total_count=0,
        )

        assert conn.edges == []
        assert conn.total_count == 0


class TestInputTypes:
    """Tests for input types."""

    def test_shell_input_creation(self) -> None:
        """ShellInput can be created."""
        input = ShellInput(
            id="urn:example:aas:1",
            id_short="MyShell",
            asset_kind=AssetKind.INSTANCE,
            global_asset_id="urn:example:asset:1",
        )

        assert input.id == "urn:example:aas:1"
        assert input.id_short == "MyShell"
        assert input.asset_kind == AssetKind.INSTANCE

    def test_shell_input_defaults(self) -> None:
        """ShellInput has correct defaults."""
        input = ShellInput(id="urn:example:aas:1")

        assert input.id_short is None
        assert input.asset_kind == AssetKind.INSTANCE
        assert input.global_asset_id is None

    def test_submodel_input_creation(self) -> None:
        """SubmodelInput can be created."""
        input = SubmodelInput(
            id="urn:example:submodel:1",
            id_short="TechnicalData",
            semantic_id="urn:example:semantic:1",
        )

        assert input.id == "urn:example:submodel:1"
        assert input.id_short == "TechnicalData"
        assert input.semantic_id == "urn:example:semantic:1"


class TestSchema:
    """Tests for the GraphQL schema."""

    def test_schema_exists(self) -> None:
        """Schema is created."""
        assert schema is not None

    def test_schema_has_query(self) -> None:
        """Schema has query type."""
        assert schema.query is not None

    def test_schema_has_mutation(self) -> None:
        """Schema has mutation type."""
        assert schema.mutation is not None

    def test_schema_introspection(self) -> None:
        """Schema can be introspected."""
        introspection = schema.introspect()

        assert introspection is not None
        assert "__schema" in introspection
