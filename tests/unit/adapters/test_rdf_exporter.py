"""Tests for RDF exporter.

Tests the AasRdfExporter class and RDF serialization functionality.
"""

import pytest
from rdflib import Graph, Literal, Namespace, URIRef

from titan.adapters.rdf import (
    AAS_NAMESPACE,
    AasRdfExporter,
    RdfFormat,
    get_aas_namespaces,
    serialize_graph,
    serialize_to_jsonld,
    serialize_to_ntriples,
    serialize_to_turtle,
)
from titan.adapters.rdf.ontology import (
    AasPropertyUri,
    AasTypeUri,
    get_rdf_type_for_model,
    get_xsd_datatype,
)
from titan.core.model import (
    AssetAdministrationShell,
    AssetInformation,
    AssetKind,
    Key,
    KeyTypes,
    Property,
    Reference,
    ReferenceTypes,
    Submodel,
    SubmodelElementCollection,
)

AAS = Namespace(AAS_NAMESPACE)


class TestRdfFormat:
    """Test RdfFormat enum."""

    def test_from_mime_type_jsonld(self) -> None:
        """Parse JSON-LD MIME type."""
        fmt = RdfFormat.from_mime_type("application/ld+json")
        assert fmt == RdfFormat.JSON_LD

    def test_from_mime_type_turtle(self) -> None:
        """Parse Turtle MIME type."""
        fmt = RdfFormat.from_mime_type("text/turtle")
        assert fmt == RdfFormat.TURTLE

    def test_from_mime_type_ntriples(self) -> None:
        """Parse N-Triples MIME type."""
        fmt = RdfFormat.from_mime_type("application/n-triples")
        assert fmt == RdfFormat.N_TRIPLES

    def test_from_mime_type_rdfxml(self) -> None:
        """Parse RDF/XML MIME type."""
        fmt = RdfFormat.from_mime_type("application/rdf+xml")
        assert fmt == RdfFormat.RDF_XML

    def test_from_mime_type_unsupported(self) -> None:
        """Unsupported MIME type raises error."""
        with pytest.raises(ValueError, match="Unsupported RDF MIME type"):
            RdfFormat.from_mime_type("text/html")

    def test_mime_type_property(self) -> None:
        """Get MIME type from format."""
        assert RdfFormat.JSON_LD.mime_type == "application/ld+json"
        assert RdfFormat.TURTLE.mime_type == "text/turtle"
        assert RdfFormat.N_TRIPLES.mime_type == "application/n-triples"
        assert RdfFormat.RDF_XML.mime_type == "application/rdf+xml"


class TestOntologyHelpers:
    """Test ontology helper functions."""

    def test_get_aas_namespaces(self) -> None:
        """Get standard AAS namespaces."""
        namespaces = get_aas_namespaces()
        assert "aas" in namespaces
        assert namespaces["aas"] == AAS_NAMESPACE
        assert "xsd" in namespaces
        assert "rdfs" in namespaces

    def test_get_rdf_type_for_model_property(self) -> None:
        """Get RDF type for Property."""
        rdf_type = get_rdf_type_for_model("Property")
        assert rdf_type == AasTypeUri.PROPERTY

    def test_get_rdf_type_for_model_submodel(self) -> None:
        """Get RDF type for Submodel."""
        rdf_type = get_rdf_type_for_model("Submodel")
        assert rdf_type == AasTypeUri.SUBMODEL

    def test_get_rdf_type_for_model_unknown(self) -> None:
        """Unknown model type returns None."""
        rdf_type = get_rdf_type_for_model("UnknownType")
        assert rdf_type is None

    def test_get_xsd_datatype_string(self) -> None:
        """Get XSD datatype for xs:string."""
        from titan.adapters.rdf.ontology import XSD

        datatype = get_xsd_datatype("xs:string")
        assert datatype == XSD.string

    def test_get_xsd_datatype_double(self) -> None:
        """Get XSD datatype for xs:double."""
        from titan.adapters.rdf.ontology import XSD

        datatype = get_xsd_datatype("xs:double")
        assert datatype == XSD.double

    def test_get_xsd_datatype_none_defaults_to_string(self) -> None:
        """None valueType defaults to xs:string."""
        from titan.adapters.rdf.ontology import XSD

        datatype = get_xsd_datatype(None)
        assert datatype == XSD.string


class TestAasRdfExporter:
    """Test AasRdfExporter class."""

    def test_init_creates_graph(self) -> None:
        """Exporter creates empty graph on init."""
        exporter = AasRdfExporter()
        assert exporter.graph is not None
        assert isinstance(exporter.graph, Graph)

    def test_add_prefix(self) -> None:
        """Add custom namespace prefix."""
        exporter = AasRdfExporter()
        exporter.add_prefix("eclass", "https://eclass.eu/")

        # Verify prefix is bound
        namespaces = dict(exporter.graph.namespaces())
        assert "eclass" in namespaces

    def test_clear_resets_graph(self) -> None:
        """Clear resets the graph."""
        exporter = AasRdfExporter()

        # Add something to the graph
        exporter.graph.add((URIRef("urn:test:1"), URIRef("urn:test:prop"), Literal("value")))
        assert len(exporter.graph) == 1

        # Clear
        exporter.clear()
        assert len(exporter.graph) == 0

    def test_clear_preserves_custom_prefixes(self) -> None:
        """Clear preserves custom prefixes."""
        exporter = AasRdfExporter()
        exporter.add_prefix("eclass", "https://eclass.eu/")

        exporter.clear()

        namespaces = dict(exporter.graph.namespaces())
        assert "eclass" in namespaces


class TestExportShell:
    """Test exporting AssetAdministrationShell."""

    def make_shell(self) -> AssetAdministrationShell:
        """Create a test shell."""
        return AssetAdministrationShell(
            id="urn:example:shell:1",
            idShort="TestShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:1",
            ),
        )

    def test_export_shell_returns_string(self) -> None:
        """Export shell returns RDF string."""
        exporter = AasRdfExporter()
        shell = self.make_shell()

        result = exporter.export_shell(shell)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_export_shell_turtle_format(self) -> None:
        """Export shell in Turtle format."""
        exporter = AasRdfExporter()
        shell = self.make_shell()

        result = exporter.export_shell(shell, format=RdfFormat.TURTLE)

        # Turtle should have prefix declarations
        assert "@prefix" in result
        assert "aas:" in result

    def test_export_shell_jsonld_format(self) -> None:
        """Export shell in JSON-LD format."""
        exporter = AasRdfExporter()
        shell = self.make_shell()

        result = exporter.export_shell(shell, format=RdfFormat.JSON_LD)

        # JSON-LD should be valid JSON
        import json

        data = json.loads(result)
        assert "@context" in data or "@graph" in data or "@type" in data

    def test_export_shell_ntriples_format(self) -> None:
        """Export shell in N-Triples format."""
        exporter = AasRdfExporter()
        shell = self.make_shell()

        result = exporter.export_shell(shell, format=RdfFormat.N_TRIPLES)

        # N-Triples should have full URIs
        assert "<urn:example:shell:1>" in result or "urn:example:shell:1" in result

    def test_add_shell_creates_type_triple(self) -> None:
        """Adding shell creates rdf:type triple."""
        exporter = AasRdfExporter()
        shell = self.make_shell()

        shell_uri = exporter.add_shell(shell)

        # Check for type triple
        from rdflib import RDF

        types = list(exporter.graph.objects(shell_uri, RDF.type))
        assert AasTypeUri.ASSET_ADMINISTRATION_SHELL in types

    def test_add_shell_creates_id_triple(self) -> None:
        """Adding shell creates id triple."""
        exporter = AasRdfExporter()
        shell = self.make_shell()

        shell_uri = exporter.add_shell(shell)

        # Check for id triple
        ids = list(exporter.graph.objects(shell_uri, AasPropertyUri.ID))
        assert Literal("urn:example:shell:1") in ids

    def test_add_shell_creates_idshort_triple(self) -> None:
        """Adding shell creates idShort triple."""
        exporter = AasRdfExporter()
        shell = self.make_shell()

        shell_uri = exporter.add_shell(shell)

        # Check for idShort triple
        id_shorts = list(exporter.graph.objects(shell_uri, AasPropertyUri.ID_SHORT))
        assert Literal("TestShell") in id_shorts


class TestExportSubmodel:
    """Test exporting Submodel."""

    def make_submodel(self) -> Submodel:
        """Create a test submodel."""
        return Submodel(
            id="urn:example:submodel:1",
            idShort="TechnicalData",
            submodelElements=[
                Property(
                    idShort="MaxTemperature",
                    valueType="xs:double",
                    value="85.5",
                    modelType="Property",
                ),
            ],
        )

    def test_export_submodel_returns_string(self) -> None:
        """Export submodel returns RDF string."""
        exporter = AasRdfExporter()
        submodel = self.make_submodel()

        result = exporter.export_submodel(submodel)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_submodel_creates_type_triple(self) -> None:
        """Adding submodel creates rdf:type triple."""
        exporter = AasRdfExporter()
        submodel = self.make_submodel()

        submodel_uri = exporter.add_submodel(submodel)

        from rdflib import RDF

        types = list(exporter.graph.objects(submodel_uri, RDF.type))
        assert AasTypeUri.SUBMODEL in types

    def test_add_submodel_includes_elements(self) -> None:
        """Adding submodel includes submodel elements."""
        exporter = AasRdfExporter()
        submodel = self.make_submodel()

        submodel_uri = exporter.add_submodel(submodel)

        # Check for submodelElements triple
        elements = list(exporter.graph.objects(submodel_uri, AasPropertyUri.SUBMODEL_ELEMENTS))
        assert len(elements) == 1

    def test_property_element_has_value(self) -> None:
        """Property element includes value triple."""
        exporter = AasRdfExporter()
        submodel = self.make_submodel()

        exporter.add_submodel(submodel)

        # Find Property node by type
        from rdflib import RDF

        property_nodes = list(exporter.graph.subjects(RDF.type, AasTypeUri.PROPERTY))
        assert len(property_nodes) == 1

        # Check value
        values = list(exporter.graph.objects(property_nodes[0], AasPropertyUri.VALUE))
        assert len(values) == 1


class TestExportSubmodelElementCollection:
    """Test exporting SubmodelElementCollection."""

    def make_smc_submodel(self) -> Submodel:
        """Create a submodel with nested SMC."""
        return Submodel(
            id="urn:example:submodel:smc",
            idShort="NestedData",
            submodelElements=[
                SubmodelElementCollection(
                    idShort="Configuration",
                    modelType="SubmodelElementCollection",
                    value=[
                        Property(
                            idShort="Setting1",
                            valueType="xs:string",
                            value="enabled",
                            modelType="Property",
                        ),
                        Property(
                            idShort="Setting2",
                            valueType="xs:int",
                            value="42",
                            modelType="Property",
                        ),
                    ],
                ),
            ],
        )

    def test_export_smc_includes_nested_elements(self) -> None:
        """SMC export includes nested elements."""
        exporter = AasRdfExporter()
        submodel = self.make_smc_submodel()

        exporter.add_submodel(submodel)

        # Count Property nodes
        from rdflib import RDF

        property_nodes = list(exporter.graph.subjects(RDF.type, AasTypeUri.PROPERTY))
        assert len(property_nodes) == 2

        # Count SMC nodes
        smc_nodes = list(exporter.graph.subjects(RDF.type, AasTypeUri.SUBMODEL_ELEMENT_COLLECTION))
        assert len(smc_nodes) == 1


class TestSerializers:
    """Test serialization functions."""

    def make_simple_graph(self) -> Graph:
        """Create a simple test graph."""
        g = Graph()
        g.bind("aas", AAS)
        subject = URIRef("urn:test:1")
        g.add((subject, AAS.id, Literal("urn:test:1")))
        g.add((subject, AAS.idShort, Literal("Test")))
        return g

    def test_serialize_to_turtle(self) -> None:
        """Serialize graph to Turtle."""
        g = self.make_simple_graph()

        result = serialize_to_turtle(g)

        assert "@prefix" in result
        assert "aas:" in result or AAS_NAMESPACE in result

    def test_serialize_to_ntriples(self) -> None:
        """Serialize graph to N-Triples."""
        g = self.make_simple_graph()

        result = serialize_to_ntriples(g)

        # N-Triples has full URIs on each line
        assert "urn:test:1" in result

    def test_serialize_to_jsonld(self) -> None:
        """Serialize graph to JSON-LD."""
        g = self.make_simple_graph()

        result = serialize_to_jsonld(g)

        import json

        data = json.loads(result)
        assert isinstance(data, dict)

    def test_serialize_graph_default_turtle(self) -> None:
        """serialize_graph defaults to Turtle."""
        g = self.make_simple_graph()

        result = serialize_graph(g)

        assert "@prefix" in result


class TestExportWithReferences:
    """Test exporting entities with references."""

    def test_shell_with_submodel_references(self) -> None:
        """Export shell with submodel references."""
        exporter = AasRdfExporter()

        shell = AssetAdministrationShell(
            id="urn:example:shell:with-refs",
            idShort="ShellWithRefs",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:1",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[
                        Key(type=KeyTypes.SUBMODEL, value="urn:example:submodel:1"),
                    ],
                ),
            ],
        )

        shell_uri = exporter.add_shell(shell)

        # Check for submodels triple
        submodel_refs = list(exporter.graph.objects(shell_uri, AasPropertyUri.SUBMODELS))
        assert len(submodel_refs) == 1

    def test_reference_has_keys(self) -> None:
        """Reference includes keys."""
        exporter = AasRdfExporter()

        shell = AssetAdministrationShell(
            id="urn:example:shell:ref-keys",
            idShort="ShellRefKeys",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:1",
            ),
            submodels=[
                Reference(
                    type=ReferenceTypes.MODEL_REFERENCE,
                    keys=[
                        Key(type=KeyTypes.SUBMODEL, value="urn:example:submodel:1"),
                    ],
                ),
            ],
        )

        exporter.add_shell(shell)

        # Find Key nodes
        from rdflib import RDF

        key_nodes = list(exporter.graph.subjects(RDF.type, AasTypeUri.KEY))
        assert len(key_nodes) == 1


class TestBaseUri:
    """Test base URI handling."""

    def test_exporter_with_base_uri(self) -> None:
        """Exporter uses base URI for identifiers."""
        exporter = AasRdfExporter(base_uri="https://example.com/aas")

        shell = AssetAdministrationShell(
            id="shell-1",  # Not a full URI
            idShort="TestShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:1",
            ),
        )

        shell_uri = exporter.add_shell(shell)

        # URI should use base_uri
        assert str(shell_uri) == "https://example.com/aas/shell-1"

    def test_exporter_without_base_uri_uses_urn(self) -> None:
        """Without base URI, non-URI identifiers get urn: prefix."""
        exporter = AasRdfExporter()

        shell = AssetAdministrationShell(
            id="shell-1",  # Not a full URI
            idShort="TestShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:1",
            ),
        )

        shell_uri = exporter.add_shell(shell)

        # URI should use urn: scheme
        assert str(shell_uri) == "urn:aas:shell-1"

    def test_exporter_preserves_full_uri(self) -> None:
        """Exporter preserves full URI identifiers."""
        exporter = AasRdfExporter(base_uri="https://example.com/aas")

        shell = AssetAdministrationShell(
            id="https://other.example.com/shells/1",  # Full URI
            idShort="TestShell",
            assetInformation=AssetInformation(
                assetKind=AssetKind.INSTANCE,
                globalAssetId="urn:example:asset:1",
            ),
        )

        shell_uri = exporter.add_shell(shell)

        # Full URI should be preserved, not modified
        assert str(shell_uri) == "https://other.example.com/shells/1"
