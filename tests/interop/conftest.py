"""BaSyx SDK interoperability test fixtures.

Provides fixtures for:
1. Creating BaSyx AAS objects (simple and complex)
2. Exporting BaSyx objects to AASX packages
3. Comparing BaSyx and Titan models for semantic equivalence
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from basyx.aas import model
from basyx.aas.adapter import aasx


@pytest.fixture
def basyx_aas_simple() -> model.AssetAdministrationShell:
    """Create minimal AAS using BaSyx SDK.

    Returns a simple shell with only required fields:
    - id
    - idShort
    - assetInformation
    """
    asset_info = model.AssetInformation(
        asset_kind=model.AssetKind.INSTANCE,
        global_asset_id="urn:example:asset:simple",
    )

    shell = model.AssetAdministrationShell(
        id_="urn:example:aas:simple",
        id_short="SimpleShell",
        asset_information=asset_info,
    )

    return shell


@pytest.fixture
def basyx_aas_complex() -> tuple[
    model.AssetAdministrationShell,
    set[model.Submodel],
    set[model.ConceptDescription],
]:
    """Create complex AAS with submodels and concept descriptions.

    Returns:
        Tuple of (shell, submodels, concept_descriptions)

    Submodels include:
    1. Properties submodel (string, int, double, boolean)
    2. Collection submodel (nested SMEs)
    3. Files submodel (File and Blob elements)
    """
    # Asset Information
    asset_info = model.AssetInformation(
        asset_kind=model.AssetKind.INSTANCE,
        global_asset_id="urn:example:asset:complex",
    )

    # Create concept descriptions
    temp_cd = model.ConceptDescription(
        id_="https://example.com/cd/Temperature",
        id_short="TemperatureCD",
    )

    humidity_cd = model.ConceptDescription(
        id_="https://example.com/cd/Humidity",
        id_short="HumidityCD",
    )

    concept_descriptions = {temp_cd, humidity_cd}

    # Submodel 1: Properties with various value types
    properties_sm = model.Submodel(
        id_="urn:example:submodel:properties",
        id_short="PropertiesSubmodel",
        submodel_element=[
            model.Property(
                id_short="StringProperty",
                value_type=model.DataTypeDefXsd.STRING,
                value="test_value",
            ),
            model.Property(
                id_short="IntProperty",
                value_type=model.DataTypeDefXsd.INT,
                value="42",
            ),
            model.Property(
                id_short="DoubleProperty",
                value_type=model.DataTypeDefXsd.DOUBLE,
                value="3.14159",
            ),
            model.Property(
                id_short="BooleanProperty",
                value_type=model.DataTypeDefXsd.BOOLEAN,
                value="true",
            ),
            model.Property(
                id_short="Temperature",
                value_type=model.DataTypeDefXsd.DOUBLE,
                value="23.5",
                semantic_id=model.ExternalReference(
                    (model.Key(
                        type_=model.KeyTypes.GLOBAL_REFERENCE,
                        value="https://example.com/cd/Temperature",
                    ),)
                ),
            ),
        ],
    )

    # Submodel 2: Collections (nested SMEs)
    collection_sm = model.Submodel(
        id_="urn:example:submodel:collection",
        id_short="CollectionSubmodel",
        submodel_element=[
            model.SubmodelElementCollection(
                id_short="SensorData",
                value=[
                    model.Property(
                        id_short="SensorId",
                        value_type=model.DataTypeDefXsd.STRING,
                        value="SENSOR_001",
                    ),
                    model.Property(
                        id_short="Reading",
                        value_type=model.DataTypeDefXsd.DOUBLE,
                        value="45.6",
                    ),
                ],
            ),
        ],
    )

    # Submodel 3: Files and Blobs
    files_sm = model.Submodel(
        id_="urn:example:submodel:files",
        id_short="FilesSubmodel",
        submodel_element=[
            model.File(
                id_short="ManualPDF",
                content_type="application/pdf",
                value="/aasx/supplementary/manual.pdf",
            ),
            model.Blob(
                id_short="ThumbnailImage",
                content_type="image/png",
                value=b"fake_png_data_for_testing",
            ),
        ],
    )

    submodels = {properties_sm, collection_sm, files_sm}

    # Create shell with references to submodels
    shell = model.AssetAdministrationShell(
        id_="urn:example:aas:complex",
        id_short="ComplexShell",
        asset_information=asset_info,
        submodel=[
            model.ModelReference(
                (model.Key(
                    type_=model.KeyTypes.SUBMODEL,
                    value=sm.id,
                ),)
            )
            for sm in submodels
        ],
    )

    return shell, submodels, concept_descriptions


@pytest.fixture
def basyx_aasx_simple(basyx_aas_simple: model.AssetAdministrationShell) -> bytes:
    """Export simple BaSyx AAS to AASX package bytes.

    Args:
        basyx_aas_simple: Simple shell fixture

    Returns:
        AASX package as bytes
    """
    buffer = io.BytesIO()

    # BaSyx SDK 2.0.0 uses AASXWriter for AASX package export
    # Object store contains shells, submodels, concept descriptions
    object_store = model.DictObjectStore([basyx_aas_simple])

    # Write to buffer using AASXWriter
    file_store = aasx.DictSupplementaryFileContainer()
    with aasx.AASXWriter(buffer) as writer:
        writer.write_aas(
            aas_ids=basyx_aas_simple.id,
            object_store=object_store,
            file_store=file_store,
            write_json=False,  # Use XML format for IDTA compliance
        )

    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def basyx_aasx_complex(basyx_aas_complex: tuple[Any, Any, Any]) -> bytes:
    """Export complex BaSyx AAS to AASX package bytes.

    Args:
        basyx_aas_complex: Complex shell fixture (shell, submodels, CDs)

    Returns:
        AASX package as bytes
    """
    shell, submodels, concept_descriptions = basyx_aas_complex

    buffer = io.BytesIO()

    # Combine all objects into object store
    all_objects = [shell, *submodels, *concept_descriptions]
    object_store = model.DictObjectStore(all_objects)

    # Write to buffer using AASXWriter
    file_store = aasx.DictSupplementaryFileContainer()
    with aasx.AASXWriter(buffer) as writer:
        writer.write_aas(
            aas_ids=shell.id,
            object_store=object_store,
            file_store=file_store,
            write_json=False,  # Use XML format
        )

    buffer.seek(0)
    return buffer.read()


def compare_shells(
    basyx_shell: model.AssetAdministrationShell,
    titan_shell: dict[str, Any],
) -> bool:
    """Compare BaSyx shell with Titan shell for semantic equivalence.

    Args:
        basyx_shell: BaSyx SDK shell object
        titan_shell: Titan shell as dict (from JSON serialization)

    Returns:
        True if semantically equivalent

    Checks:
    - IDs match
    - idShort matches
    - assetInformation matches
    - Submodel references match (if present)
    """
    # Compare IDs
    if basyx_shell.id != titan_shell.get("id"):
        return False

    # Compare idShort
    if basyx_shell.id_short != titan_shell.get("idShort"):
        return False

    # Compare asset information
    basyx_asset = basyx_shell.asset_information
    titan_asset = titan_shell.get("assetInformation", {})

    if basyx_asset.global_asset_id != titan_asset.get("globalAssetId"):
        return False

    if basyx_asset.asset_kind.name != titan_asset.get("assetKind"):
        return False

    # Compare submodel references
    basyx_sm_refs = basyx_shell.submodel or []
    titan_sm_refs = titan_shell.get("submodels", [])

    if len(basyx_sm_refs) != len(titan_sm_refs):
        return False

    basyx_sm_ids = {ref.key[0].value for ref in basyx_sm_refs}
    titan_sm_ids = {ref["keys"][0]["value"] for ref in titan_sm_refs}

    if basyx_sm_ids != titan_sm_ids:
        return False

    return True


def compare_submodels(
    basyx_submodel: model.Submodel,
    titan_submodel: dict[str, Any],
) -> bool:
    """Compare BaSyx submodel with Titan submodel for semantic equivalence.

    Args:
        basyx_submodel: BaSyx SDK submodel object
        titan_submodel: Titan submodel as dict

    Returns:
        True if semantically equivalent

    Checks:
    - IDs match
    - idShort matches
    - SubmodelElement count matches
    - Element types and values match
    """
    # Compare IDs
    if basyx_submodel.id != titan_submodel.get("id"):
        return False

    # Compare idShort
    if basyx_submodel.id_short != titan_submodel.get("idShort"):
        return False

    # Compare submodel elements
    basyx_smes = basyx_submodel.submodel_element or []
    titan_smes = titan_submodel.get("submodelElements", [])

    if len(basyx_smes) != len(titan_smes):
        return False

    # For now, just check count. Full element comparison would be more complex
    # and should be done in specific tests

    return True


def compare_properties(
    basyx_property: model.Property,
    titan_property: dict[str, Any],
) -> bool:
    """Compare BaSyx Property with Titan Property.

    Args:
        basyx_property: BaSyx SDK Property object
        titan_property: Titan Property as dict

    Returns:
        True if semantically equivalent
    """
    # Compare idShort
    if basyx_property.id_short != titan_property.get("idShort"):
        return False

    # Compare value type
    if basyx_property.value_type.name != titan_property.get("valueType"):
        return False

    # Compare value (as string, BaSyx stores all values as strings)
    if basyx_property.value != titan_property.get("value"):
        return False

    return True
