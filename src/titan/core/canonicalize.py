from __future__ import annotations

from typing import Any

import orjson
from pydantic import BaseModel


ORJSON_OPTIONS = orjson.OPT_NON_STR_KEYS | orjson.OPT_UTC_Z


def canonical_bytes(data: Any) -> bytes:
    """Return canonical JSON bytes for already-validated data."""
    return orjson.dumps(data, option=ORJSON_OPTIONS)


def canonical_bytes_from_model(model: BaseModel) -> bytes:
    """Validate with Pydantic then serialize to canonical JSON bytes."""
    payload = model.model_dump(by_alias=True, exclude_none=True)
    return canonical_bytes(payload)
