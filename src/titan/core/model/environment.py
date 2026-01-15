"""IDTA-01001 Part 1 v3.0.8: Environment container for AASX serialization.

This module defines the Environment class that serves as the top-level
container for serializing/deserializing complete AAS ecosystems (AASX packages)
per IDTA-01001-3-0-1_schemasV3.0.8.

Note: This class uses string annotations to avoid circular imports.
The model is rebuilt in __init__.py after all dependencies are loaded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from pydantic import Field

from titan.core.model import StrictModel

if TYPE_CHECKING:
    from titan.core.model.aas import AssetAdministrationShell
    from titan.core.model.concept_description import ConceptDescription
    from titan.core.model.submodel import Submodel


class Environment(StrictModel):
    """Container for a complete AAS ecosystem.

    The Environment is the top-level container used for AASX package
    serialization. It contains all AAS, Submodels, and ConceptDescriptions
    that make up a complete digital twin ecosystem.

    Per IDTA-01001-3-0-1 v3.0.8 JSON Schema, this is the root object
    for AAS JSON serialization.
    """

    asset_administration_shells: (
        Annotated[list[AssetAdministrationShell], Field(min_length=1)] | None
    ) = Field(
        default=None,
        alias="assetAdministrationShells",
        description="List of Asset Administration Shells in this environment",
    )
    submodels: Annotated[list[Submodel], Field(min_length=1)] | None = Field(
        default=None,
        description="List of Submodels in this environment",
    )
    concept_descriptions: Annotated[list[ConceptDescription], Field(min_length=1)] | None = (
        Field(
            default=None,
            alias="conceptDescriptions",
            description="List of Concept Descriptions in this environment",
        )
    )
