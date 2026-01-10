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
METADATA_FIELDS = frozenset({
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
})

# Value fields that should be included in $value projection
VALUE_FIELDS = frozenset({
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
})


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


def navigate_id_short_path(
    payload: dict[str, Any], id_short_path: str
) -> dict[str, Any] | None:
    """Navigate to nested element by idShortPath.

    The idShortPath uses dots as separators: "Collection.Property"
    For lists, use index: "List[0]"

    Returns None if path not found.
    """
    if not id_short_path:
        return payload

    parts = _parse_id_short_path(id_short_path)
    current = payload

    for part in parts:
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


def _find_element_by_id_short(
    container: dict[str, Any], id_short: str
) -> dict[str, Any] | None:
    """Find element by idShort in container."""
    # Check submodelElements
    elements = container.get("submodelElements", [])
    if not elements:
        # For SubmodelElementCollection/List
        elements = container.get("value", [])

    if isinstance(elements, list):
        for elem in elements:
            if isinstance(elem, dict) and elem.get("idShort") == id_short:
                return elem

    return None


def _get_element_at_index(
    container: dict[str, Any], index: int
) -> dict[str, Any] | None:
    """Get element at index in container."""
    elements = container.get("submodelElements", [])
    if not elements:
        elements = container.get("value", [])

    if isinstance(elements, list) and 0 <= index < len(elements):
        return elements[index]

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
