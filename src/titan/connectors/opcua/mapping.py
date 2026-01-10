"""AAS to OPC UA mapping.

Maps between AAS idShortPath and OPC UA NodeIds.
Follows IDTA-01006 (AAS over OPC UA).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NodeMapping:
    """Mapping between AAS element and OPC UA node."""

    id_short_path: str
    node_id: str
    data_type: str | None = None
    aas_id: str | None = None
    submodel_id: str | None = None
    direction: str = "bidirectional"  # "read", "write", "bidirectional"


class AasOpcUaMapper:
    """Maps between AAS model and OPC UA information model.

    Follows IDTA-01006 specification for AAS over OPC UA.
    """

    # OPC UA namespace for AAS
    AAS_NAMESPACE = "http://opcfoundation.org/UA/AAS/"

    def __init__(self, namespace_index: int = 2) -> None:
        """Initialize mapper.

        Args:
            namespace_index: OPC UA namespace index for AAS nodes
        """
        self.namespace_index = namespace_index
        self._mappings: dict[str, NodeMapping] = {}
        self._reverse_mappings: dict[str, str] = {}

    def add_mapping(self, mapping: NodeMapping) -> None:
        """Add a mapping between AAS path and OPC UA node.

        Args:
            mapping: The mapping to add
        """
        key = f"{mapping.submodel_id or ''}#{mapping.id_short_path}"
        self._mappings[key] = mapping
        self._reverse_mappings[mapping.node_id] = key
        logger.debug(f"Added mapping: {key} <-> {mapping.node_id}")

    def get_node_id(self, submodel_id: str, id_short_path: str) -> str | None:
        """Get OPC UA NodeId for an AAS element.

        Args:
            submodel_id: The submodel identifier
            id_short_path: Path to the element

        Returns:
            OPC UA NodeId string or None
        """
        key = f"{submodel_id}#{id_short_path}"
        mapping = self._mappings.get(key)
        return mapping.node_id if mapping else None

    def get_id_short_path(self, node_id: str) -> tuple[str | None, str | None]:
        """Get AAS idShortPath for an OPC UA node.

        Args:
            node_id: The OPC UA NodeId

        Returns:
            Tuple of (submodel_id, id_short_path) or (None, None)
        """
        key = self._reverse_mappings.get(node_id)
        if key:
            parts = key.split("#", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
            return None, parts[0]
        return None, None

    def generate_node_id(
        self,
        submodel_id: str,
        id_short_path: str,
    ) -> str:
        """Generate an OPC UA NodeId for an AAS element.

        Follows IDTA-01006 naming convention.

        Args:
            submodel_id: The submodel identifier
            id_short_path: Path to the element

        Returns:
            Generated OPC UA NodeId string
        """
        # Clean the path for OPC UA compatibility
        safe_path = id_short_path.replace("/", ".").replace("[", "_").replace("]", "")
        # Create NodeId with namespace index and string identifier
        return f"ns={self.namespace_index};s={submodel_id}/{safe_path}"

    def map_submodel(
        self,
        submodel: Any,
        base_node_id: str | None = None,
    ) -> list[NodeMapping]:
        """Generate mappings for all elements in a submodel.

        Args:
            submodel: The Submodel object
            base_node_id: Optional base NodeId prefix

        Returns:
            List of generated mappings
        """
        mappings = []

        def process_element(element: Any, path: str) -> None:
            # Generate node ID for this element
            node_id = base_node_id or self.generate_node_id(submodel.id, path)

            # Determine data type from element type
            data_type = self._get_opc_data_type(element)

            mapping = NodeMapping(
                id_short_path=path,
                node_id=node_id,
                data_type=data_type,
                aas_id=None,  # Could link to AAS if available
                submodel_id=submodel.id,
            )
            mappings.append(mapping)
            self.add_mapping(mapping)

            # Recursively process nested elements
            if hasattr(element, "value") and isinstance(element.value, list):
                for child in element.value:
                    if hasattr(child, "id_short"):
                        child_path = f"{path}/{child.id_short}"
                        process_element(child, child_path)

        # Process all top-level elements
        if hasattr(submodel, "submodel_elements") and submodel.submodel_elements:
            for element in submodel.submodel_elements:
                if hasattr(element, "id_short"):
                    process_element(element, element.id_short)

        return mappings

    def _get_opc_data_type(self, element: Any) -> str:
        """Determine OPC UA data type from AAS element type.

        Args:
            element: The SubmodelElement

        Returns:
            OPC UA data type name
        """
        element_type = type(element).__name__

        type_mapping = {
            "Property": "BaseDataType",
            "MultiLanguageProperty": "LocalizedText",
            "Range": "Range",
            "Blob": "ByteString",
            "File": "String",
            "ReferenceElement": "ReferenceDescription",
            "SubmodelElementCollection": "FolderType",
            "SubmodelElementList": "FolderType",
            "Entity": "FolderType",
            "Operation": "MethodType",
        }

        return type_mapping.get(element_type, "BaseDataType")

    def to_opc_value(self, aas_value: Any, data_type: str) -> Any:
        """Convert AAS value to OPC UA value.

        Args:
            aas_value: The AAS element value
            data_type: Target OPC UA data type

        Returns:
            OPC UA compatible value
        """
        # Most values pass through directly
        # Special handling for complex types
        if data_type == "LocalizedText" and isinstance(aas_value, list):
            # MultiLanguageProperty value
            if aas_value:
                return aas_value[0].get("text", "")
        return aas_value

    def from_opc_value(self, opc_value: Any, data_type: str) -> Any:
        """Convert OPC UA value to AAS value.

        Args:
            opc_value: The OPC UA value
            data_type: Source OPC UA data type

        Returns:
            AAS compatible value
        """
        # Most values pass through directly
        return opc_value
