"""Titan → BaSyx interoperability tests.

Tests that AASX packages exported from Titan can be imported into BaSyx SDK.

Test scenarios:
1. Simple AAS (shell only)
2. AAS with submodels (various element types)
3. ConceptDescriptions with semantic IDs
4. Value type compatibility
5. MultiLanguageProperty elements
6. ReferenceElement and RelationshipElement
7. Supplementary files (File elements)
"""

from __future__ import annotations

import io

import pytest
from basyx.aas import model as basyx_model
from basyx.aas.adapter import aasx as basyx_aasx
from basyx.aas.model import datatypes as basyx_datatypes

from titan.compat.aasx import AasxExporter
from titan.core.model import (
    AssetAdministrationShell,
    AssetInformation,
    AssetKind,
    DataTypeDefXsd,
    Key,
    KeyTypes,
    LangStringTextType,
    MultiLanguageProperty,
    Property,
    Reference,
    ReferenceElement,
    ReferenceTypes,
    RelationshipElement,
    Submodel,
    SubmodelElementCollection,
)


class TestTitanExportBaSyxImport:
    """Test Titan AASX export → BaSyx import."""

    @pytest.mark.asyncio
    async def test_simple_shell_round_trip(self) -> None:
        """Export simple shell from Titan, import to BaSyx."""
        # Create Titan shell
        titan_shell = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="urn:example:aas:titan:simple",
            idShort="TitanSimpleShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:titan:simple",
            ),
        )

        # Export to AASX using Titan
        exporter = AasxExporter()
        stream = await exporter.export_to_stream(
            shells=[titan_shell],
            submodels=[],
            concept_descriptions=[],
            use_json=False,  # Use XML for BaSyx compatibility
        )
        aasx_bytes = stream.getvalue()

        assert aasx_bytes is not None
        assert len(aasx_bytes) > 0

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        object_store = basyx_model.DictObjectStore()
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXReader(buffer) as reader:
            reader.read_into(object_store, file_store)

        # Verify shell was imported
        shells = [
            obj for obj in object_store if isinstance(obj, basyx_model.AssetAdministrationShell)
        ]
        assert len(shells) == 1

        basyx_shell = shells[0]
        assert basyx_shell.id == titan_shell.id
        assert basyx_shell.id_short == titan_shell.id_short
        assert (
            basyx_shell.asset_information.global_asset_id
            == titan_shell.asset_information.global_asset_id
        )

    @pytest.mark.asyncio
    async def test_shell_with_properties_submodel(self) -> None:
        """Export AAS with Properties submodel, import to BaSyx."""
        # Create submodel with various value types
        submodel = Submodel(
            model_type="Submodel",
            id="urn:example:submodel:properties",
            idShort="PropertiesSubmodel",
            submodelElements=[
                Property(
                    model_type="Property",
                    idShort="StringProperty",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="test_value",
                ),
                Property(
                    model_type="Property",
                    idShort="IntProperty",
                    valueType=DataTypeDefXsd.XS_INT,
                    value="42",
                ),
                Property(
                    model_type="Property",
                    idShort="DoubleProperty",
                    valueType=DataTypeDefXsd.XS_DOUBLE,
                    value="3.14159",
                ),
                Property(
                    model_type="Property",
                    idShort="BooleanProperty",
                    valueType=DataTypeDefXsd.XS_BOOLEAN,
                    value="true",
                ),
            ],
        )

        # Create shell referencing submodel
        shell = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="urn:example:aas:titan:with_submodel",
            idShort="TitanShellWithSubmodel",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:titan",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[
                        Key(
                            type=KeyTypes.SUBMODEL,
                            value=submodel.id,
                        )
                    ],
                )
            ],
        )

        # Export to AASX
        exporter = AasxExporter()
        stream = await exporter.export_to_stream(
            shells=[shell],
            submodels=[submodel],
            concept_descriptions=[],
            use_json=False,
        )
        aasx_bytes = stream.getvalue()

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        object_store = basyx_model.DictObjectStore()
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXReader(buffer) as reader:
            reader.read_into(object_store, file_store)

        # Verify shell
        shells = [
            obj for obj in object_store if isinstance(obj, basyx_model.AssetAdministrationShell)
        ]
        assert len(shells) == 1
        assert shells[0].id == shell.id

        # Verify submodel
        submodels = [obj for obj in object_store if isinstance(obj, basyx_model.Submodel)]
        assert len(submodels) == 1
        basyx_sm = submodels[0]
        assert basyx_sm.id == submodel.id
        assert basyx_sm.id_short == submodel.id_short

        # Verify properties
        assert len(basyx_sm.submodel_element) == 4

        # Check property values
        props_by_idshort = {prop.id_short: prop for prop in basyx_sm.submodel_element}

        string_prop = props_by_idshort["StringProperty"]
        assert isinstance(string_prop, basyx_model.Property)
        assert string_prop.value == "test_value"
        assert string_prop.value_type is str

        int_prop = props_by_idshort["IntProperty"]
        assert int_prop.value == 42  # BaSyx parses as actual int
        assert int_prop.value_type == basyx_datatypes.Int

        double_prop = props_by_idshort["DoubleProperty"]
        assert double_prop.value == 3.14159  # BaSyx parses as actual float
        # BaSyx uses built-in float for DOUBLE
        assert double_prop.value_type is float

        bool_prop = props_by_idshort["BooleanProperty"]
        assert bool_prop.value is True  # BaSyx parses as actual bool
        assert bool_prop.value_type is bool

    @pytest.mark.asyncio
    async def test_submodel_element_collection(self) -> None:
        """Export submodel with collections, import to BaSyx."""
        submodel = Submodel(
            model_type="Submodel",
            id="urn:example:submodel:collection",
            idShort="CollectionSubmodel",
            submodelElements=[
                SubmodelElementCollection(
                    model_type="SubmodelElementCollection",
                    idShort="SensorData",
                    value=[
                        Property(
                            model_type="Property",
                            idShort="SensorId",
                            valueType=DataTypeDefXsd.XS_STRING,
                            value="SENSOR_001",
                        ),
                        Property(
                            model_type="Property",
                            idShort="Reading",
                            valueType=DataTypeDefXsd.XS_DOUBLE,
                            value="45.6",
                        ),
                    ],
                )
            ],
        )

        shell = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="urn:example:aas:collection",
            idShort="CollectionShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:collection",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value=submodel.id)],
                )
            ],
        )

        # Export
        exporter = AasxExporter()
        stream = await exporter.export_to_stream([shell], [submodel], [], use_json=False)
        aasx_bytes = stream.getvalue()

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        object_store = basyx_model.DictObjectStore()
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXReader(buffer) as reader:
            reader.read_into(object_store, file_store)

        # Verify collection
        submodels = [obj for obj in object_store if isinstance(obj, basyx_model.Submodel)]
        assert len(submodels) == 1
        basyx_sm = submodels[0]

        # BaSyx uses NamespaceSet (set) for submodel_element, convert to list
        smes = list(basyx_sm.submodel_element)
        assert len(smes) == 1
        collection = smes[0]
        assert isinstance(collection, basyx_model.SubmodelElementCollection)
        assert collection.id_short == "SensorData"
        # Collection.value is also a NamespaceSet
        collection_items = list(collection.value)
        assert len(collection_items) == 2

    @pytest.mark.asyncio
    async def test_multi_language_property(self) -> None:
        """Export MultiLanguageProperty, import to BaSyx."""
        submodel = Submodel(
            model_type="Submodel",
            id="urn:example:submodel:mlp",
            idShort="MultiLangSubmodel",
            submodelElements=[
                MultiLanguageProperty(
                    model_type="Property",
                    idShort="ProductName",
                    value=[
                        LangStringTextType(language="en", text="Industrial Robot"),
                        LangStringTextType(language="de", text="Industrieroboter"),
                        LangStringTextType(language="fr", text="Robot industriel"),
                    ],
                )
            ],
        )

        shell = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="urn:example:aas:mlp",
            idShort="MLPShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:mlp",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value=submodel.id)],
                )
            ],
        )

        # Export
        exporter = AasxExporter()
        stream = await exporter.export_to_stream([shell], [submodel], [], use_json=False)
        aasx_bytes = stream.getvalue()

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        object_store = basyx_model.DictObjectStore()
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXReader(buffer) as reader:
            reader.read_into(object_store, file_store)

        # Verify MultiLanguageProperty
        submodels = [obj for obj in object_store if isinstance(obj, basyx_model.Submodel)]
        basyx_sm = submodels[0]
        # BaSyx uses NamespaceSet for submodel_element
        smes = list(basyx_sm.submodel_element)
        mlp = smes[0]

        assert isinstance(mlp, basyx_model.MultiLanguageProperty)
        assert mlp.id_short == "ProductName"
        # BaSyx MultiLanguageProperty.value is a dict, not a list
        assert len(mlp.value) == 3

        # Check language strings (value is dict[str, str] in BaSyx)
        assert mlp.value["en"] == "Industrial Robot"
        assert mlp.value["de"] == "Industrieroboter"
        assert mlp.value["fr"] == "Robot industriel"

    @pytest.mark.asyncio
    async def test_reference_element(self) -> None:
        """Export ReferenceElement, import to BaSyx."""
        submodel = Submodel(
            model_type="Submodel",
            id="urn:example:submodel:ref",
            idShort="ReferenceSubmodel",
            submodelElements=[
                ReferenceElement(
                    model_type="ReferenceElement",
                    idShort="ExternalRef",
                    value=Reference(
                        type=ReferenceTypes.EXTERNAL_REFERENCE,
                        keys=[
                            Key(
                                type=KeyTypes.GLOBAL_REFERENCE,
                                value="https://example.com/external/resource",
                            )
                        ],
                    ),
                )
            ],
        )

        shell = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="urn:example:aas:ref",
            idShort="RefShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:ref",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value=submodel.id)],
                )
            ],
        )

        # Export
        exporter = AasxExporter()
        stream = await exporter.export_to_stream([shell], [submodel], [], use_json=False)
        aasx_bytes = stream.getvalue()

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        object_store = basyx_model.DictObjectStore()
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXReader(buffer) as reader:
            reader.read_into(object_store, file_store)

        # Verify ReferenceElement
        submodels = [obj for obj in object_store if isinstance(obj, basyx_model.Submodel)]
        basyx_sm = submodels[0]
        # BaSyx uses NamespaceSet for submodel_element
        smes = list(basyx_sm.submodel_element)
        ref_elem = smes[0]

        assert isinstance(ref_elem, basyx_model.ReferenceElement)
        assert ref_elem.id_short == "ExternalRef"
        assert len(ref_elem.value.key) == 1
        assert ref_elem.value.key[0].value == "https://example.com/external/resource"

    @pytest.mark.asyncio
    async def test_relationship_element(self) -> None:
        """Export RelationshipElement, import to BaSyx."""
        submodel = Submodel(
            model_type="Submodel",
            id="urn:example:submodel:rel",
            idShort="RelationshipSubmodel",
            submodelElements=[
                # First create two properties to reference
                Property(
                    model_type="Property",
                    idShort="SourceProperty",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="source",
                ),
                Property(
                    model_type="Property",
                    idShort="TargetProperty",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="target",
                ),
                RelationshipElement(
                    model_type="RelationshipElement",
                    idShort="ConnectsTo",
                    first=Reference(
                        type=ReferenceTypes.MODEL_REFERENCE,
                        keys=[
                            Key(type=KeyTypes.SUBMODEL, value="urn:example:submodel:rel"),
                            Key(type=KeyTypes.PROPERTY, value="SourceProperty"),
                        ],
                    ),
                    second=Reference(
                        type=ReferenceTypes.MODEL_REFERENCE,
                        keys=[
                            Key(type=KeyTypes.SUBMODEL, value="urn:example:submodel:rel"),
                            Key(type=KeyTypes.PROPERTY, value="TargetProperty"),
                        ],
                    ),
                ),
            ],
        )

        shell = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="urn:example:aas:rel",
            idShort="RelShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:rel",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value=submodel.id)],
                )
            ],
        )

        # Export
        exporter = AasxExporter()
        stream = await exporter.export_to_stream([shell], [submodel], [], use_json=False)
        aasx_bytes = stream.getvalue()

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        object_store = basyx_model.DictObjectStore()
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXReader(buffer) as reader:
            reader.read_into(object_store, file_store)

        # Verify RelationshipElement
        submodels = [obj for obj in object_store if isinstance(obj, basyx_model.Submodel)]
        basyx_sm = submodels[0]

        # Find the relationship element
        rel_elem = None
        for elem in basyx_sm.submodel_element:
            if isinstance(elem, basyx_model.RelationshipElement):
                rel_elem = elem
                break

        assert rel_elem is not None
        assert rel_elem.id_short == "ConnectsTo"
        assert len(rel_elem.first.key) == 2
        assert len(rel_elem.second.key) == 2
        assert rel_elem.first.key[1].value == "SourceProperty"
        assert rel_elem.second.key[1].value == "TargetProperty"


class TestSemanticEquivalence:
    """Test semantic equivalence across Titan→BaSyx conversions."""

    @pytest.mark.asyncio
    async def test_value_type_preservation(self) -> None:
        """All XSD value types preserved in round-trip."""
        # Create submodel with all supported value types
        submodel = Submodel(
            model_type="Submodel",
            id="urn:example:submodel:types",
            idShort="TypesSubmodel",
            submodelElements=[
                Property(
                    model_type="Property",
                    idShort="xs_string",
                    valueType=DataTypeDefXsd.XS_STRING,
                    value="text",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_int",
                    valueType=DataTypeDefXsd.XS_INT,
                    value="123",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_integer",
                    valueType=DataTypeDefXsd.XS_INTEGER,
                    value="456",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_long",
                    valueType=DataTypeDefXsd.XS_LONG,
                    value="789",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_short",
                    valueType=DataTypeDefXsd.XS_SHORT,
                    value="12",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_byte",
                    valueType=DataTypeDefXsd.XS_BYTE,
                    value="5",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_double",
                    valueType=DataTypeDefXsd.XS_DOUBLE,
                    value="3.14",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_float",
                    valueType=DataTypeDefXsd.XS_FLOAT,
                    value="2.71",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_boolean",
                    valueType=DataTypeDefXsd.XS_BOOLEAN,
                    value="true",
                ),
                Property(
                    model_type="Property",
                    idShort="xs_date",
                    valueType=DataTypeDefXsd.XS_DATE,
                    value="2024-01-15",
                ),
            ],
        )

        shell = AssetAdministrationShell(
            model_type="AssetAdministrationShell",
            id="urn:example:aas:types",
            idShort="TypesShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:types",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value=submodel.id)],
                )
            ],
        )

        # Export
        exporter = AasxExporter()
        stream = await exporter.export_to_stream([shell], [submodel], [], use_json=False)
        aasx_bytes = stream.getvalue()

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        object_store = basyx_model.DictObjectStore()
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXReader(buffer) as reader:
            reader.read_into(object_store, file_store)

        # Verify all properties have correct types
        submodels = [obj for obj in object_store if isinstance(obj, basyx_model.Submodel)]
        basyx_sm = submodels[0]

        props_by_idshort = {prop.id_short: prop for prop in basyx_sm.submodel_element}

        # BaSyx uses its own datatypes from basyx.aas.model.datatypes for some types
        assert props_by_idshort["xs_string"].value_type is str
        assert props_by_idshort["xs_int"].value_type == basyx_datatypes.Int
        # BaSyx uses built-in float for DOUBLE
        assert props_by_idshort["xs_double"].value_type is float
        # BaSyx uses custom Float for FLOAT
        assert props_by_idshort["xs_float"].value_type == basyx_datatypes.Float
        assert props_by_idshort["xs_boolean"].value_type is bool
        assert props_by_idshort["xs_date"].value_type == basyx_datatypes.Date
