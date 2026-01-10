"""SubmodelElement CRUD operations for Titan-AAS.

Provides functions for inserting, replacing, patching, and deleting
SubmodelElements within a Submodel document.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from titan.core.projection import _parse_id_short_path


class ElementNotFoundError(Exception):
    """Raised when a SubmodelElement is not found at the given path."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"SubmodelElement not found at path: {path}")


class ElementExistsError(Exception):
    """Raised when a SubmodelElement already exists at the given path."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"SubmodelElement already exists at path: {path}")


class InvalidPathError(Exception):
    """Raised when the path is invalid or parent container not found."""

    def __init__(self, path: str, reason: str = "") -> None:
        self.path = path
        message = f"Invalid path: {path}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


def insert_element(
    doc: dict[str, Any],
    path: str | None,
    element: dict[str, Any],
) -> dict[str, Any]:
    """Insert a new SubmodelElement into a Submodel.

    Args:
        doc: The Submodel document
        path: The idShortPath where to insert. None or empty = root level.
              For nested insertion, path should be the parent container path.
        element: The SubmodelElement to insert

    Returns:
        Modified Submodel document

    Raises:
        ElementExistsError: If element with same idShort already exists at path
        InvalidPathError: If parent container doesn't exist
    """
    result = deepcopy(doc)
    id_short = element.get("idShort")

    if not path:
        # Insert at root level
        if not id_short:
            raise ValueError("Element must have an idShort")
        elements = result.setdefault("submodelElements", [])
        for elem in elements:
            if elem.get("idShort") == id_short:
                raise ElementExistsError(id_short)
        elements.append(element)
        return result

    # Navigate to parent container
    parts = _parse_id_short_path(path)
    container = _navigate_to_container(result, parts)

    if container is None:
        raise InvalidPathError(path, "parent container not found")

    # Get the elements list from container
    model_type = container.get("modelType")
    if model_type == "SubmodelElementCollection":
        if not id_short:
            raise ValueError("Element must have an idShort")
        elements = container.setdefault("value", [])
    elif model_type == "SubmodelElementList":
        elements = container.setdefault("value", [])
    else:
        raise InvalidPathError(path, "target is not a container")

    # Check if element already exists (collections enforce idShort uniqueness)
    if model_type == "SubmodelElementCollection":
        for elem in elements:
            if elem.get("idShort") == id_short:
                raise ElementExistsError(f"{path}.{id_short}")

    elements.append(element)
    return result


def replace_element(
    doc: dict[str, Any],
    path: str,
    element: dict[str, Any],
) -> dict[str, Any]:
    """Replace an existing SubmodelElement.

    Args:
        doc: The Submodel document
        path: The idShortPath to the element to replace
        element: The new SubmodelElement

    Returns:
        Modified Submodel document

    Raises:
        ElementNotFoundError: If element doesn't exist at path
    """
    result = deepcopy(doc)

    parts = _parse_id_short_path(path)
    if not parts:
        raise InvalidPathError(path, "empty path")

    # Navigate to parent and find element
    if len(parts) == 1:
        # Top-level element
        container = result
        elements = container.get("submodelElements", [])
    else:
        # Nested element - navigate to parent
        parent_parts = parts[:-1]
        container = _navigate_to_container(result, parent_parts)
        if container is None:
            raise ElementNotFoundError(path)

        model_type = container.get("modelType")
        if model_type in ("SubmodelElementCollection", "SubmodelElementList"):
            elements = container.get("value", [])
        else:
            elements = container.get("submodelElements", [])

    target = parts[-1]

    # Find and replace
    for i, elem in enumerate(elements):
        if isinstance(target, str):
            if elem.get("idShort") == target:
                elements[i] = element
                return result
        elif isinstance(target, int):
            if i == target:
                elements[i] = element
                return result

    raise ElementNotFoundError(path)


def patch_element(
    doc: dict[str, Any],
    path: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Partially update a SubmodelElement.

    Merges the updates into the existing element.

    Args:
        doc: The Submodel document
        path: The idShortPath to the element to patch
        updates: Dictionary of fields to update

    Returns:
        Modified Submodel document

    Raises:
        ElementNotFoundError: If element doesn't exist at path
    """
    result = deepcopy(doc)

    parts = _parse_id_short_path(path)
    if not parts:
        raise InvalidPathError(path, "empty path")

    # Navigate to parent and find element
    if len(parts) == 1:
        container = result
        elements = container.get("submodelElements", [])
    else:
        parent_parts = parts[:-1]
        container = _navigate_to_container(result, parent_parts)
        if container is None:
            raise ElementNotFoundError(path)

        model_type = container.get("modelType")
        if model_type in ("SubmodelElementCollection", "SubmodelElementList"):
            elements = container.get("value", [])
        else:
            elements = container.get("submodelElements", [])

    target = parts[-1]

    # Find and patch
    for i, elem in enumerate(elements):
        if isinstance(target, str) and elem.get("idShort") == target:
            for key, value in updates.items():
                elem[key] = value
            return result
        if isinstance(target, int) and i == target:
            for key, value in updates.items():
                elem[key] = value
            return result

    raise ElementNotFoundError(path)


def update_element_value(
    doc: dict[str, Any],
    path: str,
    value: Any,
) -> dict[str, Any]:
    """Update only the value of a SubmodelElement.

    Args:
        doc: The Submodel document
        path: The idShortPath to the element
        value: The new value

    Returns:
        Modified Submodel document

    Raises:
        ElementNotFoundError: If element doesn't exist at path
    """
    return patch_element(doc, path, {"value": value})


def delete_element(
    doc: dict[str, Any],
    path: str,
) -> dict[str, Any]:
    """Delete a SubmodelElement from a Submodel.

    Args:
        doc: The Submodel document
        path: The idShortPath to the element to delete

    Returns:
        Modified Submodel document

    Raises:
        ElementNotFoundError: If element doesn't exist at path
    """
    result = deepcopy(doc)

    parts = _parse_id_short_path(path)
    if not parts:
        raise InvalidPathError(path, "empty path")

    # Navigate to parent
    if len(parts) == 1:
        container = result
        elements = container.get("submodelElements", [])
        elements_key = "submodelElements"
    else:
        parent_parts = parts[:-1]
        container = _navigate_to_container(result, parent_parts)
        if container is None:
            raise ElementNotFoundError(path)

        model_type = container.get("modelType")
        if model_type in ("SubmodelElementCollection", "SubmodelElementList"):
            elements = container.get("value", [])
            elements_key = "value"
        else:
            elements = container.get("submodelElements", [])
            elements_key = "submodelElements"

    target = parts[-1]

    # Find and remove
    for i, elem in enumerate(elements):
        if isinstance(target, str):
            if elem.get("idShort") == target:
                del elements[i]
                return result
        elif isinstance(target, int):
            if i == target:
                del elements[i]
                return result

    raise ElementNotFoundError(path)


def _navigate_to_container(
    doc: dict[str, Any],
    parts: list[str | int],
) -> dict[str, Any] | None:
    """Navigate to a container element following the path parts.

    Returns the container element, or None if not found.
    """
    current: dict[str, Any] | None = doc

    for part in parts:
        if current is None:
            return None

        # Get elements list
        elements = current.get("submodelElements")
        if not elements:
            elements = current.get("value", [])

        if not isinstance(elements, list):
            return None

        found = False
        for i, elem in enumerate(elements):
            if not isinstance(elem, dict):
                continue

            if isinstance(part, str):
                if elem.get("idShort") == part:
                    current = elem
                    found = True
                    break
            elif isinstance(part, int):
                if i == part:
                    current = elem
                    found = True
                    break

        if not found:
            return None

    return current
