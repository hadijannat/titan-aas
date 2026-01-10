"""IDTA-01001 Part 1 v3.1.2: Identifiers, References, and Key Types.

This module defines the fundamental identification and referencing constructs
used throughout the AAS metamodel.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel


class KeyTypes(str, Enum):
    """Enumeration of key types for Reference keys."""

    # AAS Identifiables
    ASSET_ADMINISTRATION_SHELL = "AssetAdministrationShell"
    SUBMODEL = "Submodel"
    CONCEPT_DESCRIPTION = "ConceptDescription"

    # AAS Referables (non-identifiable)
    ANNOTATED_RELATIONSHIP_ELEMENT = "AnnotatedRelationshipElement"
    BASIC_EVENT_ELEMENT = "BasicEventElement"
    BLOB = "Blob"
    CAPABILITY = "Capability"
    DATA_ELEMENT = "DataElement"
    ENTITY = "Entity"
    EVENT_ELEMENT = "EventElement"
    FILE = "File"
    FRAGMENT_REFERENCE = "FragmentReference"
    GLOBAL_REFERENCE = "GlobalReference"
    IDENTIFIABLE = "Identifiable"
    MULTI_LANGUAGE_PROPERTY = "MultiLanguageProperty"
    OPERATION = "Operation"
    PROPERTY = "Property"
    RANGE = "Range"
    REFERABLE = "Referable"
    REFERENCE_ELEMENT = "ReferenceElement"
    RELATIONSHIP_ELEMENT = "RelationshipElement"
    SUBMODEL_ELEMENT = "SubmodelElement"
    SUBMODEL_ELEMENT_COLLECTION = "SubmodelElementCollection"
    SUBMODEL_ELEMENT_LIST = "SubmodelElementList"


class ReferenceTypes(str, Enum):
    """Type of a Reference."""

    EXTERNAL_REFERENCE = "ExternalReference"
    MODEL_REFERENCE = "ModelReference"


class AasSubmodelElements(str, Enum):
    """Enumeration of all concrete SubmodelElement types (modelType discriminator)."""

    ANNOTATED_RELATIONSHIP_ELEMENT = "AnnotatedRelationshipElement"
    BASIC_EVENT_ELEMENT = "BasicEventElement"
    BLOB = "Blob"
    CAPABILITY = "Capability"
    ENTITY = "Entity"
    FILE = "File"
    MULTI_LANGUAGE_PROPERTY = "MultiLanguageProperty"
    OPERATION = "Operation"
    PROPERTY = "Property"
    RANGE = "Range"
    REFERENCE_ELEMENT = "ReferenceElement"
    RELATIONSHIP_ELEMENT = "RelationshipElement"
    SUBMODEL_ELEMENT_COLLECTION = "SubmodelElementCollection"
    SUBMODEL_ELEMENT_LIST = "SubmodelElementList"


class EntityType(str, Enum):
    """Type of an Entity."""

    CO_MANAGED_ENTITY = "CoManagedEntity"
    SELF_MANAGED_ENTITY = "SelfManagedEntity"


class Direction(str, Enum):
    """Direction of a BasicEventElement."""

    INPUT = "input"
    OUTPUT = "output"


class StateOfEvent(str, Enum):
    """State of a BasicEventElement."""

    ON = "on"
    OFF = "off"


class DataTypeDefXsd(str, Enum):
    """XSD data types for Property values."""

    XS_ANY_URI = "xs:anyURI"
    XS_BASE64_BINARY = "xs:base64Binary"
    XS_BOOLEAN = "xs:boolean"
    XS_BYTE = "xs:byte"
    XS_DATE = "xs:date"
    XS_DATE_TIME = "xs:dateTime"
    XS_DECIMAL = "xs:decimal"
    XS_DOUBLE = "xs:double"
    XS_DURATION = "xs:duration"
    XS_FLOAT = "xs:float"
    XS_G_DAY = "xs:gDay"
    XS_G_MONTH = "xs:gMonth"
    XS_G_MONTH_DAY = "xs:gMonthDay"
    XS_G_YEAR = "xs:gYear"
    XS_G_YEAR_MONTH = "xs:gYearMonth"
    XS_HEX_BINARY = "xs:hexBinary"
    XS_INT = "xs:int"
    XS_INTEGER = "xs:integer"
    XS_LONG = "xs:long"
    XS_NEGATIVE_INTEGER = "xs:negativeInteger"
    XS_NON_NEGATIVE_INTEGER = "xs:nonNegativeInteger"
    XS_NON_POSITIVE_INTEGER = "xs:nonPositiveInteger"
    XS_POSITIVE_INTEGER = "xs:positiveInteger"
    XS_SHORT = "xs:short"
    XS_STRING = "xs:string"
    XS_TIME = "xs:time"
    XS_UNSIGNED_BYTE = "xs:unsignedByte"
    XS_UNSIGNED_INT = "xs:unsignedInt"
    XS_UNSIGNED_LONG = "xs:unsignedLong"
    XS_UNSIGNED_SHORT = "xs:unsignedShort"


class DataTypeIec61360(str, Enum):
    """IEC 61360 data types for DataSpecificationIec61360."""

    BLOB = "BLOB"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    FILE = "FILE"
    HTML = "HTML"
    INTEGER_COUNT = "INTEGER_COUNT"
    INTEGER_CURRENCY = "INTEGER_CURRENCY"
    INTEGER_MEASURE = "INTEGER_MEASURE"
    IRDI = "IRDI"
    IRI = "IRI"
    RATIONAL = "RATIONAL"
    RATIONAL_MEASURE = "RATIONAL_MEASURE"
    REAL_COUNT = "REAL_COUNT"
    REAL_CURRENCY = "REAL_CURRENCY"
    REAL_MEASURE = "REAL_MEASURE"
    STRING = "STRING"
    STRING_TRANSLATABLE = "STRING_TRANSLATABLE"
    TIME = "TIME"
    TIMESTAMP = "TIMESTAMP"


class LevelType(str, Enum):
    """Level type for DataSpecificationIec61360."""

    MIN = "min"
    MAX = "max"
    NOM = "nom"
    TYP = "typ"


class AssetKind(str, Enum):
    """Kind of an Asset."""

    TYPE = "Type"
    INSTANCE = "Instance"
    NOT_APPLICABLE = "NotApplicable"


class ModellingKind(str, Enum):
    """Modelling kind for Submodels."""

    TEMPLATE = "Template"
    INSTANCE = "Instance"


class QualifierKind(str, Enum):
    """Kind of a Qualifier."""

    CONCEPT_QUALIFIER = "ConceptQualifier"
    TEMPLATE_QUALIFIER = "TemplateQualifier"
    VALUE_QUALIFIER = "ValueQualifier"


# -----------------------------------------------------------------------------
# Key and Reference
# -----------------------------------------------------------------------------


class Key(StrictModel):
    """A key in a Reference."""

    type: KeyTypes = Field(..., description="Type of the key")
    value: Annotated[str, Field(min_length=1, max_length=2000)] = Field(
        ..., description="The value of the key"
    )


class Reference(StrictModel):
    """A reference to an element.

    References can be external (pointing outside the AAS ecosystem) or
    model references (pointing to elements within the AAS ecosystem).
    """

    type: ReferenceTypes = Field(..., description="Type of the reference")
    keys: Annotated[list[Key], Field(min_length=1)] = Field(
        ..., description="List of keys that make up the reference"
    )
    referred_semantic_id: Reference | None = Field(
        default=None,
        alias="referredSemanticId",
        description="SemanticId of the referred element",
    )

    @property
    def is_external(self) -> bool:
        """Check if this is an external reference."""
        return self.type == ReferenceTypes.EXTERNAL_REFERENCE

    @property
    def is_model_reference(self) -> bool:
        """Check if this is a model reference."""
        return self.type == ReferenceTypes.MODEL_REFERENCE


# Type aliases for semantic clarity
Identifier = Annotated[str, Field(min_length=1, max_length=2000)]
IdShort = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")]
ContentType = Annotated[str, Field(min_length=1, max_length=100)]
PathType = Annotated[str, Field(min_length=1, max_length=2000)]
BlobType = bytes
ValueDataType = str
