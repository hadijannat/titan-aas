"""AAS to RDF exporter.

This module provides the AasRdfExporter class for converting Asset Administration
Shell entities to RDF graphs using the IDTA AAS 3.0 ontology.

Example:
    from titan.adapters.rdf import AasRdfExporter, RdfFormat

    exporter = AasRdfExporter()

    # Export AAS to Turtle
    turtle = exporter.export_shell(shell, format=RdfFormat.TURTLE)

    # Export Submodel to JSON-LD
    jsonld = exporter.export_submodel(submodel, format=RdfFormat.JSON_LD)

    # Export multiple entities to a single graph
    exporter.add_shell(shell)
    exporter.add_submodel(submodel)
    rdf = exporter.serialize(format=RdfFormat.TURTLE)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rdflib import BNode, Graph, Literal, URIRef

from titan.adapters.rdf.ontology import (
    AAS,
    RDF,
    XSD,
    AasPropertyUri,
    AasTypeUri,
    RdfFormat,
    get_aas_namespaces,
    get_rdf_type_for_model,
    get_xsd_datatype,
)
from titan.adapters.rdf.serializers import serialize_graph

if TYPE_CHECKING:
    from titan.core.model import (
        AssetAdministrationShell,
        ConceptDescription,
        Reference,
        Submodel,
        SubmodelElementUnion,
    )


class AasRdfExporter:
    """Exports AAS entities to RDF graphs.

    This class provides methods to convert AAS models (shells, submodels,
    concept descriptions) to RDF graphs using the IDTA AAS 3.0 ontology.

    The exporter maintains an internal RDF graph that can be extended by
    adding multiple entities, then serialized to various formats.

    Attributes:
        graph: The RDF graph containing exported entities
    """

    def __init__(self, base_uri: str | None = None):
        """Initialize the exporter.

        Args:
            base_uri: Optional base URI for generated identifiers.
                     Defaults to using entity IDs directly.
        """
        self.graph = Graph()
        self.base_uri = base_uri

        # Bind standard namespaces
        for prefix, namespace in get_aas_namespaces().items():
            self.graph.bind(prefix, namespace)

        # Custom prefixes
        self._custom_prefixes: dict[str, str] = {}

    def add_prefix(self, prefix: str, namespace: str) -> None:
        """Add a custom namespace prefix.

        Args:
            prefix: Short prefix (e.g., "eclass")
            namespace: Full namespace URI (e.g., "https://eclass.eu/")
        """
        self._custom_prefixes[prefix] = namespace
        self.graph.bind(prefix, namespace)

    def clear(self) -> None:
        """Clear the internal graph and reset state."""
        self.graph = Graph()
        for prefix, namespace in get_aas_namespaces().items():
            self.graph.bind(prefix, namespace)
        for prefix, namespace in self._custom_prefixes.items():
            self.graph.bind(prefix, namespace)

    def serialize(self, format: RdfFormat = RdfFormat.TURTLE) -> str:
        """Serialize the current graph to a string.

        Args:
            format: Output format (default: Turtle)

        Returns:
            Serialized RDF string
        """
        return serialize_graph(self.graph, format)

    # -------------------------------------------------------------------------
    # High-level export methods
    # -------------------------------------------------------------------------

    def export_shell(
        self,
        shell: AssetAdministrationShell,
        format: RdfFormat = RdfFormat.TURTLE,
    ) -> str:
        """Export a single AAS to RDF string.

        Args:
            shell: The AssetAdministrationShell to export
            format: Output format (default: Turtle)

        Returns:
            Serialized RDF string
        """
        self.clear()
        self.add_shell(shell)
        return self.serialize(format)

    def export_submodel(
        self,
        submodel: Submodel,
        format: RdfFormat = RdfFormat.TURTLE,
    ) -> str:
        """Export a single Submodel to RDF string.

        Args:
            submodel: The Submodel to export
            format: Output format (default: Turtle)

        Returns:
            Serialized RDF string
        """
        self.clear()
        self.add_submodel(submodel)
        return self.serialize(format)

    def export_concept_description(
        self,
        cd: ConceptDescription,
        format: RdfFormat = RdfFormat.TURTLE,
    ) -> str:
        """Export a single ConceptDescription to RDF string.

        Args:
            cd: The ConceptDescription to export
            format: Output format (default: Turtle)

        Returns:
            Serialized RDF string
        """
        self.clear()
        self.add_concept_description(cd)
        return self.serialize(format)

    # -------------------------------------------------------------------------
    # Graph building methods
    # -------------------------------------------------------------------------

    def add_shell(self, shell: AssetAdministrationShell) -> URIRef:
        """Add an AssetAdministrationShell to the graph.

        Args:
            shell: The AAS to add

        Returns:
            URIRef for the shell node
        """
        # Create URI from identifier
        shell_uri = self._make_uri(shell.id)

        # Add type triple
        self.graph.add((shell_uri, RDF.type, AasTypeUri.ASSET_ADMINISTRATION_SHELL))

        # Add identifier
        self.graph.add((shell_uri, AasPropertyUri.ID, Literal(shell.id)))

        # Add idShort
        if shell.id_short:
            self.graph.add((shell_uri, AasPropertyUri.ID_SHORT, Literal(shell.id_short)))

        # Add category
        if shell.category:
            self.graph.add((shell_uri, AasPropertyUri.CATEGORY, Literal(shell.category)))

        # Add descriptions
        self._add_lang_strings(shell_uri, AasPropertyUri.DESCRIPTION, shell.description)
        self._add_lang_strings(shell_uri, AasPropertyUri.DISPLAY_NAME, shell.display_name)

        # Add administration
        if shell.administration:
            admin_node = self._add_administrative_info(shell.administration)
            self.graph.add((shell_uri, AasPropertyUri.ADMINISTRATION, admin_node))

        # Add asset information
        asset_node = self._add_asset_information(shell.asset_information)
        self.graph.add((shell_uri, AasPropertyUri.ASSET_INFORMATION, asset_node))

        # Add derivedFrom reference
        if shell.derived_from:
            ref_node = self._add_reference(shell.derived_from)
            self.graph.add((shell_uri, AasPropertyUri.DERIVED_FROM, ref_node))

        # Add submodel references
        if shell.submodels:
            for submodel_ref in shell.submodels:
                ref_node = self._add_reference(submodel_ref)
                self.graph.add((shell_uri, AasPropertyUri.SUBMODELS, ref_node))

        # Add extensions
        self._add_extensions(shell_uri, getattr(shell, "extensions", None))

        return shell_uri

    def add_submodel(self, submodel: Submodel) -> URIRef:
        """Add a Submodel to the graph.

        Args:
            submodel: The Submodel to add

        Returns:
            URIRef for the submodel node
        """
        # Create URI from identifier
        submodel_uri = self._make_uri(submodel.id)

        # Add type triple
        self.graph.add((submodel_uri, RDF.type, AasTypeUri.SUBMODEL))

        # Add identifier
        self.graph.add((submodel_uri, AasPropertyUri.ID, Literal(submodel.id)))

        # Add idShort
        if submodel.id_short:
            self.graph.add((submodel_uri, AasPropertyUri.ID_SHORT, Literal(submodel.id_short)))

        # Add category
        if submodel.category:
            self.graph.add((submodel_uri, AasPropertyUri.CATEGORY, Literal(submodel.category)))

        # Add modelling kind
        if submodel.kind:
            self.graph.add((submodel_uri, AasPropertyUri.KIND, Literal(submodel.kind.value)))

        # Add descriptions
        self._add_lang_strings(submodel_uri, AasPropertyUri.DESCRIPTION, submodel.description)
        self._add_lang_strings(submodel_uri, AasPropertyUri.DISPLAY_NAME, submodel.display_name)

        # Add administration
        if submodel.administration:
            admin_node = self._add_administrative_info(submodel.administration)
            self.graph.add((submodel_uri, AasPropertyUri.ADMINISTRATION, admin_node))

        # Add semantic ID
        if hasattr(submodel, "semantic_id") and submodel.semantic_id:
            ref_node = self._add_reference(submodel.semantic_id)
            self.graph.add((submodel_uri, AasPropertyUri.SEMANTIC_ID, ref_node))

        # Add submodel elements
        if submodel.submodel_elements:
            for element in submodel.submodel_elements:
                element_node = self._add_submodel_element(element)
                self.graph.add((submodel_uri, AasPropertyUri.SUBMODEL_ELEMENTS, element_node))

        # Add qualifiers
        self._add_qualifiers(submodel_uri, getattr(submodel, "qualifiers", None))

        # Add extensions
        self._add_extensions(submodel_uri, getattr(submodel, "extensions", None))

        return submodel_uri

    def add_concept_description(self, cd: ConceptDescription) -> URIRef:
        """Add a ConceptDescription to the graph.

        Args:
            cd: The ConceptDescription to add

        Returns:
            URIRef for the concept description node
        """
        # Create URI from identifier
        cd_uri = self._make_uri(cd.id)

        # Add type triple
        self.graph.add((cd_uri, RDF.type, AasTypeUri.CONCEPT_DESCRIPTION))

        # Add identifier
        self.graph.add((cd_uri, AasPropertyUri.ID, Literal(cd.id)))

        # Add idShort
        if cd.id_short:
            self.graph.add((cd_uri, AasPropertyUri.ID_SHORT, Literal(cd.id_short)))

        # Add category
        if cd.category:
            self.graph.add((cd_uri, AasPropertyUri.CATEGORY, Literal(cd.category)))

        # Add descriptions
        self._add_lang_strings(cd_uri, AasPropertyUri.DESCRIPTION, cd.description)
        self._add_lang_strings(cd_uri, AasPropertyUri.DISPLAY_NAME, cd.display_name)

        # Add administration
        if cd.administration:
            admin_node = self._add_administrative_info(cd.administration)
            self.graph.add((cd_uri, AasPropertyUri.ADMINISTRATION, admin_node))

        # Add isCaseOf references (if present)
        if hasattr(cd, "is_case_of") and cd.is_case_of:
            for ref in cd.is_case_of:
                ref_node = self._add_reference(ref)
                self.graph.add((cd_uri, AAS.isCaseOf, ref_node))

        return cd_uri

    # -------------------------------------------------------------------------
    # Submodel Element methods
    # -------------------------------------------------------------------------

    def _add_submodel_element(self, element: SubmodelElementUnion) -> BNode | URIRef:
        """Add a SubmodelElement to the graph.

        Args:
            element: The SubmodelElement to add

        Returns:
            Node (BNode or URIRef) for the element
        """
        # Create a blank node for the element
        element_node = BNode()

        # Get model type for RDF type
        model_type = getattr(element, "model_type", None)
        rdf_type = get_rdf_type_for_model(model_type)
        if rdf_type:
            self.graph.add((element_node, RDF.type, rdf_type))

        # Add common attributes
        if hasattr(element, "id_short") and element.id_short:
            self.graph.add((element_node, AasPropertyUri.ID_SHORT, Literal(element.id_short)))

        if hasattr(element, "category") and element.category:
            self.graph.add((element_node, AasPropertyUri.CATEGORY, Literal(element.category)))

        # Add descriptions
        self._add_lang_strings(
            element_node, AasPropertyUri.DESCRIPTION, getattr(element, "description", None)
        )
        self._add_lang_strings(
            element_node, AasPropertyUri.DISPLAY_NAME, getattr(element, "display_name", None)
        )

        # Add semantic ID
        if hasattr(element, "semantic_id") and element.semantic_id:
            ref_node = self._add_reference(element.semantic_id)
            self.graph.add((element_node, AasPropertyUri.SEMANTIC_ID, ref_node))

        # Add qualifiers
        self._add_qualifiers(element_node, getattr(element, "qualifiers", None))

        # Add extensions
        self._add_extensions(element_node, getattr(element, "extensions", None))

        # Handle type-specific attributes
        self._add_element_specific_attributes(element_node, element, model_type)

        return element_node

    def _add_element_specific_attributes(
        self, node: BNode | URIRef, element: SubmodelElementUnion, model_type: str | None
    ) -> None:
        """Add type-specific attributes for a SubmodelElement.

        Args:
            node: The RDF node for the element
            element: The SubmodelElement
            model_type: The model type string
        """
        if model_type == "Property":
            self._add_property_attrs(node, element)
        elif model_type == "MultiLanguageProperty":
            self._add_mlp_attrs(node, element)
        elif model_type == "Range":
            self._add_range_attrs(node, element)
        elif model_type == "Blob":
            self._add_blob_attrs(node, element)
        elif model_type == "File":
            self._add_file_attrs(node, element)
        elif model_type == "ReferenceElement":
            self._add_reference_element_attrs(node, element)
        elif model_type == "SubmodelElementCollection":
            self._add_smc_attrs(node, element)
        elif model_type == "SubmodelElementList":
            self._add_sml_attrs(node, element)
        elif model_type == "Entity":
            self._add_entity_attrs(node, element)
        elif model_type == "RelationshipElement":
            self._add_relationship_attrs(node, element)
        elif model_type == "AnnotatedRelationshipElement":
            self._add_annotated_relationship_attrs(node, element)
        elif model_type == "Operation":
            self._add_operation_attrs(node, element)
        elif model_type == "BasicEventElement":
            self._add_event_attrs(node, element)
        # Capability has no additional attributes

    def _add_property_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add Property-specific attributes."""
        if hasattr(element, "value") and element.value is not None:
            value_type = getattr(element, "value_type", None)
            datatype = get_xsd_datatype(value_type)
            self.graph.add((node, AasPropertyUri.VALUE, Literal(element.value, datatype=datatype)))

        if hasattr(element, "value_type") and element.value_type:
            self.graph.add((node, AasPropertyUri.VALUE_TYPE, Literal(element.value_type)))

        if hasattr(element, "value_id") and element.value_id:
            ref_node = self._add_reference(element.value_id)
            self.graph.add((node, AasPropertyUri.VALUE_ID, ref_node))

    def _add_mlp_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add MultiLanguageProperty-specific attributes."""
        if hasattr(element, "value") and element.value:
            self._add_lang_strings(node, AasPropertyUri.VALUE, element.value)

        if hasattr(element, "value_id") and element.value_id:
            ref_node = self._add_reference(element.value_id)
            self.graph.add((node, AasPropertyUri.VALUE_ID, ref_node))

    def _add_range_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add Range-specific attributes."""
        value_type = getattr(element, "value_type", None)
        datatype = get_xsd_datatype(value_type)

        if hasattr(element, "min") and element.min is not None:
            self.graph.add((node, AasPropertyUri.MIN, Literal(element.min, datatype=datatype)))

        if hasattr(element, "max") and element.max is not None:
            self.graph.add((node, AasPropertyUri.MAX, Literal(element.max, datatype=datatype)))

        if value_type:
            self.graph.add((node, AasPropertyUri.VALUE_TYPE, Literal(value_type)))

    def _add_blob_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add Blob-specific attributes."""
        if hasattr(element, "value") and element.value is not None:
            self.graph.add(
                (node, AasPropertyUri.VALUE, Literal(element.value, datatype=XSD.base64Binary))
            )

        if hasattr(element, "content_type") and element.content_type:
            self.graph.add((node, AasPropertyUri.CONTENT_TYPE, Literal(element.content_type)))

    def _add_file_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add File-specific attributes."""
        if hasattr(element, "value") and element.value:
            literal = Literal(element.value, datatype=XSD.anyURI)
            self.graph.add((node, AasPropertyUri.VALUE, literal))

        if hasattr(element, "content_type") and element.content_type:
            self.graph.add((node, AasPropertyUri.CONTENT_TYPE, Literal(element.content_type)))

    def _add_reference_element_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add ReferenceElement-specific attributes."""
        if hasattr(element, "value") and element.value:
            ref_node = self._add_reference(element.value)
            self.graph.add((node, AasPropertyUri.VALUE, ref_node))

    def _add_smc_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add SubmodelElementCollection-specific attributes."""
        if hasattr(element, "value") and element.value:
            for child in element.value:
                child_node = self._add_submodel_element(child)
                self.graph.add((node, AasPropertyUri.VALUE, child_node))

    def _add_sml_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add SubmodelElementList-specific attributes."""
        if hasattr(element, "order_relevant") and element.order_relevant is not None:
            self.graph.add(
                (
                    node,
                    AasPropertyUri.ORDER_RELEVANT,
                    Literal(element.order_relevant, datatype=XSD.boolean),
                )
            )

        if hasattr(element, "value_type_list_element") and element.value_type_list_element:
            self.graph.add(
                (
                    node,
                    AasPropertyUri.VALUE_TYPE_LIST_ELEMENT,
                    Literal(element.value_type_list_element),
                )
            )

        if hasattr(element, "type_value_list_element") and element.type_value_list_element:
            self.graph.add(
                (
                    node,
                    AasPropertyUri.TYPE_VALUE_LIST_ELEMENT,
                    Literal(element.type_value_list_element),
                )
            )

        if hasattr(element, "semantic_id_list_element") and element.semantic_id_list_element:
            ref_node = self._add_reference(element.semantic_id_list_element)
            self.graph.add((node, AasPropertyUri.SEMANTIC_ID_LIST_ELEMENT, ref_node))

        if hasattr(element, "value") and element.value:
            for child in element.value:
                child_node = self._add_submodel_element(child)
                self.graph.add((node, AasPropertyUri.VALUE, child_node))

    def _add_entity_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add Entity-specific attributes."""
        if hasattr(element, "entity_type") and element.entity_type:
            self.graph.add((node, AasPropertyUri.ENTITY_TYPE, Literal(element.entity_type.value)))

        if hasattr(element, "global_asset_id") and element.global_asset_id:
            self.graph.add(
                (
                    node,
                    AasPropertyUri.GLOBAL_ASSET_ID_ENTITY,
                    Literal(element.global_asset_id, datatype=XSD.anyURI),
                )
            )

        if hasattr(element, "specific_asset_ids") and element.specific_asset_ids:
            for specific_id in element.specific_asset_ids:
                specific_node = self._add_specific_asset_id(specific_id)
                self.graph.add((node, AasPropertyUri.SPECIFIC_ASSET_IDS, specific_node))

        if hasattr(element, "statements") and element.statements:
            for statement in element.statements:
                stmt_node = self._add_submodel_element(statement)
                self.graph.add((node, AasPropertyUri.STATEMENTS, stmt_node))

    def _add_relationship_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add RelationshipElement-specific attributes."""
        if hasattr(element, "first") and element.first:
            ref_node = self._add_reference(element.first)
            self.graph.add((node, AasPropertyUri.FIRST, ref_node))

        if hasattr(element, "second") and element.second:
            ref_node = self._add_reference(element.second)
            self.graph.add((node, AasPropertyUri.SECOND, ref_node))

    def _add_annotated_relationship_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add AnnotatedRelationshipElement-specific attributes."""
        # Add base relationship attributes
        self._add_relationship_attrs(node, element)

        # Add annotations
        if hasattr(element, "annotations") and element.annotations:
            for annotation in element.annotations:
                ann_node = self._add_submodel_element(annotation)
                self.graph.add((node, AasPropertyUri.ANNOTATIONS, ann_node))

    def _add_operation_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add Operation-specific attributes."""
        if hasattr(element, "input_variables") and element.input_variables:
            for var in element.input_variables:
                var_node = self._add_operation_variable(var)
                self.graph.add((node, AasPropertyUri.INPUT_VARIABLES, var_node))

        if hasattr(element, "output_variables") and element.output_variables:
            for var in element.output_variables:
                var_node = self._add_operation_variable(var)
                self.graph.add((node, AasPropertyUri.OUTPUT_VARIABLES, var_node))

        if hasattr(element, "inoutput_variables") and element.inoutput_variables:
            for var in element.inoutput_variables:
                var_node = self._add_operation_variable(var)
                self.graph.add((node, AasPropertyUri.INOUTPUT_VARIABLES, var_node))

    def _add_operation_variable(self, var: Any) -> BNode:
        """Add an OperationVariable to the graph."""
        var_node = BNode()
        self.graph.add((var_node, RDF.type, AAS.OperationVariable))

        if hasattr(var, "value") and var.value:
            element_node = self._add_submodel_element(var.value)
            self.graph.add((var_node, AasPropertyUri.VALUE, element_node))

        return var_node

    def _add_event_attrs(self, node: BNode | URIRef, element: Any) -> None:
        """Add BasicEventElement-specific attributes."""
        if hasattr(element, "observed") and element.observed:
            ref_node = self._add_reference(element.observed)
            self.graph.add((node, AasPropertyUri.OBSERVED, ref_node))

        if hasattr(element, "direction") and element.direction:
            self.graph.add((node, AasPropertyUri.DIRECTION, Literal(element.direction.value)))

        if hasattr(element, "state") and element.state:
            self.graph.add((node, AasPropertyUri.STATE, Literal(element.state.value)))

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _make_uri(self, identifier: str) -> URIRef:
        """Create a URIRef from an identifier.

        Args:
            identifier: AAS identifier (often a URN or URL)

        Returns:
            URIRef for the identifier
        """
        # If the identifier is already a valid URI, use it directly
        if identifier.startswith(("http://", "https://", "urn:")):
            return URIRef(identifier)

        # Otherwise, create a URI using base_uri or a default scheme
        if self.base_uri:
            return URIRef(f"{self.base_uri}/{identifier}")

        # Default: use a URN scheme
        return URIRef(f"urn:aas:{identifier}")

    def _add_lang_strings(
        self, subject: URIRef | BNode, predicate: URIRef, lang_strings: list[Any] | None
    ) -> None:
        """Add multilingual string literals to the graph.

        Args:
            subject: Subject node
            predicate: Predicate URI
            lang_strings: List of LangStringTextType objects
        """
        if not lang_strings:
            return

        for ls in lang_strings:
            if hasattr(ls, "language") and hasattr(ls, "text"):
                lang = ls.language if ls.language else None
                self.graph.add((subject, predicate, Literal(ls.text, lang=lang)))
            elif isinstance(ls, dict):
                lang = ls.get("language")
                text = ls.get("text", "")
                self.graph.add((subject, predicate, Literal(text, lang=lang)))

    def _add_reference(self, ref: Reference) -> BNode:
        """Add a Reference to the graph.

        Args:
            ref: The Reference to add

        Returns:
            BNode for the reference
        """
        ref_node = BNode()
        self.graph.add((ref_node, RDF.type, AasTypeUri.REFERENCE))

        # Add reference type
        if hasattr(ref, "type") and ref.type:
            self.graph.add((ref_node, AasPropertyUri.TYPE, Literal(ref.type.value)))

        # Add keys
        if hasattr(ref, "keys") and ref.keys:
            for key in ref.keys:
                key_node = BNode()
                self.graph.add((key_node, RDF.type, AasTypeUri.KEY))
                self.graph.add((key_node, AasPropertyUri.KEY_TYPE, Literal(key.type.value)))
                self.graph.add((key_node, AasPropertyUri.KEY_VALUE, Literal(key.value)))
                self.graph.add((ref_node, AasPropertyUri.KEYS, key_node))

        # Add referred semantic ID (if present)
        if hasattr(ref, "referred_semantic_id") and ref.referred_semantic_id:
            referred_node = self._add_reference(ref.referred_semantic_id)
            self.graph.add((ref_node, AasPropertyUri.REFERRED_SEMANTIC_ID, referred_node))

        return ref_node

    def _add_administrative_info(self, admin: Any) -> BNode:
        """Add AdministrativeInformation to the graph.

        Args:
            admin: The AdministrativeInformation to add

        Returns:
            BNode for the administrative info
        """
        admin_node = BNode()
        self.graph.add((admin_node, RDF.type, AasTypeUri.ADMINISTRATIVE_INFORMATION))

        if hasattr(admin, "version") and admin.version:
            self.graph.add((admin_node, AasPropertyUri.VERSION, Literal(admin.version)))

        if hasattr(admin, "revision") and admin.revision:
            self.graph.add((admin_node, AasPropertyUri.REVISION, Literal(admin.revision)))

        if hasattr(admin, "creator") and admin.creator:
            ref_node = self._add_reference(admin.creator)
            self.graph.add((admin_node, AasPropertyUri.CREATOR, ref_node))

        if hasattr(admin, "template_id") and admin.template_id:
            self.graph.add((admin_node, AasPropertyUri.TEMPLATE_ID, Literal(admin.template_id)))

        return admin_node

    def _add_asset_information(self, asset_info: Any) -> BNode:
        """Add AssetInformation to the graph.

        Args:
            asset_info: The AssetInformation to add

        Returns:
            BNode for the asset info
        """
        asset_node = BNode()
        self.graph.add((asset_node, RDF.type, AasTypeUri.ASSET_INFORMATION))

        # Add asset kind
        if hasattr(asset_info, "asset_kind") and asset_info.asset_kind:
            self.graph.add(
                (asset_node, AasPropertyUri.ASSET_KIND, Literal(asset_info.asset_kind.value))
            )

        # Add global asset ID
        if hasattr(asset_info, "global_asset_id") and asset_info.global_asset_id:
            self.graph.add(
                (
                    asset_node,
                    AasPropertyUri.GLOBAL_ASSET_ID,
                    Literal(asset_info.global_asset_id, datatype=XSD.anyURI),
                )
            )

        # Add asset type
        if hasattr(asset_info, "asset_type") and asset_info.asset_type:
            self.graph.add((asset_node, AasPropertyUri.ASSET_TYPE, Literal(asset_info.asset_type)))

        # Add specific asset IDs
        if hasattr(asset_info, "specific_asset_ids") and asset_info.specific_asset_ids:
            for specific_id in asset_info.specific_asset_ids:
                specific_node = self._add_specific_asset_id(specific_id)
                self.graph.add((asset_node, AasPropertyUri.SPECIFIC_ASSET_IDS, specific_node))

        # Add default thumbnail
        if hasattr(asset_info, "default_thumbnail") and asset_info.default_thumbnail:
            thumb_node = self._add_resource(asset_info.default_thumbnail)
            self.graph.add((asset_node, AasPropertyUri.DEFAULT_THUMBNAIL, thumb_node))

        return asset_node

    def _add_specific_asset_id(self, specific_id: Any) -> BNode:
        """Add a SpecificAssetId to the graph.

        Args:
            specific_id: The SpecificAssetId to add

        Returns:
            BNode for the specific asset ID
        """
        node = BNode()
        self.graph.add((node, RDF.type, AasTypeUri.SPECIFIC_ASSET_ID))

        if hasattr(specific_id, "name") and specific_id.name:
            self.graph.add((node, AAS.name, Literal(specific_id.name)))

        if hasattr(specific_id, "value") and specific_id.value:
            self.graph.add((node, AasPropertyUri.VALUE, Literal(specific_id.value)))

        if hasattr(specific_id, "external_subject_id") and specific_id.external_subject_id:
            ref_node = self._add_reference(specific_id.external_subject_id)
            self.graph.add((node, AAS.externalSubjectId, ref_node))

        if hasattr(specific_id, "semantic_id") and specific_id.semantic_id:
            ref_node = self._add_reference(specific_id.semantic_id)
            self.graph.add((node, AasPropertyUri.SEMANTIC_ID, ref_node))

        return node

    def _add_resource(self, resource: Any) -> BNode:
        """Add a Resource (thumbnail) to the graph.

        Args:
            resource: The Resource to add

        Returns:
            BNode for the resource
        """
        node = BNode()
        self.graph.add((node, RDF.type, AasTypeUri.RESOURCE))

        if hasattr(resource, "path") and resource.path:
            self.graph.add((node, AasPropertyUri.PATH, Literal(resource.path, datatype=XSD.anyURI)))

        if hasattr(resource, "content_type") and resource.content_type:
            self.graph.add((node, AasPropertyUri.CONTENT_TYPE, Literal(resource.content_type)))

        return node

    def _add_qualifiers(self, subject: URIRef | BNode, qualifiers: list[Any] | None) -> None:
        """Add qualifiers to a subject node.

        Args:
            subject: Subject node
            qualifiers: List of Qualifier objects
        """
        if not qualifiers:
            return

        for qualifier in qualifiers:
            qual_node = BNode()
            self.graph.add((qual_node, RDF.type, AasTypeUri.QUALIFIER))

            if hasattr(qualifier, "kind") and qualifier.kind:
                self.graph.add((qual_node, AasPropertyUri.QUALIFIER_KIND, Literal(qualifier.kind)))

            if hasattr(qualifier, "type") and qualifier.type:
                self.graph.add((qual_node, AasPropertyUri.QUALIFIER_TYPE, Literal(qualifier.type)))

            if hasattr(qualifier, "value") and qualifier.value is not None:
                value_type = getattr(qualifier, "value_type", None)
                datatype = get_xsd_datatype(value_type)
                literal = Literal(qualifier.value, datatype=datatype)
                self.graph.add((qual_node, AasPropertyUri.QUALIFIER_VALUE, literal))

            if hasattr(qualifier, "value_type") and qualifier.value_type:
                self.graph.add(
                    (qual_node, AasPropertyUri.QUALIFIER_VALUE_TYPE, Literal(qualifier.value_type))
                )

            if hasattr(qualifier, "value_id") and qualifier.value_id:
                ref_node = self._add_reference(qualifier.value_id)
                self.graph.add((qual_node, AasPropertyUri.VALUE_ID, ref_node))

            if hasattr(qualifier, "semantic_id") and qualifier.semantic_id:
                ref_node = self._add_reference(qualifier.semantic_id)
                self.graph.add((qual_node, AasPropertyUri.SEMANTIC_ID, ref_node))

            self.graph.add((subject, AasPropertyUri.QUALIFIERS, qual_node))

    def _add_extensions(self, subject: URIRef | BNode, extensions: list[Any] | None) -> None:
        """Add extensions to a subject node.

        Args:
            subject: Subject node
            extensions: List of Extension objects
        """
        if not extensions:
            return

        for extension in extensions:
            ext_node = BNode()
            self.graph.add((ext_node, RDF.type, AasTypeUri.EXTENSION))

            if hasattr(extension, "name") and extension.name:
                self.graph.add((ext_node, AasPropertyUri.EXTENSION_NAME, Literal(extension.name)))

            if hasattr(extension, "value") and extension.value is not None:
                value_type = getattr(extension, "value_type", None)
                datatype = get_xsd_datatype(value_type)
                literal = Literal(extension.value, datatype=datatype)
                self.graph.add((ext_node, AasPropertyUri.EXTENSION_VALUE, literal))

            if hasattr(extension, "value_type") and extension.value_type:
                self.graph.add(
                    (ext_node, AasPropertyUri.EXTENSION_VALUE_TYPE, Literal(extension.value_type))
                )

            if hasattr(extension, "semantic_id") and extension.semantic_id:
                ref_node = self._add_reference(extension.semantic_id)
                self.graph.add((ext_node, AasPropertyUri.SEMANTIC_ID, ref_node))

            if hasattr(extension, "refers_to") and extension.refers_to:
                for ref in extension.refers_to:
                    ref_node = self._add_reference(ref)
                    self.graph.add((ext_node, AAS.refersTo, ref_node))

            self.graph.add((subject, AasPropertyUri.EXTENSIONS, ext_node))
