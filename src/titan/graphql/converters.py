"""Type converters from Pydantic models to GraphQL Strawberry types.

Converts between:
- titan.core.model.AssetAdministrationShell → graphql.schema.Shell
- titan.core.model.Submodel → graphql.schema.Submodel
- Related nested types (Reference, Key, etc.)
"""

from __future__ import annotations

from typing import Any

from titan.core.model import AssetAdministrationShell
from titan.core.model import Submodel as PydanticSubmodel
from titan.graphql.schema import (
    AdministrativeInfo,
    AssetInformation,
    AssetKind,
    Blob,
    ConceptDescription,
    File,
    Key,
    KeyType,
    LangString,
    ModellingKind,
    MultiLanguageProperty,
    Property,
    Qualifier,
    Range,
    Reference,
    Shell,
    Submodel,
    SubmodelElement,
)


def shell_to_graphql(model: AssetAdministrationShell | None) -> Shell | None:
    """Convert Pydantic AssetAdministrationShell to GraphQL Shell.

    Args:
        model: Pydantic AAS model or None

    Returns:
        GraphQL Shell type or None
    """
    if model is None:
        return None

    # Convert asset information
    asset_info = AssetInformation(
        asset_kind=_convert_asset_kind(model.asset_information.asset_kind),
        global_asset_id=model.asset_information.global_asset_id,
        asset_type=model.asset_information.asset_type,
    )

    return Shell(
        id=model.id,
        id_short=model.id_short,
        description=_convert_descriptions(model.description),
        asset_information=asset_info,
        administration=_convert_administration(model.administration),
        derived_from=_convert_reference(model.derived_from),
    )


def submodel_to_graphql(model: PydanticSubmodel | None) -> Submodel | None:
    """Convert Pydantic Submodel to GraphQL Submodel.

    Args:
        model: Pydantic Submodel model or None

    Returns:
        GraphQL Submodel type or None
    """
    if model is None:
        return None

    return Submodel(
        id=model.id,
        id_short=model.id_short,
        description=_convert_descriptions(model.description),
        semantic_id=_convert_reference(model.semantic_id),
        kind=_convert_modelling_kind(model.kind),
        administration=_convert_administration(model.administration),
        submodel_elements=_convert_submodel_elements(model.submodel_elements),
    )


def _convert_asset_kind(kind: Any | None) -> AssetKind:
    """Convert Pydantic AssetKind to GraphQL AssetKind."""
    if kind is None:
        return AssetKind.INSTANCE

    kind_str = str(kind.value) if hasattr(kind, "value") else str(kind)
    mapping = {
        "Type": AssetKind.TYPE,
        "Instance": AssetKind.INSTANCE,
        "NotApplicable": AssetKind.NOT_APPLICABLE,
    }
    return mapping.get(kind_str, AssetKind.INSTANCE)


def _convert_modelling_kind(kind: Any | None) -> ModellingKind | None:
    """Convert Pydantic ModellingKind to GraphQL ModellingKind."""
    if kind is None:
        return None

    kind_str = str(kind.value) if hasattr(kind, "value") else str(kind)
    mapping = {
        "Template": ModellingKind.TEMPLATE,
        "Instance": ModellingKind.INSTANCE,
    }
    return mapping.get(kind_str)


def _convert_descriptions(
    descriptions: list[Any] | None,
) -> list[LangString] | None:
    """Convert Pydantic description list to GraphQL LangString list."""
    if not descriptions:
        return None

    result = []
    for desc in descriptions:
        if hasattr(desc, "language") and hasattr(desc, "text"):
            result.append(LangString(language=desc.language, text=desc.text))
    return result if result else None


def _convert_reference(ref: Any | None) -> Reference | None:
    """Convert Pydantic Reference to GraphQL Reference."""
    if ref is None:
        return None

    if not hasattr(ref, "keys"):
        return None

    keys = []
    for key in ref.keys or []:
        key_type = _convert_key_type(key.type)
        if key_type:
            keys.append(Key(type=key_type, value=key.value))

    if not keys:
        return None

    ref_type = str(ref.type) if hasattr(ref, "type") else "ModelReference"
    return Reference(type=ref_type, keys=keys)


def _convert_key_type(key_type: Any | None) -> KeyType | None:
    """Convert Pydantic KeyType to GraphQL KeyType."""
    if key_type is None:
        return None

    type_str = str(key_type.value) if hasattr(key_type, "value") else str(key_type)
    mapping = {
        "AssetAdministrationShell": KeyType.ASSET_ADMINISTRATION_SHELL,
        "Submodel": KeyType.SUBMODEL,
        "ConceptDescription": KeyType.CONCEPT_DESCRIPTION,
        "GlobalReference": KeyType.GLOBAL_REFERENCE,
        "SubmodelElement": KeyType.SUBMODEL_ELEMENT,
    }
    return mapping.get(type_str)


def _convert_administration(admin: Any | None) -> AdministrativeInfo | None:
    """Convert Pydantic AdministrativeInformation to GraphQL AdministrativeInfo."""
    if admin is None:
        return None

    return AdministrativeInfo(
        version=getattr(admin, "version", None),
        revision=getattr(admin, "revision", None),
    )


def _convert_qualifiers(qualifiers: list[Any] | None) -> list[Qualifier] | None:
    """Convert Pydantic Qualifiers to GraphQL Qualifiers."""
    if not qualifiers:
        return None

    result = []
    for q in qualifiers:
        result.append(
            Qualifier(
                type=getattr(q, "type", ""),
                value_type=str(getattr(q, "value_type", "xs:string")),
                value=getattr(q, "value", None),
            )
        )
    return result if result else None


def _convert_submodel_elements(
    elements: list[Any] | None,
) -> list[SubmodelElement] | None:
    """Convert Pydantic SubmodelElements to GraphQL SubmodelElement union."""
    if not elements:
        return None

    result: list[SubmodelElement] = []
    for elem in elements:
        converted = _convert_single_element(elem)
        if converted is not None:
            result.append(converted)
    return result if result else None


def _convert_single_element(elem: Any) -> SubmodelElement | None:
    """Convert a single Pydantic SubmodelElement to GraphQL type."""
    if elem is None:
        return None

    model_type = getattr(elem, "model_type", None)
    if model_type is None:
        # Try to infer from class name
        model_type = type(elem).__name__

    id_short = getattr(elem, "id_short", "")
    description = _convert_descriptions(getattr(elem, "description", None))
    semantic_id = _convert_reference(getattr(elem, "semantic_id", None))
    qualifiers = _convert_qualifiers(getattr(elem, "qualifiers", None))

    if model_type == "Property":
        value_type = getattr(elem, "value_type", "xs:string")
        if hasattr(value_type, "value"):
            value_type = value_type.value
        return Property(
            id_short=id_short,
            value_type=str(value_type),
            value=getattr(elem, "value", None),
            description=description,
            semantic_id=semantic_id,
            qualifiers=qualifiers,
        )

    elif model_type == "MultiLanguageProperty":
        mlp_value = getattr(elem, "value", None)
        lang_strings = _convert_descriptions(mlp_value) if mlp_value else None
        return MultiLanguageProperty(
            id_short=id_short,
            value=lang_strings,
            description=description,
            semantic_id=semantic_id,
            qualifiers=qualifiers,
        )

    elif model_type == "Range":
        value_type = getattr(elem, "value_type", "xs:double")
        if hasattr(value_type, "value"):
            value_type = value_type.value
        return Range(
            id_short=id_short,
            value_type=str(value_type),
            min=getattr(elem, "min", None),
            max=getattr(elem, "max", None),
            description=description,
            semantic_id=semantic_id,
            qualifiers=qualifiers,
        )

    elif model_type == "Blob":
        return Blob(
            id_short=id_short,
            content_type=getattr(elem, "content_type", "application/octet-stream"),
            value=getattr(elem, "value", None),
            description=description,
            semantic_id=semantic_id,
            qualifiers=qualifiers,
        )

    elif model_type == "File":
        return File(
            id_short=id_short,
            content_type=getattr(elem, "content_type", "application/octet-stream"),
            value=getattr(elem, "value", None),
            description=description,
            semantic_id=semantic_id,
            qualifiers=qualifiers,
        )

    # Default to Property for unknown types
    return Property(
        id_short=id_short,
        value=str(elem) if elem else None,
        description=description,
        semantic_id=semantic_id,
        qualifiers=qualifiers,
    )


# -----------------------------------------------------------------------------
# Reverse Converters: GraphQL Input → Pydantic Domain Models
# -----------------------------------------------------------------------------


def shell_from_input(input_data: Any) -> AssetAdministrationShell:
    """Convert GraphQL ShellInput to Pydantic AssetAdministrationShell.

    Args:
        input_data: GraphQL ShellInput

    Returns:
        Pydantic AssetAdministrationShell model
    """
    from titan.core.model import AssetInformation as PydanticAssetInfo
    from titan.core.model import AssetKind as PydanticAssetKind

    # Convert AssetKind
    asset_kind_map = {
        AssetKind.TYPE: PydanticAssetKind.TYPE,
        AssetKind.INSTANCE: PydanticAssetKind.INSTANCE,
        AssetKind.NOT_APPLICABLE: PydanticAssetKind.NOT_APPLICABLE,
    }
    pydantic_asset_kind = asset_kind_map.get(input_data.asset_kind, PydanticAssetKind.INSTANCE)

    # Create asset information (use camelCase field names)
    asset_info = PydanticAssetInfo(
        assetKind=pydantic_asset_kind,
        globalAssetId=input_data.global_asset_id,
    )

    # Create shell (use camelCase field names)
    return AssetAdministrationShell(
        id=input_data.id,
        idShort=input_data.id_short,
        assetInformation=asset_info,
    )


def submodel_from_input(input_data: Any) -> PydanticSubmodel:
    """Convert GraphQL SubmodelInput to Pydantic Submodel.

    Args:
        input_data: GraphQL SubmodelInput

    Returns:
        Pydantic Submodel model
    """
    return PydanticSubmodel(
        id=input_data.id,
        idShort=input_data.id_short,
        submodelElements=[],
    )


def concept_description_to_graphql(
    model: Any | None,
) -> ConceptDescription | None:
    """Convert Pydantic ConceptDescription to GraphQL ConceptDescription.

    Args:
        model: Pydantic ConceptDescription model or None

    Returns:
        GraphQL ConceptDescription type or None
    """
    if model is None:
        return None

    return ConceptDescription(
        id=model.id,
        id_short=getattr(model, "id_short", None) or getattr(model, "idShort", None),
        description=_convert_descriptions(getattr(model, "description", None)),
    )


def concept_description_from_input(input_data: Any) -> Any:
    """Convert GraphQL ConceptDescriptionInput to Pydantic ConceptDescription.

    Args:
        input_data: GraphQL ConceptDescriptionInput

    Returns:
        Pydantic ConceptDescription model
    """
    from titan.core.model import ConceptDescription as PydanticConceptDescription

    return PydanticConceptDescription(
        id=input_data.id,
        idShort=input_data.id_short,
    )
