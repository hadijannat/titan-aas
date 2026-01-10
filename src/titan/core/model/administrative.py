"""IDTA-01001 Part 1 v3.1.2: Administrative information and data specifications.

This module defines AdministrativeInformation, HasDataSpecification,
EmbeddedDataSpecification, and the IEC 61360 data specification content.

Note: HasDataSpecification is explicitly NOT implemented in BaSyx Python SDK.
This is a Titan-only feature that provides full IDTA spec compliance.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from titan.core.model import StrictModel
from titan.core.model.descriptions import (
    LangStringDefinitionType,
    LangStringPreferredNameType,
    LangStringShortNameType,
    MultiLanguageDefinitionType,
    MultiLanguagePreferredNameType,
    MultiLanguageShortNameType,
)
from titan.core.model.identifiers import (
    DataTypeIec61360,
    LevelType,
    Reference,
)
from titan.core.model.qualifiers import ValueReferencePair


class AdministrativeInformation(StrictModel):
    """Administrative metadata for an identifiable element.

    Contains version and revision information as well as optional
    creator and template references.
    """

    version: Annotated[str, Field(min_length=1, max_length=4)] | None = Field(
        default=None, description="Version of the element"
    )
    revision: Annotated[str, Field(min_length=1, max_length=4)] | None = Field(
        default=None, description="Revision of the element"
    )
    creator: Reference | None = Field(
        default=None, description="Reference to the creator of the element"
    )
    template_id: Annotated[str, Field(min_length=1, max_length=2000)] | None = Field(
        default=None,
        alias="templateId",
        description="Identifier of the template this element was created from",
    )


class ValueFormatType(StrictModel):
    """Format specification for values."""

    pass  # Reserved for future use per IDTA spec


class LevelTypeSpec(StrictModel):
    """Specification of which level types are applicable."""

    min: bool = Field(default=False, description="Minimum value is applicable")
    max: bool = Field(default=False, description="Maximum value is applicable")
    nom: bool = Field(default=False, description="Nominal value is applicable")
    typ: bool = Field(default=False, description="Typical value is applicable")


class DataSpecificationIec61360(StrictModel):
    """Data specification content following IEC 61360 / ECLASS structure.

    This is the primary data specification type used in industrial applications
    for describing concept descriptions that follow the IEC 61360 standard.
    """

    preferred_name: MultiLanguagePreferredNameType = Field(
        ...,
        alias="preferredName",
        description="Preferred name in multiple languages (required)",
    )
    short_name: MultiLanguageShortNameType | None = Field(
        default=None, alias="shortName", description="Short name in multiple languages"
    )
    unit: Annotated[str, Field(max_length=30)] | None = Field(
        default=None, description="Unit of the value"
    )
    unit_id: Reference | None = Field(
        default=None, alias="unitId", description="Reference to the unit definition"
    )
    source_of_definition: Annotated[str, Field(max_length=255)] | None = Field(
        default=None,
        alias="sourceOfDefinition",
        description="Source of the definition",
    )
    symbol: Annotated[str, Field(max_length=30)] | None = Field(
        default=None, description="Symbol for the concept"
    )
    data_type: DataTypeIec61360 | None = Field(
        default=None, alias="dataType", description="Data type of the value"
    )
    definition: MultiLanguageDefinitionType | None = Field(
        default=None, description="Definition in multiple languages"
    )
    value_format: Annotated[str, Field(max_length=2000)] | None = Field(
        default=None, alias="valueFormat", description="Format specification for values"
    )
    value_list: list[ValueReferencePair] | None = Field(
        default=None,
        alias="valueList",
        description="List of allowed values (for enumerations)",
    )
    value: Annotated[str, Field(max_length=2000)] | None = Field(
        default=None, description="Default or example value"
    )
    level_type: LevelTypeSpec | None = Field(
        default=None,
        alias="levelType",
        description="Specification of applicable level types",
    )


class EmbeddedDataSpecification(StrictModel):
    """An embedded data specification with its content.

    Contains a reference to the data specification template and the
    actual content following that specification (typically IEC 61360).
    """

    data_specification: Reference = Field(
        ...,
        alias="dataSpecification",
        description="Reference to the data specification template",
    )
    data_specification_content: DataSpecificationIec61360 = Field(
        ...,
        alias="dataSpecificationContent",
        description="The actual data specification content",
    )


class HasDataSpecificationMixin(StrictModel):
    """Mixin for elements that can have embedded data specifications.

    This is a Titan-only feature - BaSyx Python SDK explicitly does not
    implement HasDataSpecification. Titan provides full support for
    embedding IEC 61360 data specifications.
    """

    embedded_data_specifications: list[EmbeddedDataSpecification] | None = Field(
        default=None,
        alias="embeddedDataSpecifications",
        description="List of embedded data specifications",
    )
