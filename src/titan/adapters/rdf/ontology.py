"""AAS 3.0 RDF ontology definitions and namespace mappings.

This module defines the RDF namespaces, prefixes, and type mappings
according to the IDTA AAS 3.0 ontology specification.

The AAS ontology defines how AAS concepts map to RDF/OWL constructs:
- AssetAdministrationShell → aas:AssetAdministrationShell
- Submodel → aas:Submodel
- Property → aas:Property
- semanticId → aas:semanticId (object property)
- value → aas:value (data property)

References:
- IDTA-01001: Metamodel specification
- AAS ontology: https://admin-shell.io/aas/3/0/
"""

from enum import Enum
from typing import Final

from rdflib import Namespace, URIRef

# Core AAS namespace (IDTA AAS 3.0 ontology)
AAS_NAMESPACE: Final[str] = "https://admin-shell.io/aas/3/0/"
AAS_PREFIX: Final[str] = "aas"

# Standard namespaces
XSD_NAMESPACE: Final[str] = "http://www.w3.org/2001/XMLSchema#"
RDFS_NAMESPACE: Final[str] = "http://www.w3.org/2000/01/rdf-schema#"
RDF_NAMESPACE: Final[str] = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL_NAMESPACE: Final[str] = "http://www.w3.org/2002/07/owl#"

# RDFLib namespace objects
AAS = Namespace(AAS_NAMESPACE)
XSD = Namespace(XSD_NAMESPACE)
RDFS = Namespace(RDFS_NAMESPACE)
RDF = Namespace(RDF_NAMESPACE)
OWL = Namespace(OWL_NAMESPACE)


class RdfFormat(str, Enum):
    """Supported RDF serialization formats."""

    JSON_LD = "json-ld"
    TURTLE = "turtle"
    N_TRIPLES = "nt"
    RDF_XML = "xml"

    @classmethod
    def from_mime_type(cls, mime_type: str) -> "RdfFormat":
        """Get format from MIME type.

        Args:
            mime_type: HTTP Accept header MIME type

        Returns:
            Corresponding RdfFormat

        Raises:
            ValueError: If MIME type not supported
        """
        mapping = {
            "application/ld+json": cls.JSON_LD,
            "text/turtle": cls.TURTLE,
            "application/n-triples": cls.N_TRIPLES,
            "application/rdf+xml": cls.RDF_XML,
        }
        if mime_type not in mapping:
            raise ValueError(f"Unsupported RDF MIME type: {mime_type}")
        return mapping[mime_type]

    @property
    def mime_type(self) -> str:
        """Get MIME type for this format."""
        mapping = {
            self.JSON_LD: "application/ld+json",
            self.TURTLE: "text/turtle",
            self.N_TRIPLES: "application/n-triples",
            self.RDF_XML: "application/rdf+xml",
        }
        return mapping[self]


def get_aas_namespaces() -> dict[str, str]:
    """Get standard AAS namespace prefix mappings.

    Returns:
        Dict mapping prefix to namespace URI
    """
    return {
        "aas": AAS_NAMESPACE,
        "xsd": XSD_NAMESPACE,
        "rdfs": RDFS_NAMESPACE,
        "rdf": RDF_NAMESPACE,
        "owl": OWL_NAMESPACE,
    }


# AAS Type URIs
# These map AAS metamodel types to their RDF class URIs
class AasTypeUri:
    """RDF type URIs for AAS metamodel classes."""

    # Top-level containers
    ASSET_ADMINISTRATION_SHELL: Final[URIRef] = AAS.AssetAdministrationShell
    SUBMODEL: Final[URIRef] = AAS.Submodel
    CONCEPT_DESCRIPTION: Final[URIRef] = AAS.ConceptDescription

    # Asset Information
    ASSET_INFORMATION: Final[URIRef] = AAS.AssetInformation
    RESOURCE: Final[URIRef] = AAS.Resource
    SPECIFIC_ASSET_ID: Final[URIRef] = AAS.SpecificAssetId

    # Administrative
    ADMINISTRATIVE_INFORMATION: Final[URIRef] = AAS.AdministrativeInformation

    # Submodel Elements
    PROPERTY: Final[URIRef] = AAS.Property
    MULTI_LANGUAGE_PROPERTY: Final[URIRef] = AAS.MultiLanguageProperty
    RANGE: Final[URIRef] = AAS.Range
    BLOB: Final[URIRef] = AAS.Blob
    FILE: Final[URIRef] = AAS.File
    REFERENCE_ELEMENT: Final[URIRef] = AAS.ReferenceElement
    SUBMODEL_ELEMENT_COLLECTION: Final[URIRef] = AAS.SubmodelElementCollection
    SUBMODEL_ELEMENT_LIST: Final[URIRef] = AAS.SubmodelElementList
    ENTITY: Final[URIRef] = AAS.Entity
    BASIC_EVENT_ELEMENT: Final[URIRef] = AAS.BasicEventElement
    OPERATION: Final[URIRef] = AAS.Operation
    CAPABILITY: Final[URIRef] = AAS.Capability
    ANNOTATED_RELATIONSHIP_ELEMENT: Final[URIRef] = AAS.AnnotatedRelationshipElement
    RELATIONSHIP_ELEMENT: Final[URIRef] = AAS.RelationshipElement

    # References
    REFERENCE: Final[URIRef] = AAS.Reference
    KEY: Final[URIRef] = AAS.Key

    # Qualifiers
    QUALIFIER: Final[URIRef] = AAS.Qualifier
    EXTENSION: Final[URIRef] = AAS.Extension


# AAS Property URIs
# These map AAS attributes to their RDF property URIs
class AasPropertyUri:
    """RDF property URIs for AAS metamodel attributes."""

    # Identifiers
    ID: Final[URIRef] = AAS.id
    ID_SHORT: Final[URIRef] = AAS.idShort
    CATEGORY: Final[URIRef] = AAS.category

    # Descriptions
    DESCRIPTION: Final[URIRef] = AAS.description
    DISPLAY_NAME: Final[URIRef] = AAS.displayName

    # Semantics
    SEMANTIC_ID: Final[URIRef] = AAS.semanticId
    SUPPLEMENTAL_SEMANTIC_IDS: Final[URIRef] = AAS.supplementalSemanticIds

    # Values
    VALUE: Final[URIRef] = AAS.value
    VALUE_TYPE: Final[URIRef] = AAS.valueType
    VALUE_ID: Final[URIRef] = AAS.valueId
    MIN: Final[URIRef] = AAS["min"]
    MAX: Final[URIRef] = AAS["max"]

    # Containers
    SUBMODELS: Final[URIRef] = AAS.submodels
    SUBMODEL_ELEMENTS: Final[URIRef] = AAS.submodelElements
    STATEMENTS: Final[URIRef] = AAS.statements

    # Asset Information
    ASSET_INFORMATION: Final[URIRef] = AAS.assetInformation
    ASSET_KIND: Final[URIRef] = AAS.assetKind
    GLOBAL_ASSET_ID: Final[URIRef] = AAS.globalAssetId
    SPECIFIC_ASSET_IDS: Final[URIRef] = AAS.specificAssetIds
    ASSET_TYPE: Final[URIRef] = AAS.assetType
    DEFAULT_THUMBNAIL: Final[URIRef] = AAS.defaultThumbnail

    # Administrative
    ADMINISTRATION: Final[URIRef] = AAS.administration
    VERSION: Final[URIRef] = AAS.version
    REVISION: Final[URIRef] = AAS.revision
    CREATOR: Final[URIRef] = AAS.creator
    TEMPLATE_ID: Final[URIRef] = AAS.templateId

    # References
    DERIVED_FROM: Final[URIRef] = AAS.derivedFrom
    TYPE: Final[URIRef] = AAS.type
    KEYS: Final[URIRef] = AAS.keys
    REFERRED_SEMANTIC_ID: Final[URIRef] = AAS.referredSemanticId

    # Key attributes
    KEY_TYPE: Final[URIRef] = AAS.type
    KEY_VALUE: Final[URIRef] = AAS.value

    # Qualifiers
    QUALIFIERS: Final[URIRef] = AAS.qualifiers
    QUALIFIER_KIND: Final[URIRef] = AAS.kind
    QUALIFIER_TYPE: Final[URIRef] = AAS.type
    QUALIFIER_VALUE: Final[URIRef] = AAS.value
    QUALIFIER_VALUE_TYPE: Final[URIRef] = AAS.valueType

    # Extensions
    EXTENSIONS: Final[URIRef] = AAS.extensions
    EXTENSION_NAME: Final[URIRef] = AAS.name
    EXTENSION_VALUE: Final[URIRef] = AAS.value
    EXTENSION_VALUE_TYPE: Final[URIRef] = AAS.valueType

    # File/Blob
    CONTENT_TYPE: Final[URIRef] = AAS.contentType
    PATH: Final[URIRef] = AAS.path

    # Relationships
    FIRST: Final[URIRef] = AAS.first
    SECOND: Final[URIRef] = AAS.second
    ANNOTATIONS: Final[URIRef] = AAS.annotations

    # Entity
    ENTITY_TYPE: Final[URIRef] = AAS.entityType
    GLOBAL_ASSET_ID_ENTITY: Final[URIRef] = AAS.globalAssetId

    # Event
    OBSERVED: Final[URIRef] = AAS.observed
    DIRECTION: Final[URIRef] = AAS.direction
    STATE: Final[URIRef] = AAS.state

    # Operation
    INPUT_VARIABLES: Final[URIRef] = AAS.inputVariables
    OUTPUT_VARIABLES: Final[URIRef] = AAS.outputVariables
    INOUTPUT_VARIABLES: Final[URIRef] = AAS.inoutputVariables

    # SubmodelElementList
    ORDER_RELEVANT: Final[URIRef] = AAS.orderRelevant
    SEMANTIC_ID_LIST_ELEMENT: Final[URIRef] = AAS.semanticIdListElement
    TYPE_VALUE_LIST_ELEMENT: Final[URIRef] = AAS.typeValueListElement
    VALUE_TYPE_LIST_ELEMENT: Final[URIRef] = AAS.valueTypeListElement

    # Modelling Kind
    KIND: Final[URIRef] = AAS.kind

    # Lang String
    LANGUAGE: Final[URIRef] = AAS.language
    TEXT: Final[URIRef] = AAS.text


# XSD DataType mapping from AAS valueType to XSD URIRef
XSD_DATATYPE_MAP: dict[str, URIRef] = {
    "xs:string": XSD.string,
    "xs:boolean": XSD.boolean,
    "xs:decimal": XSD.decimal,
    "xs:integer": XSD.integer,
    "xs:double": XSD.double,
    "xs:float": XSD.float,
    "xs:date": XSD.date,
    "xs:time": XSD.time,
    "xs:dateTime": XSD.dateTime,
    "xs:dateTimeStamp": XSD.dateTimeStamp,
    "xs:duration": XSD.duration,
    "xs:gYearMonth": XSD.gYearMonth,
    "xs:gYear": XSD.gYear,
    "xs:gMonthDay": XSD.gMonthDay,
    "xs:gDay": XSD.gDay,
    "xs:gMonth": XSD.gMonth,
    "xs:hexBinary": XSD.hexBinary,
    "xs:base64Binary": XSD.base64Binary,
    "xs:anyURI": XSD.anyURI,
    "xs:int": XSD.int,
    "xs:long": XSD.long,
    "xs:short": XSD.short,
    "xs:byte": XSD.byte,
    "xs:unsignedInt": XSD.unsignedInt,
    "xs:unsignedLong": XSD.unsignedLong,
    "xs:unsignedShort": XSD.unsignedShort,
    "xs:unsignedByte": XSD.unsignedByte,
    "xs:positiveInteger": XSD.positiveInteger,
    "xs:nonPositiveInteger": XSD.nonPositiveInteger,
    "xs:negativeInteger": XSD.negativeInteger,
    "xs:nonNegativeInteger": XSD.nonNegativeInteger,
}


def get_xsd_datatype(value_type: str | None) -> URIRef:
    """Get XSD datatype URI for an AAS valueType.

    Args:
        value_type: AAS valueType string (e.g., "xs:string", "xs:int")

    Returns:
        XSD namespace URIRef for the datatype
    """
    if not value_type:
        return XSD.string  # Default to string
    return XSD_DATATYPE_MAP.get(value_type, XSD.string)


# Model type to RDF type mapping
MODEL_TYPE_TO_RDF: dict[str, URIRef] = {
    "AssetAdministrationShell": AasTypeUri.ASSET_ADMINISTRATION_SHELL,
    "Submodel": AasTypeUri.SUBMODEL,
    "ConceptDescription": AasTypeUri.CONCEPT_DESCRIPTION,
    "Property": AasTypeUri.PROPERTY,
    "MultiLanguageProperty": AasTypeUri.MULTI_LANGUAGE_PROPERTY,
    "Range": AasTypeUri.RANGE,
    "Blob": AasTypeUri.BLOB,
    "File": AasTypeUri.FILE,
    "ReferenceElement": AasTypeUri.REFERENCE_ELEMENT,
    "SubmodelElementCollection": AasTypeUri.SUBMODEL_ELEMENT_COLLECTION,
    "SubmodelElementList": AasTypeUri.SUBMODEL_ELEMENT_LIST,
    "Entity": AasTypeUri.ENTITY,
    "BasicEventElement": AasTypeUri.BASIC_EVENT_ELEMENT,
    "Operation": AasTypeUri.OPERATION,
    "Capability": AasTypeUri.CAPABILITY,
    "AnnotatedRelationshipElement": AasTypeUri.ANNOTATED_RELATIONSHIP_ELEMENT,
    "RelationshipElement": AasTypeUri.RELATIONSHIP_ELEMENT,
}


def get_rdf_type_for_model(model_type: str | None) -> URIRef | None:
    """Get RDF type URI for an AAS model type.

    Args:
        model_type: AAS modelType string (e.g., "Property", "Submodel")

    Returns:
        RDF type URIRef or None if not found
    """
    if not model_type:
        return None
    return MODEL_TYPE_TO_RDF.get(model_type)
