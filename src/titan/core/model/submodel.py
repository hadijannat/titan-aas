"""IDTA-01001 Part 1 v3.1.2: Submodel.

This module defines the Submodel type, which is a container for
SubmodelElements representing a specific aspect of an asset.
"""

from __future__ import annotations

from pydantic import Field

from titan.core.model.administrative import (
    AdministrativeInformation,
    HasDataSpecificationMixin,
)
from titan.core.model.descriptions import LangStringTextType
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

    model_type: str | None = Field(
        default=None, alias="modelType", description="Model type identifier"
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
    display_name: list[LangStringTextType] | None = Field(
        default=None,
        alias="displayName",
        description="Display name in multiple languages",
    )
    category: str | None = Field(default=None, description="Category of the Submodel")
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
