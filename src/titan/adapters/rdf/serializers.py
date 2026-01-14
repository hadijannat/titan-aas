"""RDF serialization utilities.

This module provides format-specific serialization functions for RDF graphs,
supporting JSON-LD, Turtle, N-Triples, and RDF/XML formats.

Example:
    from rdflib import Graph
    from titan.adapters.rdf.serializers import serialize_graph, RdfFormat

    graph = Graph()
    # ... populate graph ...

    # Serialize to different formats
    turtle = serialize_graph(graph, RdfFormat.TURTLE)
    jsonld = serialize_graph(graph, RdfFormat.JSON_LD)
    ntriples = serialize_graph(graph, RdfFormat.N_TRIPLES)
"""

from __future__ import annotations

import json
from typing import Any

from rdflib import Graph

from titan.adapters.rdf.ontology import AAS_NAMESPACE, RdfFormat, get_aas_namespaces


def serialize_graph(graph: Graph, format: RdfFormat = RdfFormat.TURTLE) -> str:
    """Serialize an RDF graph to a string.

    Args:
        graph: The RDF graph to serialize
        format: Output format (default: Turtle)

    Returns:
        Serialized RDF string
    """
    if format == RdfFormat.JSON_LD:
        return serialize_to_jsonld(graph)
    elif format == RdfFormat.TURTLE:
        return serialize_to_turtle(graph)
    elif format == RdfFormat.N_TRIPLES:
        return serialize_to_ntriples(graph)
    elif format == RdfFormat.RDF_XML:
        return serialize_to_rdfxml(graph)
    else:
        raise ValueError(f"Unsupported format: {format}")


def serialize_to_turtle(graph: Graph) -> str:
    """Serialize graph to Turtle format.

    Turtle is a human-readable RDF format that uses prefix declarations
    and a compact syntax for triples.

    Args:
        graph: The RDF graph to serialize

    Returns:
        Turtle-formatted string
    """
    return graph.serialize(format="turtle")


def serialize_to_ntriples(graph: Graph) -> str:
    """Serialize graph to N-Triples format.

    N-Triples is a line-based, plain text format for RDF triples.
    Each line represents a single triple.

    Args:
        graph: The RDF graph to serialize

    Returns:
        N-Triples-formatted string
    """
    return graph.serialize(format="nt")


def serialize_to_rdfxml(graph: Graph) -> str:
    """Serialize graph to RDF/XML format.

    RDF/XML is the original W3C standard serialization format for RDF.

    Args:
        graph: The RDF graph to serialize

    Returns:
        RDF/XML-formatted string
    """
    return graph.serialize(format="xml")


def serialize_to_jsonld(graph: Graph, context: dict[str, Any] | None = None) -> str:
    """Serialize graph to JSON-LD format.

    JSON-LD is a JSON-based serialization format for linked data that
    combines the simplicity of JSON with the semantic capabilities of RDF.

    The output includes:
    - A @context section mapping prefixes to namespaces
    - A @graph array containing the serialized entities
    - Proper type coercion for URIs and data types

    Args:
        graph: The RDF graph to serialize
        context: Optional custom JSON-LD context to use

    Returns:
        JSON-LD-formatted string with proper formatting
    """
    # Build the JSON-LD context
    if context is None:
        context = _build_jsonld_context(graph)

    # Serialize using rdflib's json-ld plugin
    jsonld_str = graph.serialize(format="json-ld", context=context)

    # Parse and re-format for consistent output
    jsonld_data = json.loads(jsonld_str)

    # Ensure we have a nicely formatted output
    return json.dumps(jsonld_data, indent=2, ensure_ascii=False)


def _build_jsonld_context(graph: Graph) -> dict[str, Any]:
    """Build a JSON-LD context from graph namespace bindings.

    Args:
        graph: The RDF graph

    Returns:
        JSON-LD context dictionary
    """
    context: dict[str, Any] = {}

    # Add standard AAS namespaces
    namespaces = get_aas_namespaces()
    for prefix, namespace in namespaces.items():
        context[prefix] = namespace

    # Add any additional namespaces bound to the graph
    for prefix, namespace in graph.namespaces():
        prefix_str = str(prefix)
        namespace_str = str(namespace)
        if prefix_str and prefix_str not in context:
            context[prefix_str] = namespace_str

    # Add common JSON-LD type coercions for AAS properties
    context.update(_get_jsonld_type_coercions())

    return context


def _get_jsonld_type_coercions() -> dict[str, Any]:
    """Get JSON-LD type coercions for AAS properties.

    Returns:
        Dictionary of property type coercions
    """
    aas = AAS_NAMESPACE

    return {
        # Identifier properties that should be treated as @id references
        "id": {"@id": f"{aas}id"},
        "idShort": {"@id": f"{aas}idShort"},
        "semanticId": {"@id": f"{aas}semanticId", "@type": "@id"},
        "submodels": {"@id": f"{aas}submodels", "@type": "@id", "@container": "@set"},
        "submodelElements": {
            "@id": f"{aas}submodelElements",
            "@container": "@set",
        },
        "derivedFrom": {"@id": f"{aas}derivedFrom", "@type": "@id"},
        # Asset information
        "assetInformation": {"@id": f"{aas}assetInformation"},
        "assetKind": {"@id": f"{aas}assetKind"},
        "globalAssetId": {"@id": f"{aas}globalAssetId", "@type": "@id"},
        # Value properties
        "value": {"@id": f"{aas}value"},
        "valueType": {"@id": f"{aas}valueType"},
        "valueId": {"@id": f"{aas}valueId", "@type": "@id"},
        # Reference properties
        "keys": {"@id": f"{aas}keys", "@container": "@list"},
        "type": {"@id": f"{aas}type"},
        # Administrative
        "administration": {"@id": f"{aas}administration"},
        "version": {"@id": f"{aas}version"},
        "revision": {"@id": f"{aas}revision"},
        # Descriptions
        "description": {"@id": f"{aas}description", "@container": "@set"},
        "displayName": {"@id": f"{aas}displayName", "@container": "@set"},
        "language": {"@id": f"{aas}language"},
        "text": {"@id": f"{aas}text"},
    }


# Additional format utilities


def get_format_from_accept_header(accept: str) -> RdfFormat:
    """Parse Accept header and return the best matching RDF format.

    Args:
        accept: HTTP Accept header value

    Returns:
        Best matching RdfFormat

    Raises:
        ValueError: If no supported format found
    """
    # Parse the Accept header (simplified - doesn't handle q-values)
    mime_types = [mt.strip().split(";")[0] for mt in accept.split(",")]

    # Priority order for matching
    priority = [
        "application/ld+json",
        "text/turtle",
        "application/n-triples",
        "application/rdf+xml",
    ]

    for mime_type in mime_types:
        if mime_type in priority:
            return RdfFormat.from_mime_type(mime_type)

    # Check for wildcard
    if "*/*" in mime_types or "application/*" in mime_types:
        return RdfFormat.TURTLE  # Default

    raise ValueError(f"No supported RDF format in Accept header: {accept}")


def get_content_type(format: RdfFormat) -> str:
    """Get the Content-Type header value for an RDF format.

    Args:
        format: The RDF format

    Returns:
        Content-Type header value with charset
    """
    return f"{format.mime_type}; charset=utf-8"
