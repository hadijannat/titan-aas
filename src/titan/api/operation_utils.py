"""Helpers for Operation invocation payload conversions."""

from __future__ import annotations

from typing import Any

from titan.api.errors import BadRequestError


def coerce_value_only_arguments(value: Any, field_name: str) -> list[dict[str, Any]] | None:
    """Coerce value-only argument payloads to OperationArgument dicts."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [{"idShort": key, "value": val} for key, val in value.items()]
    raise BadRequestError(f"{field_name} must be an object or array")


def arguments_to_value_map(args: Any) -> dict[str, Any] | None:
    """Convert OperationArgument dicts to a value-only map."""
    if not args:
        return None
    if isinstance(args, dict):
        return args
    if not isinstance(args, list):
        return None
    result: dict[str, Any] = {}
    for arg in args:
        if not isinstance(arg, dict):
            continue
        id_short = arg.get("idShort")
        if id_short:
            result[id_short] = arg.get("value")
    return result
