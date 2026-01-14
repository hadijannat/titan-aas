"""RDF adapter for AAS semantic interoperability.

This module provides RDF export and import capabilities for Asset Administration
Shells, enabling integration with Knowledge Graph ecosystems and semantic web
applications.

Supported formats:
- JSON-LD (application/ld+json)
- Turtle (text/turtle)
- N-Triples (application/n-triples)
- RDF/XML (application/rdf+xml)

Example:
    from titan.adapters.rdf import AasRdfExporter, RdfFormat

    exporter = AasRdfExporter()

    # Export AAS to JSON-LD
    jsonld = exporter.export_shell(shell, format=RdfFormat.JSON_LD)

    # Export Submodel to Turtle
    turtle = exporter.export_submodel(submodel, format=RdfFormat.TURTLE)

    # Export with custom prefixes
    exporter.add_prefix("eclass", "https://eclass.eu/")
    rdf = exporter.export_shell(shell, format=RdfFormat.TURTLE)
"""

from titan.adapters.rdf.exporter import AasRdfExporter
from titan.adapters.rdf.ontology import (
    AAS_NAMESPACE,
    AAS_PREFIX,
    XSD_NAMESPACE,
    RdfFormat,
    get_aas_namespaces,
)
from titan.adapters.rdf.serializers import (
    serialize_graph,
    serialize_to_jsonld,
    serialize_to_ntriples,
    serialize_to_turtle,
)

__all__ = [
    # Exporter
    "AasRdfExporter",
    # Ontology
    "AAS_NAMESPACE",
    "AAS_PREFIX",
    "XSD_NAMESPACE",
    "RdfFormat",
    "get_aas_namespaces",
    # Serializers
    "serialize_graph",
    "serialize_to_jsonld",
    "serialize_to_turtle",
    "serialize_to_ntriples",
]
