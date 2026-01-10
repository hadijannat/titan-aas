"""Cursor-based pagination for Titan-AAS.

Implements IDTA-compliant pagination with:
- Opaque cursor tokens (base64-encoded)
- Configurable page size (limit)
- Stable ordering by creation time

The cursor encodes the last seen item's timestamp and ID
for consistent pagination even with concurrent updates.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


@dataclass
class CursorData:
    """Internal cursor data structure."""

    created_at: str  # ISO format timestamp
    id: str  # UUID of last item


def encode_cursor(created_at: datetime, id: str) -> str:
    """Encode pagination cursor.

    The cursor is an opaque base64-encoded JSON containing:
    - created_at: ISO timestamp of last item
    - id: UUID of last item

    This allows stable pagination even with concurrent inserts.
    """
    data = {
        "created_at": created_at.isoformat(),
        "id": id,
    }
    json_bytes = json.dumps(data).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> CursorData | None:
    """Decode pagination cursor.

    Returns None if cursor is invalid.
    """
    try:
        # Restore padding
        padded = cursor + "=" * ((4 - len(cursor) % 4) % 4)
        json_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(json_bytes)
        return CursorData(
            created_at=data["created_at"],
            id=data["id"],
        )
    except Exception:
        return None


class PaginatedResult(BaseModel, Generic[T]):
    """Paginated result following IDTA conventions."""

    result: list[T]
    paging_metadata: PagingMetadata


class PagingMetadata(BaseModel):
    """Pagination metadata."""

    model_config = {"extra": "forbid"}

    cursor: str | None = None


# Query parameter types
LimitParam = Annotated[
    int,
    Query(
        ge=1,
        le=1000,
        description="Maximum number of items to return (1-1000)",
    ),
]

CursorParam = Annotated[
    str | None,
    Query(
        description="Opaque cursor for pagination continuation",
    ),
]


# Default limit
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
