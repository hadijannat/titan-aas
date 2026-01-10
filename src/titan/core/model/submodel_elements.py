"""IDTA-01001 Part 1 v3.1.2: SubmodelElement types.

This module defines all concrete SubmodelElement types with a discriminated
union for efficient O(1) type resolution based on the modelType field.

The discriminated union pattern ensures that:
1. Validation chooses the correct model in O(1) time
2. Serialization includes the modelType discriminator
3. Type safety is preserved throughout the codebase
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, Tag

from titan.core.model import StrictModel
from titan.core.model.administrative import HasDataSpecificationMixin
from titan.core.model.descriptions import (
    LangStringTextType,
    MultiLanguageTextType,
)
from titan.core.model.identifiers import (
    AasSubmodelElements,
    ContentType,
    DataTypeDefXsd,
    Direction,
    EntityType,
    IdShort,
    PathType,
    Reference,
    StateOfEvent,
    ValueDataType,
)
from titan.core.model.qualifiers import HasExtensionsMixin, HasQualifiersMixin
from titan.core.model.semantic import HasSemanticsMixin

# -----------------------------------------------------------------------------
# Base classes for SubmodelElement hierarchy
# -----------------------------------------------------------------------------


class SubmodelElementBase(
    HasSemanticsMixin,
    HasQualifiersMixin,
    HasExtensionsMixin,
    HasDataSpecificationMixin,
):
    """Base class for all SubmodelElement types.

    Combines all the standard mixins that SubmodelElements can have.
    Subclasses must define a Literal modelType for the discriminated union.
    """

    id_short: IdShort | None = Field(
        default=None,
        alias="idShort",
        description="Short identifier of the element (unique within parent)",
    )
    display_name: list[LangStringTextType] | None = Field(
        default=None,
        alias="displayName",
        description="Display name in multiple languages",
    )
    description: list[LangStringTextType] | None = Field(
        default=None, description="Description in multiple languages"
    )
    category: str | None = Field(
        default=None,
        description="Category of the element (CONSTANT, PARAMETER, VARIABLE)",
    )


# -----------------------------------------------------------------------------
# DataElement types
# -----------------------------------------------------------------------------


class Property(SubmodelElementBase):
    """A data element with a single value.

    Properties are the most common SubmodelElement type, representing
    simple typed values like temperatures, speeds, or identifiers.
    """

    model_type: Literal["Property"] = Field(
        default="Property", alias="modelType", description="Model type discriminator"
    )
    value_type: DataTypeDefXsd = Field(
        ..., alias="valueType", description="XSD data type of the value"
    )
    value: ValueDataType | None = Field(default=None, description="The actual value")
    value_id: Reference | None = Field(
        default=None,
        alias="valueId",
        description="Reference to the value definition",
    )


class MultiLanguageProperty(SubmodelElementBase):
    """A data element with values in multiple languages.

    Used for text content that needs to be localized, such as
    descriptions, labels, or instructions.
    """

    model_type: Literal["MultiLanguageProperty"] = Field(
        default="MultiLanguageProperty",
        alias="modelType",
        description="Model type discriminator",
    )
    value: MultiLanguageTextType | None = Field(
        default=None, description="The multi-language value"
    )
    value_id: Reference | None = Field(
        default=None,
        alias="valueId",
        description="Reference to the value definition",
    )


class Range(SubmodelElementBase):
    """A data element representing a range with min and max values.

    Used for specifications like operating temperature ranges,
    voltage tolerances, or dimension limits.
    """

    model_type: Literal["Range"] = Field(
        default="Range", alias="modelType", description="Model type discriminator"
    )
    value_type: DataTypeDefXsd = Field(
        ..., alias="valueType", description="XSD data type of the min/max values"
    )
    min: ValueDataType | None = Field(default=None, description="Minimum value")
    max: ValueDataType | None = Field(default=None, description="Maximum value")


class Blob(SubmodelElementBase):
    """A data element containing binary data.

    Used for embedded binary content like images, PDF documents,
    or other non-text data.
    """

    model_type: Literal["Blob"] = Field(
        default="Blob", alias="modelType", description="Model type discriminator"
    )
    content_type: ContentType = Field(
        ..., alias="contentType", description="MIME type of the content"
    )
    value: str | None = Field(default=None, description="Base64-encoded binary content")


class File(SubmodelElementBase):
    """A data element referencing an external file.

    Used for files that are either embedded in an AASX package
    or accessible via URL.
    """

    model_type: Literal["File"] = Field(
        default="File", alias="modelType", description="Model type discriminator"
    )
    content_type: ContentType = Field(..., alias="contentType", description="MIME type of the file")
    value: PathType | None = Field(default=None, description="Path or URL to the file")


class ReferenceElement(SubmodelElementBase):
    """A data element containing a reference to another element.

    Used to create links between elements within or across
    Asset Administration Shells.
    """

    model_type: Literal["ReferenceElement"] = Field(
        default="ReferenceElement",
        alias="modelType",
        description="Model type discriminator",
    )
    value: Reference | None = Field(default=None, description="The reference value")


# -----------------------------------------------------------------------------
# Relationship types
# -----------------------------------------------------------------------------


class RelationshipElement(SubmodelElementBase):
    """A relationship between two elements.

    Used to express semantic relationships like "is composed of",
    "is similar to", or custom domain-specific relationships.
    """

    model_type: Literal["RelationshipElement"] = Field(
        default="RelationshipElement",
        alias="modelType",
        description="Model type discriminator",
    )
    first: Reference = Field(..., description="Reference to the first element")
    second: Reference = Field(..., description="Reference to the second element")


class AnnotatedRelationshipElement(SubmodelElementBase):
    """A relationship with additional annotations.

    Extends RelationshipElement with the ability to attach
    SubmodelElements as annotations to provide more context.
    """

    model_type: Literal["AnnotatedRelationshipElement"] = Field(
        default="AnnotatedRelationshipElement",
        alias="modelType",
        description="Model type discriminator",
    )
    first: Reference = Field(..., description="Reference to the first element")
    second: Reference = Field(..., description="Reference to the second element")
    annotations: list[SubmodelElementUnion] | None = Field(
        default=None, description="Annotations on the relationship"
    )


# -----------------------------------------------------------------------------
# Collection types
# -----------------------------------------------------------------------------


class SubmodelElementCollection(SubmodelElementBase):
    """A collection of SubmodelElements.

    Used to group related elements together, similar to a folder
    or object structure.
    """

    model_type: Literal["SubmodelElementCollection"] = Field(
        default="SubmodelElementCollection",
        alias="modelType",
        description="Model type discriminator",
    )
    value: list[SubmodelElementUnion] | None = Field(
        default=None, description="The contained SubmodelElements"
    )


class SubmodelElementList(SubmodelElementBase):
    """An ordered list of SubmodelElements of the same type.

    Used for arrays or sequences where order matters and all
    elements share the same semantics.
    """

    model_type: Literal["SubmodelElementList"] = Field(
        default="SubmodelElementList",
        alias="modelType",
        description="Model type discriminator",
    )
    order_relevant: bool = Field(
        default=True,
        alias="orderRelevant",
        description="Whether the order of elements matters",
    )
    semantic_id_list_element: Reference | None = Field(
        default=None,
        alias="semanticIdListElement",
        description="SemanticId for all list elements",
    )
    type_value_list_element: AasSubmodelElements = Field(
        ...,
        alias="typeValueListElement",
        description="Type of the list elements",
    )
    value_type_list_element: DataTypeDefXsd | None = Field(
        default=None,
        alias="valueTypeListElement",
        description="Value type for Property/Range list elements",
    )
    value: list[SubmodelElementUnion] | None = Field(
        default=None, description="The contained SubmodelElements"
    )


# -----------------------------------------------------------------------------
# Entity
# -----------------------------------------------------------------------------


class Entity(SubmodelElementBase):
    """A self-contained entity within the AAS ecosystem.

    Entities can represent physical assets, software components,
    or other identifiable things that have their own lifecycle.
    """

    model_type: Literal["Entity"] = Field(
        default="Entity", alias="modelType", description="Model type discriminator"
    )
    entity_type: EntityType = Field(..., alias="entityType", description="Type of entity")
    global_asset_id: Annotated[str, Field(min_length=1, max_length=2000)] | None = Field(
        default=None,
        alias="globalAssetId",
        description="Global identifier of the entity's asset",
    )
    specific_asset_ids: list[SpecificAssetId] | None = Field(
        default=None,
        alias="specificAssetIds",
        description="Specific identifiers of the entity's asset",
    )
    statements: list[SubmodelElementUnion] | None = Field(
        default=None, description="Statements about the entity"
    )


class SpecificAssetId(HasSemanticsMixin):
    """A specific identifier for an asset.

    Used to provide domain-specific identifiers like serial numbers,
    batch numbers, or customer part numbers.
    """

    name: Annotated[str, Field(min_length=1, max_length=64)] = Field(
        ..., description="Name of the specific asset ID"
    )
    value: Annotated[str, Field(min_length=1, max_length=2000)] = Field(
        ..., description="Value of the specific asset ID"
    )
    subject_id: Reference | None = Field(
        default=None,
        alias="subjectId",
        description="Reference to the subject that defined this ID",
    )
    external_subject_id: Reference | None = Field(
        default=None,
        alias="externalSubjectId",
        description="External reference to the subject",
    )


# -----------------------------------------------------------------------------
# Event types
# -----------------------------------------------------------------------------


class BasicEventElement(SubmodelElementBase):
    """A basic event element for publishing/subscribing to events.

    Used to define event sources and sinks in the AAS for
    integration with messaging systems.
    """

    model_type: Literal["BasicEventElement"] = Field(
        default="BasicEventElement",
        alias="modelType",
        description="Model type discriminator",
    )
    observed: Reference = Field(..., description="Reference to the observed element")
    direction: Direction = Field(..., description="Direction of the event (input/output)")
    state: StateOfEvent = Field(..., description="State of the event (on/off)")
    message_topic: Annotated[str, Field(max_length=255)] | None = Field(
        default=None, alias="messageTopic", description="Topic for the event messages"
    )
    message_broker: Reference | None = Field(
        default=None,
        alias="messageBroker",
        description="Reference to the message broker",
    )
    last_update: Annotated[str, Field(max_length=50)] | None = Field(
        default=None, alias="lastUpdate", description="Timestamp of last update"
    )
    min_interval: Annotated[str, Field(max_length=50)] | None = Field(
        default=None, alias="minInterval", description="Minimum interval between events"
    )
    max_interval: Annotated[str, Field(max_length=50)] | None = Field(
        default=None, alias="maxInterval", description="Maximum interval between events"
    )


# -----------------------------------------------------------------------------
# Operation and Capability
# -----------------------------------------------------------------------------


class OperationVariable(StrictModel):
    """A variable in an operation's input/output/inoutput list."""

    value: SubmodelElementUnion = Field(
        ..., description="The SubmodelElement describing the variable"
    )


class Operation(SubmodelElementBase):
    """An operation that can be invoked.

    Operations define callable functionality with typed
    input, output, and in-out parameters.
    """

    model_type: Literal["Operation"] = Field(
        default="Operation", alias="modelType", description="Model type discriminator"
    )
    input_variables: list[OperationVariable] | None = Field(
        default=None, alias="inputVariables", description="Input parameters"
    )
    output_variables: list[OperationVariable] | None = Field(
        default=None, alias="outputVariables", description="Output parameters"
    )
    inoutput_variables: list[OperationVariable] | None = Field(
        default=None,
        alias="inoutputVariables",
        description="Parameters that are both input and output",
    )


class Capability(SubmodelElementBase):
    """A capability that an asset provides.

    Capabilities describe what an asset can do without specifying
    the concrete implementation or operation.
    """

    model_type: Literal["Capability"] = Field(
        default="Capability",
        alias="modelType",
        description="Model type discriminator",
    )


# -----------------------------------------------------------------------------
# Discriminated Union
# -----------------------------------------------------------------------------


def _submodel_element_discriminator(value: Any) -> str | None:
    """Resolve modelType for discriminated union, supporting aliases in input payloads."""
    if isinstance(value, Mapping):
        model_type = value.get("modelType") or value.get("model_type")
        return model_type if isinstance(model_type, str) else None
    return getattr(value, "model_type", None)


# Forward reference for recursive types
SubmodelElementUnion = Annotated[
    Annotated[Property, Tag("Property")]
    | Annotated[MultiLanguageProperty, Tag("MultiLanguageProperty")]
    | Annotated[Range, Tag("Range")]
    | Annotated[Blob, Tag("Blob")]
    | Annotated[File, Tag("File")]
    | Annotated[ReferenceElement, Tag("ReferenceElement")]
    | Annotated[RelationshipElement, Tag("RelationshipElement")]
    | Annotated[AnnotatedRelationshipElement, Tag("AnnotatedRelationshipElement")]
    | Annotated[SubmodelElementCollection, Tag("SubmodelElementCollection")]
    | Annotated[SubmodelElementList, Tag("SubmodelElementList")]
    | Annotated[Entity, Tag("Entity")]
    | Annotated[BasicEventElement, Tag("BasicEventElement")]
    | Annotated[Operation, Tag("Operation")]
    | Annotated[Capability, Tag("Capability")],
    Discriminator(_submodel_element_discriminator),
]

# Update forward references for recursive models
AnnotatedRelationshipElement.model_rebuild()
SubmodelElementCollection.model_rebuild()
SubmodelElementList.model_rebuild()
Entity.model_rebuild()
OperationVariable.model_rebuild()


# Type alias for convenience
SubmodelElement = SubmodelElementUnion
