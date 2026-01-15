"""IDTA projection modifiers for Titan-AAS.

Implements the serialization modifiers from IDTA-01002 Part 2:
- $value: Return only the value (strip metadata)
- $metadata: Return only metadata (strip value)
- $reference: Return as Reference
- $path: Navigate to nested element by idShortPath
- level=deep|core: Control nesting depth
- extent=withBlobValue|withoutBlobValue: Control blob inclusion
- content=normal|metadata|value|reference|path: Content modifier

This is the slow path - used when modifiers are present.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class ProjectionModifiers:
    """Container for projection modifiers."""

    def __init__(
        self,
        level: str | None = None,
        extent: str | None = None,
        content: str | None = None,
    ):
        self.level = level or "deep"
        self.extent = extent or "withBlobValue"
        self.content = content or "normal"

    @property
    def is_deep(self) -> bool:
        return self.level == "deep"

    @property
    def is_core(self) -> bool:
        return self.level == "core"

    @property
    def include_blob_value(self) -> bool:
        return self.extent == "withBlobValue"


# Metadata fields that should be included in $metadata projection
METADATA_FIELDS = frozenset(
    {
        "modelType",
        "idShort",
        "semanticId",
        "supplementalSemanticIds",
        "qualifiers",
        "category",
        "description",
        "displayName",
        "extensions",
        "embeddedDataSpecifications",
    }
)

# Value fields that should be included in $value projection
VALUE_FIELDS = frozenset(
    {
        "modelType",
        "value",
        "valueType",
        "min",
        "max",
        "contentType",
        "first",
        "second",
        "entityType",
        "globalAssetId",
        "specificAssetIds",
        "observed",
        "direction",
        "state",
    }
)


def apply_projection(
    payload: dict[str, Any],
    modifiers: ProjectionModifiers | None = None,
) -> dict[str, Any]:
    """Apply IDTA modifiers to payload (slow path).

    Args:
        payload: The JSON payload to project
        modifiers: Projection modifiers to apply

    Returns:
        Projected payload
    """
    if modifiers is None:
        return payload

    result = deepcopy(payload)

    # Apply content modifier
    if modifiers.content == "metadata":
        result = _project_metadata(result)
    elif modifiers.content == "value":
        result = _project_value(result)

    # Apply level modifier
    if modifiers.is_core:
        result = _apply_core_level(result)

    # Apply extent modifier
    if not modifiers.include_blob_value:
        result = _strip_blob_values(result)

    return result


def _project_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Project to metadata only (strip values)."""
    result = {}
    for key, value in payload.items():
        if key in METADATA_FIELDS:
            result[key] = value
        elif key == "submodelElements" and isinstance(value, list):
            result[key] = [_project_metadata(elem) for elem in value]
        elif key == "value" and isinstance(value, list):
            # For SubmodelElementCollection/List
            if payload.get("modelType") in (
                "SubmodelElementCollection",
                "SubmodelElementList",
            ):
                result[key] = [_project_metadata(elem) for elem in value]
    return result


def _project_value(payload: dict[str, Any]) -> dict[str, Any]:
    """Project to value only (strip metadata)."""
    result = {}
    for key, value in payload.items():
        if key == "submodelElements" and isinstance(value, list):
            # Recursively process submodel elements
            result[key] = [_project_value(elem) for elem in value]
        elif key == "value" and isinstance(value, list):
            # For SubmodelElementCollection/List - recursive processing
            if payload.get("modelType") in (
                "SubmodelElementCollection",
                "SubmodelElementList",
            ):
                result[key] = [_project_value(elem) for elem in value]
            else:
                # Non-collection value list (e.g., MultiLanguageProperty)
                result[key] = value
        elif key in VALUE_FIELDS:
            result[key] = value
    return result


def _apply_core_level(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply core level (no nested elements)."""
    result = {}
    for key, value in payload.items():
        if key in ("submodelElements", "value", "statements", "annotations"):
            # Don't include nested elements at core level
            continue
        result[key] = value
    return result


def _strip_blob_values(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip blob values (extent=withoutBlobValue)."""
    result = deepcopy(payload)

    if payload.get("modelType") == "Blob":
        result.pop("value", None)

    # Recursively process nested elements
    if "submodelElements" in result and isinstance(result["submodelElements"], list):
        result["submodelElements"] = [
            _strip_blob_values(elem) for elem in result["submodelElements"]
        ]
    if "value" in result and isinstance(result["value"], list):
        if payload.get("modelType") in (
            "SubmodelElementCollection",
            "SubmodelElementList",
        ):
            result["value"] = [_strip_blob_values(elem) for elem in result["value"]]

    return result


def navigate_id_short_path(payload: dict[str, Any], id_short_path: str) -> dict[str, Any] | None:
    """Navigate to nested element by idShortPath.

    The idShortPath uses dots as separators: "Collection.Property"
    For lists, use index: "List[0]"

    Returns None if path not found.
    """
    if not id_short_path:
        return payload

    parts = _parse_id_short_path(id_short_path)
    current: dict[str, Any] | None = payload

    for part in parts:
        if current is None:
            return None
        if isinstance(part, str):
            # Navigate by idShort
            current = _find_element_by_id_short(current, part)
        elif isinstance(part, int):
            # Navigate by index
            current = _get_element_at_index(current, part)

        if current is None:
            return None

    return current


def _parse_id_short_path(path: str) -> list[str | int]:
    """Parse idShortPath into components.

    Examples:
    - "Temperature" -> ["Temperature"]
    - "Nameplate.SerialNumber" -> ["Nameplate", "SerialNumber"]
    - "Measurements[0]" -> ["Measurements", 0]
    """
    parts: list[str | int] = []
    current = ""

    i = 0
    while i < len(path):
        char = path[i]

        if char == ".":
            if current:
                parts.append(current)
                current = ""
        elif char == "[":
            if current:
                parts.append(current)
                current = ""
            # Parse index
            j = i + 1
            while j < len(path) and path[j] != "]":
                j += 1
            index = int(path[i + 1 : j])
            parts.append(index)
            i = j
        else:
            current += char

        i += 1

    if current:
        parts.append(current)

    return parts


def _find_element_by_id_short(container: dict[str, Any], id_short: str) -> dict[str, Any] | None:
    """Find element by idShort in container."""
    # Check submodelElements
    elements = container.get("submodelElements", [])
    if not elements:
        # For SubmodelElementCollection/List
        elements = container.get("value", [])
    if not elements:
        # For Entity statements or AnnotatedRelationshipElement annotations
        elements = container.get("statements", []) or container.get("annotations", [])

    if isinstance(elements, list):
        for elem in elements:
            if isinstance(elem, dict) and elem.get("idShort") == id_short:
                return elem

    return None


def _get_element_at_index(container: dict[str, Any], index: int) -> dict[str, Any] | None:
    """Get element at index in container."""
    elements = container.get("submodelElements", [])
    if not elements:
        elements = container.get("value", [])
    if not elements:
        elements = container.get("statements", []) or container.get("annotations", [])

    if isinstance(elements, list) and 0 <= index < len(elements):
        elem = elements[index]
        return elem if isinstance(elem, dict) else None

    return None


def extract_value(element: dict[str, Any]) -> Any:
    """Extract $value from a SubmodelElement.

    For Property: returns the value
    For MultiLanguageProperty: returns the language string array
    For Range: returns {min, max}
    For collections: returns array of nested $values
    """
    model_type = element.get("modelType")

    if model_type == "Property":
        return element.get("value")

    elif model_type == "MultiLanguageProperty":
        return element.get("value")

    elif model_type == "Range":
        return {
            "min": element.get("min"),
            "max": element.get("max"),
        }

    elif model_type == "Blob":
        return element.get("value")

    elif model_type == "File":
        return element.get("value")

    elif model_type == "ReferenceElement":
        return element.get("value")

    elif model_type in ("SubmodelElementCollection", "SubmodelElementList"):
        nested = element.get("value", [])
        return [extract_value(e) for e in nested] if nested else None

    elif model_type == "Entity":
        return {
            "entityType": element.get("entityType"),
            "globalAssetId": element.get("globalAssetId"),
            "specificAssetIds": element.get("specificAssetIds"),
        }

    else:
        return None


def extract_metadata(element: dict[str, Any]) -> dict[str, Any]:
    """Extract $metadata from a SubmodelElement or Submodel.

    Returns only metadata fields (no values) per IDTA-01002.
    Recursively extracts metadata for nested elements.
    """
    result: dict[str, Any] = {}

    for key, value in element.items():
        if key in METADATA_FIELDS:
            result[key] = value
        elif key == "submodelElements" and isinstance(value, list):
            # For Submodel: recursively extract metadata from elements
            result[key] = [extract_metadata(elem) for elem in value]
        elif key == "value" and isinstance(value, list):
            # For SubmodelElementCollection/List
            model_type = element.get("modelType")
            if model_type in ("SubmodelElementCollection", "SubmodelElementList"):
                result[key] = [extract_metadata(elem) for elem in value]
        # Preserve submodel-level metadata
        elif key in ("id", "administration", "kind"):
            result[key] = value

    return result


def extract_reference(
    element: dict[str, Any],
    submodel_id: str,
    id_short_path: str | None = None,
) -> dict[str, Any]:
    """Extract $reference representation for a SubmodelElement.

    Returns a ModelReference pointing to this element per IDTA-01002.

    Args:
        element: The SubmodelElement dictionary
        submodel_id: The parent Submodel's identifier
        id_short_path: The idShortPath to this element (None for Submodel itself)

    Returns:
        Reference structure with type and keys
    """
    keys: list[dict[str, str]] = [{"type": "Submodel", "value": submodel_id}]

    if id_short_path:
        # Add SubmodelElement key
        model_type = element.get("modelType", "SubmodelElement")
        keys.append({"type": model_type, "value": id_short_path})

    return {
        "type": "ModelReference",
        "keys": keys,
    }


def extract_reference_for_aas(aas: dict[str, Any]) -> dict[str, Any]:
    """Extract $reference representation for an AAS.

    Returns a ModelReference pointing to this AAS per IDTA-01002.
    """
    aas_id = aas.get("id", "")
    return {
        "type": "ModelReference",
        "keys": [{"type": "AssetAdministrationShell", "value": aas_id}],
    }


def extract_reference_for_submodel(submodel: dict[str, Any]) -> dict[str, Any]:
    """Extract $reference representation for a Submodel."""
    submodel_id = submodel.get("id", "")
    return {
        "type": "ModelReference",
        "keys": [{"type": "Submodel", "value": submodel_id}],
    }


def extract_path(element: dict[str, Any], id_short_path: str) -> dict[str, Any]:
    """Extract $path representation for a SubmodelElement.

    Returns the idShortPath representation per IDTA-01002.

    Args:
        element: The SubmodelElement dictionary
        id_short_path: The full idShortPath to this element

    Returns:
        Path structure containing idShortPath
    """
    return {
        "idShortPath": id_short_path,
    }


def collect_id_short_paths(submodel: dict[str, Any]) -> list[str]:
    """Collect all idShortPaths for submodel elements (including hierarchy)."""
    elements = submodel.get("submodelElements", [])
    paths: list[str] = []
    for elem in elements:
        id_short = elem.get("idShort")
        if id_short:
            _collect_paths(elem, id_short, paths)
    return paths


def collect_element_references(submodel: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect references for all submodel elements (including hierarchy)."""
    submodel_id = submodel.get("id", "")
    elements = submodel.get("submodelElements", [])
    references: list[dict[str, Any]] = []
    for elem in elements:
        id_short = elem.get("idShort")
        if id_short:
            _collect_references(elem, id_short, submodel_id, references)
    return references


def _collect_paths(element: dict[str, Any], path: str, out: list[str]) -> None:
    """Recursively collect idShortPaths for nested elements."""
    out.append(path)
    model_type = element.get("modelType")

    if model_type in ("SubmodelElementCollection",):
        for child in element.get("value", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_paths(child, f"{path}.{child_id}", out)
        return

    if model_type in ("Entity",):
        for child in element.get("statements", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_paths(child, f"{path}.{child_id}", out)
        return

    if model_type in ("AnnotatedRelationshipElement",):
        for child in element.get("annotations", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_paths(child, f"{path}.{child_id}", out)
        return

    if model_type == "SubmodelElementList":
        for idx, child in enumerate(element.get("value", []) or []):
            item_path = f"{path}[{idx}]"
            out.append(item_path)
            _collect_list_child_paths(child, item_path, out)


def _collect_list_child_paths(element: dict[str, Any], path: str, out: list[str]) -> None:
    """Collect nested paths for list elements without duplicating the list item path."""
    model_type = element.get("modelType")
    if model_type == "SubmodelElementCollection":
        for child in element.get("value", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_paths(child, f"{path}.{child_id}", out)
    elif model_type == "Entity":
        for child in element.get("statements", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_paths(child, f"{path}.{child_id}", out)
    elif model_type == "AnnotatedRelationshipElement":
        for child in element.get("annotations", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_paths(child, f"{path}.{child_id}", out)
    elif model_type == "SubmodelElementList":
        for idx, child in enumerate(element.get("value", []) or []):
            item_path = f"{path}[{idx}]"
            out.append(item_path)
            _collect_list_child_paths(child, item_path, out)


def _collect_references(
    element: dict[str, Any],
    path: str,
    submodel_id: str,
    out: list[dict[str, Any]],
) -> None:
    """Recursively collect references for nested elements."""
    out.append(extract_reference(element, submodel_id, path))
    model_type = element.get("modelType")

    if model_type == "SubmodelElementCollection":
        for child in element.get("value", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_references(child, f"{path}.{child_id}", submodel_id, out)
        return

    if model_type == "Entity":
        for child in element.get("statements", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_references(child, f"{path}.{child_id}", submodel_id, out)
        return

    if model_type == "AnnotatedRelationshipElement":
        for child in element.get("annotations", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_references(child, f"{path}.{child_id}", submodel_id, out)
        return

    if model_type == "SubmodelElementList":
        for idx, child in enumerate(element.get("value", []) or []):
            item_path = f"{path}[{idx}]"
            out.append(extract_reference(child, submodel_id, item_path))
            _collect_list_child_references(child, item_path, submodel_id, out)


def _collect_list_child_references(
    element: dict[str, Any],
    path: str,
    submodel_id: str,
    out: list[dict[str, Any]],
) -> None:
    """Collect nested references for list elements without duplicating the list item."""
    model_type = element.get("modelType")
    if model_type == "SubmodelElementCollection":
        for child in element.get("value", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_references(child, f"{path}.{child_id}", submodel_id, out)
    elif model_type == "Entity":
        for child in element.get("statements", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_references(child, f"{path}.{child_id}", submodel_id, out)
    elif model_type == "AnnotatedRelationshipElement":
        for child in element.get("annotations", []) or []:
            child_id = child.get("idShort")
            if child_id:
                _collect_references(child, f"{path}.{child_id}", submodel_id, out)
    elif model_type == "SubmodelElementList":
        for idx, child in enumerate(element.get("value", []) or []):
            item_path = f"{path}[{idx}]"
            out.append(extract_reference(child, submodel_id, item_path))
            _collect_list_child_references(child, item_path, submodel_id, out)
