"""IDTA-01001 Part 1 v3.0.8 + IDTA-01002 Part 2 v3.0: Domain Models.

This module provides the complete AAS domain model hierarchy following
the IDTA specification bundle, with full conformance to the JSON Schema
published at: https://github.com/admin-shell-io/aas-specs

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


# Import order matters due to forward references - StrictModel must be defined first
# ruff: noqa: E402
from titan.core.model.aas import (
    AssetAdministrationShell,
    AssetInformation,
    Resource,
)
from titan.core.model.administrative import (
    AdministrativeInformation,
    DataSpecificationIec61360,
    EmbeddedDataSpecification,
    HasDataSpecificationMixin,
    LevelTypeSpec,
)
from titan.core.model.concept_description import ConceptDescription
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

# Import after all types are defined due to forward references
from titan.core.model.environment import Environment
from titan.core.model.event_payload import EventPayload
from titan.core.model.identifiers import (
    AasSubmodelElements,
    AssetKind,
    ContentType,
    DataTypeDefXsd,
    DataTypeIec61360,
    Direction,
    EntityType,
    Identifier,
    IdShort,
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
from titan.core.model.qualifiers import (
    Extension,
    HasExtensionsMixin,
    HasQualifiersMixin,
    Qualifier,
    ValueList,
    ValueReferencePair,
)
from titan.core.model.registry import (
    AssetAdministrationShellDescriptor,
    Endpoint,
    ProtocolInformation,
    ProtocolInformationSecurityType,
    SubmodelDescriptor,
)
from titan.core.model.semantic import HasSemanticsMixin
from titan.core.model.submodel import Submodel
from titan.core.model.submodel_elements import (
    AnnotatedRelationshipElement,
    BasicEventElement,
    Blob,
    Capability,
    DataElementUnion,
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
    "ValueList",
    "ValueReferencePair",
    # Administrative
    "AdministrativeInformation",
    "DataSpecificationIec61360",
    "EmbeddedDataSpecification",
    "LevelTypeSpec",
    # SubmodelElements
    "DataElementUnion",
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
    # Environment (AASX serialization container)
    "Environment",
    # Event messaging
    "EventPayload",
]

# Rebuild Environment model to resolve forward references now that all types are loaded
Environment.model_rebuild()
