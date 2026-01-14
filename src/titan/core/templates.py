"""Template instantiation for Submodels (SSP-003/004 profiles).

This module provides functionality to create Submodel instances from
Submodel templates, supporting the IDTA SSP-003 and SSP-004 profiles.

A Submodel template (kind=Template) defines the structure of a Submodel
without actual runtime values. Instantiation creates a new Submodel
(kind=Instance) based on the template, with:
- A new unique identifier
- All structure copied from template
- Optional value overrides
- Kind set to Instance
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InstantiationResult:
    """Result of template instantiation.

    Attributes:
        success: Whether instantiation succeeded
        submodel_doc: The instantiated submodel document (if success)
        error: Error message (if not success)
    """

    success: bool
    submodel_doc: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class InstantiationRequest:
    """Request to instantiate a Submodel from a template.

    Attributes:
        new_id: The identifier for the new instance
        id_short: Optional idShort override for the instance
        value_overrides: Optional dict mapping idShortPath to new values
        copy_semantic_id: Whether to copy semanticId from template (default True)
    """

    new_id: str
    id_short: str | None = None
    value_overrides: dict[str, Any] = field(default_factory=dict)
    copy_semantic_id: bool = True


class TemplateInstantiator:
    """Instantiates Submodel instances from templates.

    This implements the core logic for SSP-003/004 template profiles,
    allowing creation of Submodel instances from template definitions.
    """

    def instantiate(
        self, template_doc: dict[str, Any], request: InstantiationRequest
    ) -> InstantiationResult:
        """Create a Submodel instance from a template.

        Args:
            template_doc: The template Submodel document (kind=Template)
            request: Instantiation parameters

        Returns:
            InstantiationResult with the new instance or error
        """
        # Validate template
        if template_doc.get("kind") != "Template":
            return InstantiationResult(
                success=False,
                error="Source Submodel is not a template (kind must be 'Template')",
            )

        # Deep copy the template
        instance_doc = copy.deepcopy(template_doc)

        # Set instance properties
        instance_doc["id"] = request.new_id
        instance_doc["kind"] = "Instance"

        # Override idShort if provided
        if request.id_short:
            instance_doc["idShort"] = request.id_short

        # Remove or keep semanticId based on request
        if not request.copy_semantic_id and "semanticId" in instance_doc:
            del instance_doc["semanticId"]

        # Apply value overrides
        if request.value_overrides:
            self._apply_value_overrides(instance_doc, request.value_overrides)

        # Clear template-specific metadata if present
        if "administration" in instance_doc:
            admin = instance_doc["administration"]
            # Keep version but clear template-specific fields
            if admin:
                admin.pop("templateId", None)

        return InstantiationResult(success=True, submodel_doc=instance_doc)

    def _apply_value_overrides(self, doc: dict[str, Any], overrides: dict[str, Any]) -> None:
        """Apply value overrides to submodel elements.

        Args:
            doc: The submodel document to modify
            overrides: Dict mapping idShortPath to new values
        """
        elements = doc.get("submodelElements", [])
        if not elements:
            return

        for path, value in overrides.items():
            self._set_value_at_path(elements, path, value)

    def _set_value_at_path(self, elements: list[dict[str, Any]], path: str, value: Any) -> bool:
        """Set value at a specific idShortPath.

        Supports dot notation for nested elements (e.g., "Collection.Property")
        and bracket notation for list indices (e.g., "List[0]").

        Args:
            elements: List of submodel elements
            path: The idShortPath to the element
            value: The value to set

        Returns:
            True if value was set, False if path not found
        """
        parts = self._parse_path(path)
        if not parts:
            return False

        current = elements
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            name, index = part

            # Find element by idShort
            found = None
            for elem in current:
                if elem.get("idShort") == name:
                    found = elem
                    break

            if found is None:
                return False

            # Handle list index access
            if index is not None:
                if found.get("modelType") == "SubmodelElementList":
                    list_value = found.get("value", [])
                    if 0 <= index < len(list_value):
                        if is_last:
                            list_value[index]["value"] = value
                            return True
                        else:
                            # Navigate into nested element
                            nested = list_value[index]
                            if "value" in nested and isinstance(nested["value"], list):
                                current = nested["value"]
                            else:
                                return False
                    else:
                        return False
                else:
                    return False
            elif is_last:
                # Set the value
                found["value"] = value
                return True
            else:
                # Navigate deeper
                if found.get("modelType") == "SubmodelElementCollection":
                    current = found.get("value", [])
                elif found.get("modelType") == "SubmodelElementList":
                    current = found.get("value", [])
                else:
                    return False

        return False

    def _parse_path(self, path: str) -> list[tuple[str, int | None]]:
        """Parse idShortPath into components.

        Args:
            path: The idShortPath (e.g., "Collection.Property" or "List[0]")

        Returns:
            List of (name, index) tuples where index is None for non-list access
        """
        if not path:
            return []

        result: list[tuple[str, int | None]] = []
        parts = path.replace("[", ".[").split(".")

        current_name: str | None = None
        for part in parts:
            if not part:
                continue

            if part.startswith("[") and part.endswith("]"):
                # List index
                try:
                    index = int(part[1:-1])
                    if current_name:
                        result.append((current_name, index))
                        current_name = None
                except ValueError:
                    return []
            else:
                # Element name
                if current_name:
                    result.append((current_name, None))
                current_name = part

        if current_name:
            result.append((current_name, None))

        return result


# Module-level instance for convenience
_instantiator = TemplateInstantiator()


def instantiate_template(
    template_doc: dict[str, Any], request: InstantiationRequest
) -> InstantiationResult:
    """Create a Submodel instance from a template.

    Convenience function that uses the module-level instantiator.

    Args:
        template_doc: The template Submodel document (kind=Template)
        request: Instantiation parameters

    Returns:
        InstantiationResult with the new instance or error
    """
    return _instantiator.instantiate(template_doc, request)
