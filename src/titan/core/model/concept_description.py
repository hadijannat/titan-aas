"""IDTA-01001 Part 1 v3.0.8: Concept Descriptions.

This module defines ConceptDescription - a standardized way to describe
the semantics of elements using IEC 61360 data specifications
per IDTA-01001-3-0-1_schemasV3.0.8.

ConceptDescriptions are typically used to reference properties from
standardized data dictionaries like ECLASS or IEC CDD.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from titan.core.model.administrative import (
    AdministrativeInformation,
    HasDataSpecificationMixin,
)
from titan.core.model.descriptions import LangStringNameType, LangStringTextType
from titan.core.model.identifiers import Identifier, IdShort, Reference
from titan.core.model.qualifiers import HasExtensionsMixin


class ConceptDescription(HasExtensionsMixin, HasDataSpecificationMixin):
    """A ConceptDescription defines the semantics of elements.

    ConceptDescriptions provide standardized property definitions from
    data dictionaries like ECLASS or IEC CDD. They are typically
    referenced via semanticId from SubmodelElements.

    Key features:
    - Globally unique identifier
    - Optional isCaseOf references to external concept definitions
    - Support for IEC 61360 data specifications via embeddedDataSpecifications
    - Multi-language descriptions and display names
    """

    model_type: Literal["ConceptDescription"] = Field(
        default="ConceptDescription",
        alias="modelType",
        description="Model type identifier",
    )
    id: Identifier = Field(..., description="Globally unique identifier of the ConceptDescription")
    id_short: IdShort | None = Field(
        default=None,
        alias="idShort",
        description="Short identifier (unique within context)",
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
        default=None, description="Category of the ConceptDescription"
    )
    administration: AdministrativeInformation | None = Field(
        default=None, description="Administrative information (version, revision)"
    )
    is_case_of: Annotated[list[Reference], Field(min_length=1)] | None = Field(
        default=None,
        alias="isCaseOf",
        description="References to external concept definitions this is a case of",
    )
