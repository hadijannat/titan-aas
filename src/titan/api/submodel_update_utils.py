"""Utilities for partial Submodel updates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from titan.api.errors import BadRequestError, NotFoundError
from titan.core.element_operations import (
    ElementNotFoundError,
    InvalidPathError,
    update_element_value,
)

SUBMODEL_METADATA_FIELDS = frozenset(
    {
        "idShort",
        "description",
        "displayName",
        "category",
        "administration",
        "kind",
        "semanticId",
        "supplementalSemanticIds",
        "qualifiers",
        "extensions",
        "embeddedDataSpecifications",
    }
)


def apply_submodel_metadata_patch(doc: dict[str, Any], updates: Any) -> dict[str, Any]:
    """Apply metadata-only updates to a Submodel document."""
    if not isinstance(updates, dict):
        raise BadRequestError("Metadata payload must be an object")

    unknown = set(updates) - SUBMODEL_METADATA_FIELDS
    if unknown:
        raise BadRequestError(f"Unsupported metadata fields: {', '.join(sorted(unknown))}")

    updated = deepcopy(doc)
    for key, value in updates.items():
        if value is None:
            updated.pop(key, None)
        else:
            updated[key] = value

    return updated


def apply_submodel_value_patch(doc: dict[str, Any], values: Any) -> dict[str, Any]:
    """Apply value-only updates using idShortPath keys."""
    if not isinstance(values, dict):
        raise BadRequestError("Value payload must be an object with idShortPath keys")

    updated = deepcopy(doc)
    for path, value in values.items():
        if not isinstance(path, str):
            raise BadRequestError("Value payload keys must be strings")
        try:
            updated = update_element_value(updated, path, value)
        except ElementNotFoundError:
            raise NotFoundError("SubmodelElement", path)
        except InvalidPathError as e:
            raise BadRequestError(str(e)) from e

    return updated
