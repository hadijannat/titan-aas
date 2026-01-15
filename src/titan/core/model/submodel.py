"""IDTA-01001 Part 1 v3.0.8: Submodel.

This module defines the Submodel type, which is a container for
SubmodelElements representing a specific aspect of an asset
per IDTA-01001-3-0-1_schemasV3.0.8.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from titan.core.model.administrative import (
    AdministrativeInformation,
    HasDataSpecificationMixin,
)
from titan.core.model.descriptions import LangStringNameType, LangStringTextType
from titan.core.model.identifiers import Identifier, IdShort, ModellingKind
from titan.core.model.qualifiers import HasExtensionsMixin, HasQualifiersMixin
from titan.core.model.semantic import HasSemanticsMixin
from titan.core.model.submodel_elements import SubmodelElementUnion


class Submodel(
    HasSemanticsMixin,
    HasQualifiersMixin,
    HasExtensionsMixin,
    HasDataSpecificationMixin,
):
    """A Submodel represents a specific aspect or view of an asset.

    Submodels contain SubmodelElements that describe properties,
    operations, events, and relationships related to a particular
    domain (e.g., technical data, documentation, operational data).

    Each Submodel has a globally unique identifier and can be
    associated with multiple Asset Administration Shells.
    """

    model_type: Literal["Submodel"] = Field(
        default="Submodel", alias="modelType", description="Model type identifier"
    )
    id: Identifier = Field(..., description="Globally unique identifier of the Submodel")
    id_short: IdShort | None = Field(
        default=None,
        alias="idShort",
        description="Short identifier (unique within containing AAS)",
    )
    description: list[LangStringTextType] | None = Field(
        default=None, description="Description in multiple languages"
    )
    display_name: list[LangStringNameType] | None = Field(
        default=None,
        alias="displayName",
        description="Display name in multiple languages",
    )
    category: Annotated[str, Field(min_length=1, max_length=128)] | None = Field(
        default=None, description="Category of the Submodel"
    )
    administration: AdministrativeInformation | None = Field(
        default=None, description="Administrative information"
    )
    kind: ModellingKind | None = Field(
        default=None, description="Modelling kind (Template or Instance)"
    )
    submodel_elements: list[SubmodelElementUnion] | None = Field(
        default=None,
        alias="submodelElements",
        description="The SubmodelElements contained in this Submodel",
    )

    @model_validator(mode="after")
    def _validate_unique_id_shorts(self) -> Submodel:
        """Ensure idShort uniqueness at the Submodel root level."""
        if not self.submodel_elements:
            return self
        seen: set[str] = set()
        for element in self.submodel_elements:
            id_short = getattr(element, "id_short", None)
            if not id_short:
                continue
            if id_short in seen:
                raise ValueError(f"Duplicate idShort in submodelElements: {id_short}")
            seen.add(id_short)
        return self
