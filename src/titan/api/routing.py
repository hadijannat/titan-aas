"""Fast/slow path routing for Titan-AAS.

IDTA modifiers and query parameters create a performance cliff.
This module provides explicit routing to protect the fast path:

- Fast Path (default): No modifiers, stream bytes directly
- Slow Path: Modifiers present, hydrate model and apply projections

Fast path target: <10ms p50 for cached reads
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from fastapi import Query, Request


class PathType(str, Enum):
    """Type of request path based on modifiers."""

    FAST = "fast"
    SLOW = "slow"


# IDTA modifiers that trigger slow path
SLOW_PATH_MODIFIERS = frozenset({
    "level",
    "extent",
    "content",
})

# Special path suffixes that trigger slow path
SLOW_PATH_SUFFIXES = frozenset({
    "/$value",
    "/$metadata",
    "/$reference",
    "/$path",
})


def detect_path_type(request: Request) -> PathType:
    """Detect if request should use fast or slow path.

    Fast path conditions (all must be true):
    - No IDTA modifiers in query params (level, extent, content)
    - No special suffixes ($value, $metadata, $reference, $path)

    Slow path triggers:
    - Any modifier query parameter present
    - Path ends with special suffix
    """
    # Check query parameters
    for param in SLOW_PATH_MODIFIERS:
        if request.query_params.get(param) is not None:
            return PathType.SLOW

    # Check path suffixes
    path = request.url.path
    for suffix in SLOW_PATH_SUFFIXES:
        if path.endswith(suffix):
            return PathType.SLOW

    return PathType.FAST


def is_fast_path(request: Request) -> bool:
    """Check if request qualifies for fast path."""
    return detect_path_type(request) == PathType.FAST


def is_slow_path(request: Request) -> bool:
    """Check if request requires slow path."""
    return detect_path_type(request) == PathType.SLOW


# Query parameter types for IDTA modifiers
LevelParam = Annotated[
    str | None,
    Query(
        alias="level",
        description="Depth level: 'deep' (default) or 'core'",
        pattern="^(deep|core)$",
    ),
]

ExtentParam = Annotated[
    str | None,
    Query(
        alias="extent",
        description="Blob extent: 'withBlobValue' (default) or 'withoutBlobValue'",
        pattern="^(withBlobValue|withoutBlobValue)$",
    ),
]

ContentParam = Annotated[
    str | None,
    Query(
        alias="content",
        description="Content modifier: 'normal', 'metadata', 'value', 'reference', 'path'",
        pattern="^(normal|metadata|value|reference|path)$",
    ),
]
