"""XML serialization for IDTA-01001 Part 1 AAS Environment.

Implements bidirectional XML serialization following the IDTA-01001 v3.1 XML schema.
Uses stdlib xml.etree.ElementTree for zero-dependency operation.

Supports:
- AssetAdministrationShell serialization
- Submodel serialization (including all 23 SubmodelElement types)
- ConceptDescription serialization
- Full round-trip (export -> import preserves data)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any
from xml.etree import ElementTree as ET

from pydantic import BaseModel

from titan.core.model import (
    AssetAdministrationShell,
    ConceptDescription,
    Submodel,
)
from titan.core.model.identifiers import AasSubmodelElements

logger = logging.getLogger(__name__)

# AAS XML namespace (IDTA-01001 v3.1)
AAS_NS = "https://admin-shell.io/aas/3/0"
AAS_NS_PREFIX = f"{{{AAS_NS}}}"

# Register namespace prefix for clean output
ET.register_namespace("aas", AAS_NS)


class XmlSerializer:
    """Serialize Pydantic AAS models to IDTA-compliant XML."""

    def __init__(self) -> None:
        self.ns = AAS_NS
        self.ns_prefix = AAS_NS_PREFIX

    def serialize_environment(
        self,
        shells: list[AssetAdministrationShell],
        submodels: list[Submodel],
        concept_descriptions: list[ConceptDescription] | None = None,
    ) -> bytes:
        """Serialize AAS environment to XML bytes.

        Args:
            shells: List of Asset Administration Shells
            submodels: List of Submodels
            concept_descriptions: Optional list of Concept Descriptions

        Returns:
            UTF-8 encoded XML bytes
        """
        concept_descriptions = concept_descriptions or []

        # Create root environment element
        # Note: ET.register_namespace handles the xmlns:aas declaration
        root = ET.Element(f"{self.ns_prefix}environment")

        # Add shells
        if shells:
            shells_elem = ET.SubElement(root, f"{self.ns_prefix}assetAdministrationShells")
            for shell in shells:
                shell_elem = self._model_to_element(shell, "assetAdministrationShell")
                shells_elem.append(shell_elem)

        # Add submodels
        if submodels:
            submodels_elem = ET.SubElement(root, f"{self.ns_prefix}submodels")
            for submodel in submodels:
                sm_elem = self._model_to_element(submodel, "submodel")
                submodels_elem.append(sm_elem)

        # Add concept descriptions
        if concept_descriptions:
            cds_elem = ET.SubElement(root, f"{self.ns_prefix}conceptDescriptions")
            for cd in concept_descriptions:
                cd_elem = self._model_to_element(cd, "conceptDescription")
                cds_elem.append(cd_elem)

        # Convert to string with XML declaration
        ET.indent(root, space="  ")
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
        return xml_str.encode("utf-8")

    def _model_to_element(self, model: BaseModel, tag: str) -> ET.Element:
        """Convert a Pydantic model to an XML element.

        Args:
            model: Pydantic model instance
            tag: XML tag name (without namespace)

        Returns:
            XML Element
        """
        element = ET.Element(f"{self.ns_prefix}{tag}")

        # Get model data with aliases
        data = model.model_dump(mode="json", by_alias=True, exclude_none=True)

        # Add each field as subelement
        for key, value in data.items():
            self._value_to_element(value, key, element)

        return element

    def _value_to_element(self, value: Any, tag: str, parent: ET.Element) -> None:
        """Convert a value to XML subelement(s).

        Args:
            value: The value to convert
            tag: XML tag name
            parent: Parent element to append to
        """
        if value is None:
            return  # Omit None values

        if isinstance(value, dict):
            # Nested object
            elem = ET.SubElement(parent, f"{self.ns_prefix}{tag}")
            for k, v in value.items():
                self._value_to_element(v, k, elem)

        elif isinstance(value, list):
            # List of items - wrap in container element
            if not value:
                return  # Skip empty lists

            # Check if items are primitives or objects
            if value and isinstance(value[0], dict):
                # List of objects - each gets its own element
                container = ET.SubElement(parent, f"{self.ns_prefix}{tag}")

                # Special handling for SubmodelElements: use modelType for tag name
                if tag == "submodelElements" and "modelType" in value[0]:
                    for item in value:
                        # Use modelType to determine element-specific tag
                        model_type = item.get("modelType", "submodelElement")
                        # Convert to camelCase with lowercase first letter
                        # e.g., "Property" -> "property",
                        # "SubmodelElementCollection" -> "submodelElementCollection"
                        item_tag = model_type[0].lower() + model_type[1:]
                        self._value_to_element(item, item_tag, container)
                # Special handling for "value" lists that contain SubmodelElements
                # (e.g., SubmodelElementCollection.value, AnnotatedRelationshipElement.annotations)
                elif tag == "value" and "modelType" in value[0]:
                    for item in value:
                        model_type = item.get("modelType", "submodelElement")
                        item_tag = model_type[0].lower() + model_type[1:]
                        self._value_to_element(item, item_tag, container)
                # Special handling for LangString types (language + text)
                elif tag == "value" and "language" in value[0] and "text" in value[0]:
                    for item in value:
                        self._value_to_element(item, "langStringTextType", container)
                # Special handling for Reference objects: always use "reference" tag
                elif "type" in value[0] and "keys" in value[0]:
                    for item in value:
                        self._value_to_element(item, "reference", container)
                else:
                    # Standard singular tag name
                    item_tag = self._singularize(tag)
                    for item in value:
                        self._value_to_element(item, item_tag, container)
            else:
                # List of primitives - each as separate element
                for item in value:
                    elem = ET.SubElement(parent, f"{self.ns_prefix}{tag}")
                    elem.text = self._to_text(item)

        elif isinstance(value, bool):
            # Boolean must come before int check (bool is subclass of int)
            elem = ET.SubElement(parent, f"{self.ns_prefix}{tag}")
            elem.text = "true" if value else "false"

        elif isinstance(value, (str, int, float)):
            elem = ET.SubElement(parent, f"{self.ns_prefix}{tag}")
            elem.text = str(value)

        elif isinstance(value, Enum):
            elem = ET.SubElement(parent, f"{self.ns_prefix}{tag}")
            elem.text = value.value

        else:
            # Unknown type - convert to string
            elem = ET.SubElement(parent, f"{self.ns_prefix}{tag}")
            elem.text = str(value)

    def _singularize(self, tag: str) -> str:
        """Get singular form of a plural tag name.

        Args:
            tag: Plural tag name (e.g., 'submodels', 'keys')

        Returns:
            Singular form (e.g., 'submodel', 'key')
        """
        # Common pluralization patterns in AAS
        if tag.endswith("ies"):
            return tag[:-3] + "y"
        elif tag.endswith("ses"):
            return tag[:-2]
        elif tag.endswith("s") and not tag.endswith("ss"):
            return tag[:-1]
        return tag

    def _to_text(self, value: Any) -> str:
        """Convert a value to XML text content."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, Enum):
            return str(value.value)
        return str(value)


class XmlDeserializer:
    """Deserialize IDTA-compliant XML to Pydantic AAS models."""

    SUBMODEL_ELEMENT_TAGS = frozenset(value[0].lower() + value[1:] for value in AasSubmodelElements)

    def __init__(self) -> None:
        self.ns = AAS_NS
        self.ns_prefix = AAS_NS_PREFIX

    def parse_environment(
        self, xml_bytes: bytes
    ) -> tuple[
        list[AssetAdministrationShell],
        list[Submodel],
        list[ConceptDescription],
    ]:
        """Parse XML environment to Pydantic models.

        Args:
            xml_bytes: UTF-8 encoded XML bytes

        Returns:
            Tuple of (shells, submodels, concept_descriptions)
        """
        # nosec B314 - XML data comes from trusted AASX packages, not arbitrary external input
        root = ET.fromstring(xml_bytes)  # nosec B314

        shells: list[AssetAdministrationShell] = []
        submodels: list[Submodel] = []
        concept_descriptions: list[ConceptDescription] = []

        # Parse shells
        shells_elem = root.find(f"{self.ns_prefix}assetAdministrationShells")
        if shells_elem is not None:
            for shell_elem in shells_elem.findall(f"{self.ns_prefix}assetAdministrationShell"):
                data = self._element_to_dict(shell_elem)
                try:
                    shell = AssetAdministrationShell.model_validate(data)
                    shells.append(shell)
                except Exception as e:
                    logger.warning(f"Failed to parse shell: {e}")

        # Parse submodels
        submodels_elem = root.find(f"{self.ns_prefix}submodels")
        if submodels_elem is not None:
            for sm_elem in submodels_elem.findall(f"{self.ns_prefix}submodel"):
                data = self._element_to_dict(sm_elem)
                try:
                    submodel = Submodel.model_validate(data)
                    submodels.append(submodel)
                except Exception as e:
                    logger.warning(f"Failed to parse submodel: {e}")

        # Parse concept descriptions
        cds_elem = root.find(f"{self.ns_prefix}conceptDescriptions")
        if cds_elem is not None:
            for cd_elem in cds_elem.findall(f"{self.ns_prefix}conceptDescription"):
                data = self._element_to_dict(cd_elem)
                try:
                    cd = ConceptDescription.model_validate(data)
                    concept_descriptions.append(cd)
                except Exception as e:
                    logger.warning(f"Failed to parse concept description: {e}")

        logger.info(
            f"Parsed {len(shells)} shells, {len(submodels)} submodels, "
            f"{len(concept_descriptions)} concept descriptions"
        )

        return shells, submodels, concept_descriptions

    # Tags that are known to contain lists of items
    LIST_CONTAINER_TAGS = frozenset(
        {
            "assetAdministrationShells",
            "submodels",
            "conceptDescriptions",
            "submodelElements",
            "value",
            "keys",
            "description",
            "displayName",
            "extensions",
            "qualifiers",
            "embeddedDataSpecifications",
            "specificAssetIds",
            "isCaseOf",
            "supplementalSemanticIds",
            "statements",
            "annotations",
            "inputVariables",
            "outputVariables",
            "inoutputVariables",
            "valueList",
            "preferredName",
            "shortName",
            "definition",
        }
    )

    def _element_to_dict(self, element: ET.Element) -> dict[str, Any]:
        """Convert an XML element to a dict suitable for Pydantic validation.

        Args:
            element: XML element

        Returns:
            Dictionary that can be passed to model_validate()
        """
        result: dict[str, Any] = {}

        # Process child elements
        for child in element:
            # Strip namespace from tag
            tag = self._strip_ns(child.tag)

            # Check if this is a list container
            if self._is_list_container(child, tag):
                # Parse as list of child elements
                items = []
                for item in child:
                    item_value = self._parse_element_value(item)
                    items.append(item_value)
                result[tag] = items
            else:
                # Parse as single value
                result[tag] = self._parse_element_value(child)

        return result

    # Tags that are known to contain boolean values
    BOOLEAN_TAGS = frozenset(
        {
            "min",
            "max",
            "nom",
            "typ",  # LevelTypeSpec
            "allowDuplicates",
        }
    )

    def _parse_element_value(self, element: ET.Element) -> Any:
        """Parse an element's value (text content or nested structure).

        Args:
            element: XML element

        Returns:
            Parsed value (dict, list, string, or bool)
        """
        tag = self._strip_ns(element.tag)

        # Check for child elements
        if len(element) > 0:
            # Has children - recursively parse as dict
            data = self._element_to_dict(element)
            if (
                tag in self.SUBMODEL_ELEMENT_TAGS
                and "modelType" not in data
                and "model_type" not in data
            ):
                data["modelType"] = tag[0].upper() + tag[1:]
            return data
        else:
            # Text content only
            text = element.text
            if text is None:
                return None

            text = text.strip()

            # Only parse as boolean for known boolean tags
            if tag in self.BOOLEAN_TAGS:
                if text.lower() == "true":
                    return True
                elif text.lower() == "false":
                    return False

            # Keep all other values as strings - let Pydantic do the type coercion
            # This prevents issues like "100" being converted to int when it should
            # remain a string (e.g., Property.value)
            return text

    def _is_list_container(self, element: ET.Element, tag: str) -> bool:
        """Check if an element is a container for a list of items.

        Args:
            element: XML element
            tag: The tag name of the element

        Returns:
            True if element is a known list container or has multiple children
        """
        # Check if this is a known list container tag with child elements
        if tag in self.LIST_CONTAINER_TAGS:
            return len(element) > 0

        if len(element) == 0:
            return False

        # Check if all children have the same tag (heuristic for unknown lists)
        child_tags = [self._strip_ns(child.tag) for child in element]
        return len(set(child_tags)) == 1 and len(child_tags) > 1

    def _strip_ns(self, tag: str) -> str:
        """Strip namespace prefix from tag.

        Args:
            tag: Tag with namespace (e.g., '{https://...}tagName')

        Returns:
            Tag without namespace (e.g., 'tagName')
        """
        if tag.startswith("{"):
            return tag.split("}", 1)[1]
        return tag
