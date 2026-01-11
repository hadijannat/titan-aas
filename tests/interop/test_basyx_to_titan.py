"""BaSyx → Titan interoperability tests.

Tests that AASX packages exported from BaSyx SDK can be imported into Titan.

Test scenarios:
1. Simple AAS import
2. Complex AAS with submodels
3. Round-trip tests (Titan → BaSyx → Titan)
4. Semantic equivalence validation
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from basyx.aas import model as basyx_model
from basyx.aas.adapter import aasx as basyx_aasx

from titan.compat.aasx import AasxImporter


class TestBaSyxExportTitanImport:
    """Test BaSyx AASX export → Titan import."""

    @pytest.mark.asyncio
    async def test_import_simple_shell(
        self,
        basyx_aas_simple: basyx_model.AssetAdministrationShell,
    ) -> None:
        """Import simple BaSyx shell into Titan."""
        # Export from BaSyx using AASXWriter
        buffer = io.BytesIO()
        object_store = basyx_model.DictObjectStore([basyx_aas_simple])

        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXWriter(buffer) as writer:
            writer.write_aas(
                aas_ids=basyx_aas_simple.id,
                object_store=object_store,
                file_store=file_store,
                write_json=False,
            )

        buffer.seek(0)

        # Import to Titan
        importer = AasxImporter()
        package = await importer.import_from_stream(buffer)

        # Verify shell was imported
        assert len(package.shells) == 1
        titan_shell = package.shells[0]

        # Verify IDs match
        assert titan_shell.id == basyx_aas_simple.id
        assert titan_shell.id_short == basyx_aas_simple.id_short

        # Verify asset information
        assert titan_shell.asset_information.global_asset_id == basyx_aas_simple.asset_information.global_asset_id

    @pytest.mark.asyncio
    async def test_import_complex_shell(
        self,
        basyx_aas_complex: tuple[
            basyx_model.AssetAdministrationShell,
            set[basyx_model.Submodel],
            set[basyx_model.ConceptDescription],
        ],
    ) -> None:
        """Import complex BaSyx AAS (with submodels and CDs) into Titan."""
        shell, submodels, concept_descriptions = basyx_aas_complex

        # Export from BaSyx
        buffer = io.BytesIO()
        all_objects = [shell, *submodels, *concept_descriptions]
        object_store = basyx_model.DictObjectStore(all_objects)

        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXWriter(buffer) as writer:
            writer.write_aas(
                aas_ids=shell.id,
                object_store=object_store,
                file_store=file_store,
                write_json=False,
            )

        buffer.seek(0)

        # Import to Titan
        importer = AasxImporter()
        package = await importer.import_from_stream(buffer)

        # Verify shell
        assert len(package.shells) == 1
        titan_shell = package.shells[0]
        assert titan_shell.id == shell.id
        assert titan_shell.id_short == shell.id_short

        # Verify submodels
        assert len(package.submodels) == len(submodels)
        titan_sm_ids = {sm.id for sm in package.submodels}
        basyx_sm_ids = {sm.id for sm in submodels}
        assert titan_sm_ids == basyx_sm_ids

        # Verify concept descriptions
        assert len(package.concept_descriptions) == len(concept_descriptions)
        titan_cd_ids = {cd.id for cd in package.concept_descriptions}
        basyx_cd_ids = {cd.id for cd in concept_descriptions}
        assert titan_cd_ids == basyx_cd_ids

    @pytest.mark.asyncio
    async def test_import_properties_submodel(self) -> None:
        """Import submodel with various Property types."""
        # Create BaSyx submodel with properties
        submodel = basyx_model.Submodel(
            id_="urn:basyx:submodel:properties",
            id_short="PropertiesSubmodel",
            submodel_element=[
                basyx_model.Property(
                    id_short="StringProp",
                    value_type=basyx_model.DataTypeDefXsd.STRING,
                    value="test",
                ),
                basyx_model.Property(
                    id_short="IntProp",
                    value_type=basyx_model.DataTypeDefXsd.INT,
                    value="123",
                ),
                basyx_model.Property(
                    id_short="DoubleProp",
                    value_type=basyx_model.DataTypeDefXsd.DOUBLE,
                    value="45.67",
                ),
                basyx_model.Property(
                    id_short="BoolProp",
                    value_type=basyx_model.DataTypeDefXsd.BOOLEAN,
                    value="false",
                ),
            ],
        )

        shell = basyx_model.AssetAdministrationShell(
            id_="urn:basyx:aas:props",
            id_short="PropsShell",
            asset_information=basyx_model.AssetInformation(
                asset_kind=basyx_model.AssetKind.INSTANCE,
                global_asset_id="urn:basyx:asset:props",
            ),
            submodel=[
                basyx_model.ModelReference(
                    (basyx_model.Key(
                        type_=basyx_model.KeyTypes.SUBMODEL,
                        value=submodel.id,
                    ),)
                )
            ],
        )

        # Export from BaSyx
        buffer = io.BytesIO()
        object_store = basyx_model.DictObjectStore([shell, submodel])

        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXWriter(buffer) as writer:
            writer.write_aas(
                aas_ids=shell.id,
                object_store=object_store,
                file_store=file_store,
                write_json=False,
            )

        buffer.seek(0)

        # Import to Titan
        importer = AasxImporter()
        package = await importer.import_from_stream(buffer)

        # Verify submodel
        assert len(package.submodels) == 1
        titan_sm = package.submodels[0]
        assert titan_sm.id == submodel.id
        assert len(titan_sm.submodelElements) == 4

        # Verify properties
        props_by_idshort = {elem.id_short: elem for elem in titan_sm.submodelElements}

        string_prop = props_by_idshort["StringProp"]
        assert string_prop.value == "test"

        int_prop = props_by_idshort["IntProp"]
        assert int_prop.value == "123"

        double_prop = props_by_idshort["DoubleProp"]
        assert double_prop.value == "45.67"

        bool_prop = props_by_idshort["BoolProp"]
        assert bool_prop.value == "false"

    @pytest.mark.asyncio
    async def test_import_submodel_element_collection(self) -> None:
        """Import SubmodelElementCollection from BaSyx."""
        # Create BaSyx collection
        collection = basyx_model.SubmodelElementCollection(
            id_short="DataCollection",
            value=[
                basyx_model.Property(
                    id_short="Item1",
                    value_type=basyx_model.DataTypeDefXsd.STRING,
                    value="first",
                ),
                basyx_model.Property(
                    id_short="Item2",
                    value_type=basyx_model.DataTypeDefXsd.STRING,
                    value="second",
                ),
            ],
        )

        submodel = basyx_model.Submodel(
            id_="urn:basyx:submodel:collection",
            id_short="CollectionSubmodel",
            submodel_element=[collection],
        )

        shell = basyx_model.AssetAdministrationShell(
            id_="urn:basyx:aas:collection",
            id_short="CollectionShell",
            asset_information=basyx_model.AssetInformation(
                asset_kind=basyx_model.AssetKind.INSTANCE,
                global_asset_id="urn:basyx:asset:collection",
            ),
            submodel=[
                basyx_model.ModelReference(
                    (basyx_model.Key(
                        type_=basyx_model.KeyTypes.SUBMODEL,
                        value=submodel.id,
                    ),)
                )
            ],
        )

        # Export from BaSyx
        buffer = io.BytesIO()
        object_store = basyx_model.DictObjectStore([shell, submodel])

        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXWriter(buffer) as writer:
            writer.write_aas(
                aas_ids=shell.id,
                object_store=object_store,
                file_store=file_store,
                write_json=False,
            )

        buffer.seek(0)

        # Import to Titan
        importer = AasxImporter()
        package = await importer.import_from_stream(buffer)

        # Verify collection
        titan_sm = package.submodels[0]
        assert len(titan_sm.submodelElements) == 1

        titan_collection = titan_sm.submodelElements[0]
        assert titan_collection.id_short == "DataCollection"
        assert len(titan_collection.value) == 2

    @pytest.mark.asyncio
    async def test_import_multi_language_property(self) -> None:
        """Import MultiLanguageProperty from BaSyx."""
        # Create BaSyx MultiLanguageProperty
        mlp = basyx_model.MultiLanguageProperty(
            id_short="Description",
            value={
                basyx_model.LangStringTextType("en", "English description"),
                basyx_model.LangStringTextType("de", "Deutsche Beschreibung"),
            },
        )

        submodel = basyx_model.Submodel(
            id_="urn:basyx:submodel:mlp",
            id_short="MLPSubmodel",
            submodel_element=[mlp],
        )

        shell = basyx_model.AssetAdministrationShell(
            id_="urn:basyx:aas:mlp",
            id_short="MLPShell",
            asset_information=basyx_model.AssetInformation(
                asset_kind=basyx_model.AssetKind.INSTANCE,
                global_asset_id="urn:basyx:asset:mlp",
            ),
            submodel=[
                basyx_model.ModelReference(
                    (basyx_model.Key(
                        type_=basyx_model.KeyTypes.SUBMODEL,
                        value=submodel.id,
                    ),)
                )
            ],
        )

        # Export from BaSyx
        buffer = io.BytesIO()
        object_store = basyx_model.DictObjectStore([shell, submodel])

        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXWriter(buffer) as writer:
            writer.write_aas(
                aas_ids=shell.id,
                object_store=object_store,
                file_store=file_store,
                write_json=False,
            )

        buffer.seek(0)

        # Import to Titan
        importer = AasxImporter()
        package = await importer.import_from_stream(buffer)

        # Verify MultiLanguageProperty
        titan_sm = package.submodels[0]
        titan_mlp = titan_sm.submodelElements[0]

        assert titan_mlp.id_short == "Description"
        assert len(titan_mlp.value) == 2

        # Check language strings
        lang_dict = {ls.language: ls.text for ls in titan_mlp.value}
        assert lang_dict["en"] == "English description"
        assert lang_dict["de"] == "Deutsche Beschreibung"


class TestRoundTrip:
    """Test round-trip conversions: Titan → BaSyx → Titan."""

    @pytest.mark.asyncio
    async def test_simple_shell_round_trip(self) -> None:
        """Round-trip test: Create in Titan, export to BaSyx, import back to Titan."""
        from titan.compat.aasx import AasxExporter
        from titan.core.model import AssetAdministrationShell, AssetInformation, AssetKind

        # Create Titan shell
        original_shell = AssetAdministrationShell(
            id="urn:roundtrip:aas:1",
            idShort="RoundTripShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:roundtrip:asset:1",
            ),
        )

        # Export from Titan
        exporter = AasxExporter()
        aasx_bytes = await exporter.export_to_bytes([original_shell], [], [])

        # Import to BaSyx
        buffer = io.BytesIO(aasx_bytes)
        with basyx_aasx.AASXReader(buffer) as reader:
            basyx_object_store = basyx_model.DictObjectStore()
            reader.read_into(basyx_object_store)

        # Export from BaSyx
        basyx_buffer = io.BytesIO()
        # Find the shell ID from the object store
        shells = [obj for obj in basyx_object_store if isinstance(obj, basyx_model.AssetAdministrationShell)]
        file_store = basyx_aasx.DictSupplementaryFileContainer()
        with basyx_aasx.AASXWriter(basyx_buffer) as writer:
            writer.write_aas(
                aas_ids=shells[0].id,
                object_store=basyx_object_store,
                file_store=file_store,
                write_json=False,
            )
        basyx_buffer.seek(0)

        # Import back to Titan
        importer = AasxImporter()
        final_package = await importer.import_from_stream(basyx_buffer)

        # Verify semantic equivalence
        assert len(final_package.shells) == 1
        final_shell = final_package.shells[0]

        assert final_shell.id == original_shell.id
        assert final_shell.id_short == original_shell.idShort
        assert final_shell.asset_information.global_asset_id == original_shell.asset_information.global_asset_id

    @pytest.mark.asyncio
    async def test_submodel_round_trip(self) -> None:
        """Round-trip test with submodel."""
        from titan.compat.aasx import AasxExporter
        from titan.core.model import (
            AssetAdministrationShell,
            AssetInformation,
            AssetKind,
            DataTypeDefXsd,
            Key,
            KeyTypes,
            Property,
            Reference,
            ReferenceTypes,
            Submodel,
        )

        # Create Titan objects
        submodel = Submodel(
            id="urn:roundtrip:submodel:1",
            idShort="RoundTripSubmodel",
            submodelElements=[
                Property(
                    idShort="TestProperty",
                    valueType=DataTypeDefXsd.STRING,
                    value="round_trip_value",
                )
            ],
        )

        shell = AssetAdministrationShell(
            id="urn:roundtrip:aas:2",
            idShort="RoundTripShell2",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:roundtrip:asset:2",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value=submodel.id)],
                )
            ],
        )

        # Titan → AASX
        exporter = AasxExporter()
        aasx_bytes = await exporter.export_to_bytes([shell], [submodel], [])

        # AASX → BaSyx
        buffer = io.BytesIO(aasx_bytes)
        basyx_object_store = basyx_aasx.read_aas_xml_file(buffer)

        # BaSyx → AASX
        basyx_buffer = io.BytesIO()
        basyx_aasx.write_aas_xml_file(basyx_buffer, basyx_object_store)
        basyx_buffer.seek(0)

        # AASX → Titan
        importer = AasxImporter()
        final_package = await importer.import_from_stream(basyx_buffer)

        # Verify equivalence
        assert len(final_package.shells) == 1
        assert len(final_package.submodels) == 1

        final_shell = final_package.shells[0]
        final_submodel = final_package.submodels[0]

        assert final_shell.id == shell.id
        assert final_submodel.id == submodel.id
        assert len(final_submodel.submodelElements) == 1

        final_property = final_submodel.submodelElements[0]
        assert final_property.id_short == "TestProperty"
        assert final_property.value == "round_trip_value"

    @pytest.mark.asyncio
    async def test_complex_round_trip_preserves_structure(self) -> None:
        """Round-trip test with complex nested structure."""
        from titan.compat.aasx import AasxExporter
        from titan.core.model import (
            AssetAdministrationShell,
            AssetInformation,
            AssetKind,
            DataTypeDefXsd,
            Key,
            KeyTypes,
            Property,
            Reference,
            ReferenceTypes,
            Submodel,
            SubmodelElementCollection,
        )

        # Create complex structure
        submodel = Submodel(
            id="urn:roundtrip:submodel:complex",
            idShort="ComplexSubmodel",
            submodelElements=[
                SubmodelElementCollection(
                    idShort="OuterCollection",
                    value=[
                        Property(
                            idShort="Prop1",
                            valueType=DataTypeDefXsd.STRING,
                            value="value1",
                        ),
                        SubmodelElementCollection(
                            idShort="InnerCollection",
                            value=[
                                Property(
                                    idShort="NestedProp",
                                    valueType=DataTypeDefXsd.INT,
                                    value="42",
                                )
                            ],
                        ),
                    ],
                )
            ],
        )

        shell = AssetAdministrationShell(
            id="urn:roundtrip:aas:complex",
            idShort="ComplexShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:roundtrip:asset:complex",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[Key(type=KeyTypes.SUBMODEL, value=submodel.id)],
                )
            ],
        )

        # Full round-trip
        exporter = AasxExporter()
        aasx_bytes = await exporter.export_to_bytes([shell], [submodel], [])

        # Through BaSyx
        buffer = io.BytesIO(aasx_bytes)
        basyx_store = basyx_aasx.read_aas_xml_file(buffer)
        basyx_buffer = io.BytesIO()
        basyx_aasx.write_aas_xml_file(basyx_buffer, basyx_store)
        basyx_buffer.seek(0)

        # Back to Titan
        importer = AasxImporter()
        final_package = await importer.import_from_stream(basyx_buffer)

        # Verify nested structure preserved
        final_submodel = final_package.submodels[0]
        outer_collection = final_submodel.submodelElements[0]

        assert outer_collection.id_short == "OuterCollection"
        assert len(outer_collection.value) == 2

        # Find inner collection
        inner_collection = outer_collection.value[1]
        assert inner_collection.id_short == "InnerCollection"
        assert len(inner_collection.value) == 1

        nested_prop = inner_collection.value[0]
        assert nested_prop.id_short == "NestedProp"
        assert nested_prop.value == "42"
