"""IDTA-01001 Part 1 v3.0.8: Identifiers, References, and Key Types.

This module defines the fundamental identification and referencing constructs
used throughout the AAS metamodel per IDTA-01001-3-0-1_schemasV3.0.8.
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
    """Enumeration of SubmodelElement types (includes abstract base types per v3.0.8+).

    Concrete types are used as modelType discriminators. Abstract types
    (DataElement, EventElement, SubmodelElement) are included for schema
    conformance and type constraints.
    """

    # Concrete types (used as modelType discriminators)
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

    # Abstract types (for schema conformance, not used as modelType)
    DATA_ELEMENT = "DataElement"
    EVENT_ELEMENT = "EventElement"
    SUBMODEL_ELEMENT = "SubmodelElement"


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
    """Kind of an Asset.

    Per IDTA-01001-3-0-1 v3.0.8 JSON Schema:
    - Instance: Asset is an instance (individual)
    - NotApplicable: Asset kind is not applicable
    - Type: Asset is a type (template/class)
    """

    INSTANCE = "Instance"
    NOT_APPLICABLE = "NotApplicable"
    TYPE = "Type"


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
    value: Annotated[str, Field(min_length=1, max_length=2048)] = Field(
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
Identifier = Annotated[str, Field(min_length=1, max_length=2048)]
IdShort = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z](?:[a-zA-Z0-9_-]*[a-zA-Z0-9_])?$",
    ),
]

# MIME type pattern per IDTA-01001-3-0-1 v3.0.8 JSON schema (RFC 2045/7231).
# Format: type/subtype[;parameter=value]*
MIME_TYPE_PATTERN = (
    r"^([!#$%&'*+\-.^_`|~0-9a-zA-Z])+/([!#$%&'*+\-.^_`|~0-9a-zA-Z])+"
    r"([ \t]*;[ \t]*([!#$%&'*+\-.^_`|~0-9a-zA-Z])+=("
    r"([!#$%&'*+\-.^_`|~0-9a-zA-Z])+|"
    r"\"(([\t !#-\[\]-~]|[\x80-\xff])|\\\\([\t !-~]|[\x80-\xff]))*\"))*$"
)
ContentType = Annotated[str, Field(min_length=1, max_length=128, pattern=MIME_TYPE_PATTERN)]

# URI pattern per IDTA-01001-3-0-1 v3.0.8 JSON schema (RFC 3986).
# NOTE: The full RFC 3986 regex from the spec is not compatible with the
# Rust regex engine used by pydantic-core and fails schema compilation.
# This relaxed pattern allows absolute/relative paths and URI schemes.
URI_PATTERN = r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:(//)?\S+|/\S+|\S+)$"
PathType = Annotated[str, Field(min_length=1, max_length=2048, pattern=URI_PATTERN)]
BlobType = bytes
ValueDataType = str

# ISO 8601 Duration pattern per IDTA-01001-3-0-1 v3.0.8 JSON schema.
# Format: P[n]Y[n]M[n]DT[n]H[n]M[n]S or PT[n]H[n]M[n]S
ISO8601_DURATION_PATTERN = (
    r"^-?P((([0-9]+Y([0-9]+M)?([0-9]+D)?|([0-9]+M)([0-9]+D)?|([0-9]+D))"
    r"(T(([0-9]+H)([0-9]+M)?([0-9]+(\\.[0-9]+)?S)?|"
    r"([0-9]+M)([0-9]+(\\.[0-9]+)?S)?|([0-9]+(\\.[0-9]+)?S)))?)|"
    r"(T(([0-9]+H)([0-9]+M)?([0-9]+(\\.[0-9]+)?S)?|"
    r"([0-9]+M)([0-9]+(\\.[0-9]+)?S)?|([0-9]+(\\.[0-9]+)?S))))$"
)

# ISO 8601 UTC timestamp pattern per IDTA-01001-3-0-1 v3.0.8 JSON schema.
# Format: YYYY-MM-DDTHH:MM:SS[.sss](Z|+00:00|-00:00)
ISO8601_UTC_PATTERN = (
    r"^-?(([1-9][0-9][0-9][0-9]+)|(0[0-9][0-9][0-9]))-((0[1-9])|(1[0-2]))-"
    r"((0[1-9])|([12][0-9])|(3[01]))T(((([01][0-9])|(2[0-3])):[0-5][0-9]:"
    r"([0-5][0-9])(\.[0-9]+)?)|24:00:00(\.0+)?)(Z|\+00:00|-00:00)$"
)
