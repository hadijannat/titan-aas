"""IDTA-01001 Part 1 v3.1.2 + IDTA-01002 Part 2 v3.1.1: Domain Models.

This module provides the complete AAS domain model hierarchy following
the IDTA Release 25-01 specification bundle.

All models use Pydantic v2 with strict mode for validation.
SubmodelElements use a discriminated union on modelType for O(1) type resolution.
"""

from pydantic import BaseModel


class StrictModel(BaseModel):
    """Base model with strict validation for all AAS domain models.

    Note: We use extra="forbid" to prevent unknown fields, but we don't use
    strict=True because it prevents string-to-enum coercion which is needed
    for JSON parsing. Type safety is still enforced via type hints.
    """

    model_config = {
        "extra": "forbid",
        "populate_by_name": True,
        "validate_default": True,
    }


# Import order matters due to forward references
from titan.core.model.identifiers import (
    AasSubmodelElements,
    AssetKind,
    ContentType,
    DataTypeDefXsd,
    DataTypeIec61360,
    Direction,
    EntityType,
    IdShort,
    Identifier,
    Key,
    KeyTypes,
    LevelType,
    ModellingKind,
    PathType,
    QualifierKind,
    Reference,
    ReferenceTypes,
    StateOfEvent,
    ValueDataType,
)
from titan.core.model.descriptions import (
    LangStringDefinitionType,
    LangStringNameType,
    LangStringPreferredNameType,
    LangStringShortNameType,
    LangStringTextType,
    MultiLanguageDefinitionType,
    MultiLanguageNameType,
    MultiLanguagePreferredNameType,
    MultiLanguageShortNameType,
    MultiLanguageTextType,
)
from titan.core.model.semantic import HasSemanticsMixin
from titan.core.model.qualifiers import (
    Extension,
    HasExtensionsMixin,
    HasQualifiersMixin,
    Qualifier,
    ValueReferencePair,
)
from titan.core.model.administrative import (
    AdministrativeInformation,
    DataSpecificationIec61360,
    EmbeddedDataSpecification,
    HasDataSpecificationMixin,
    LevelTypeSpec,
)
from titan.core.model.submodel_elements import (
    AnnotatedRelationshipElement,
    BasicEventElement,
    Blob,
    Capability,
    Entity,
    File,
    MultiLanguageProperty,
    Operation,
    OperationVariable,
    Property,
    Range,
    ReferenceElement,
    RelationshipElement,
    SpecificAssetId,
    SubmodelElement,
    SubmodelElementBase,
    SubmodelElementCollection,
    SubmodelElementList,
    SubmodelElementUnion,
)
from titan.core.model.submodel import Submodel
from titan.core.model.aas import (
    AssetAdministrationShell,
    AssetInformation,
    Resource,
)
from titan.core.model.concept_description import ConceptDescription
from titan.core.model.registry import (
    AssetAdministrationShellDescriptor,
    Endpoint,
    ProtocolInformation,
    ProtocolInformationSecurityType,
    SubmodelDescriptor,
)


__all__ = [
    # Base
    "StrictModel",
    # Enums
    "AasSubmodelElements",
    "AssetKind",
    "DataTypeDefXsd",
    "DataTypeIec61360",
    "Direction",
    "EntityType",
    "KeyTypes",
    "LevelType",
    "ModellingKind",
    "ProtocolInformationSecurityType",
    "QualifierKind",
    "ReferenceTypes",
    "StateOfEvent",
    # Type aliases
    "ContentType",
    "IdShort",
    "Identifier",
    "PathType",
    "ValueDataType",
    # Core types
    "Key",
    "Reference",
    # Lang strings
    "LangStringDefinitionType",
    "LangStringNameType",
    "LangStringPreferredNameType",
    "LangStringShortNameType",
    "LangStringTextType",
    "MultiLanguageDefinitionType",
    "MultiLanguageNameType",
    "MultiLanguagePreferredNameType",
    "MultiLanguageShortNameType",
    "MultiLanguageTextType",
    # Mixins
    "HasDataSpecificationMixin",
    "HasExtensionsMixin",
    "HasQualifiersMixin",
    "HasSemanticsMixin",
    # Qualifiers/Extensions
    "Extension",
    "Qualifier",
    "ValueReferencePair",
    # Administrative
    "AdministrativeInformation",
    "DataSpecificationIec61360",
    "EmbeddedDataSpecification",
    "LevelTypeSpec",
    # SubmodelElements
    "AnnotatedRelationshipElement",
    "BasicEventElement",
    "Blob",
    "Capability",
    "Entity",
    "File",
    "MultiLanguageProperty",
    "Operation",
    "OperationVariable",
    "Property",
    "Range",
    "ReferenceElement",
    "RelationshipElement",
    "SpecificAssetId",
    "SubmodelElement",
    "SubmodelElementBase",
    "SubmodelElementCollection",
    "SubmodelElementList",
    "SubmodelElementUnion",
    # Submodel
    "Submodel",
    # AAS
    "AssetAdministrationShell",
    "AssetInformation",
    "Resource",
    # ConceptDescription
    "ConceptDescription",
    # Registry
    "AssetAdministrationShellDescriptor",
    "Endpoint",
    "ProtocolInformation",
    "SubmodelDescriptor",
]
