"""IDTA-01001 Part 1 v3.0.8: Semantic identification.

This module defines the HasSemantics mixin and related types for
semantic identification of AAS elements per IDTA-01001-3-0-1_schemasV3.0.8.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel
from titan.core.model.identifiers import Reference


class HasSemanticsMixin(StrictModel):
    """Mixin for elements that can have semantic identification.

    semanticId identifies the semantics of the element (e.g., a concept
    from a data dictionary like ECLASS or IEC CDD).

    supplementalSemanticIds can provide additional semantic identifiers
    that complement the primary semanticId.
    """

    semantic_id: Reference | None = Field(
        default=None,
        alias="semanticId",
        description="Semantic identifier of the element",
    )
    supplemental_semantic_ids: Annotated[list[Reference], Field(min_length=1)] | None = Field(
        default=None,
        alias="supplementalSemanticIds",
        description="Additional semantic identifiers",
    )
