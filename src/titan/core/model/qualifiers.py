"""IDTA-01001 Part 1 v3.1.2: Qualifiers and Extensions.

This module defines Qualifier, Extension, and related mixins used to
add metadata and constraints to AAS elements.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel
from titan.core.model.identifiers import (
    DataTypeDefXsd,
    IdShort,
    QualifierKind,
    Reference,
    ValueDataType,
)
from titan.core.model.semantic import HasSemanticsMixin


class ValueReferencePair(StrictModel):
    """A value with an associated reference (for enumerations)."""

    value: ValueDataType = Field(..., description="The value")
    value_id: Reference = Field(
        ..., alias="valueId", description="Reference to the value definition"
    )


class Qualifier(HasSemanticsMixin):
    """A qualifier constrains or extends the meaning of an element.

    Qualifiers are used to express additional semantics beyond what
    is provided by the element's semanticId. Examples include:
    - Cardinality constraints
    - Template qualifiers for defining required values
    - Concept qualifiers for additional classification
    """

    kind: QualifierKind | None = Field(
        default=None,
        description="Kind of qualifier (ConceptQualifier, TemplateQualifier, ValueQualifier)",
    )
    type: Annotated[str, Field(min_length=1, max_length=128)] = Field(
        ..., description="Type of the qualifier"
    )
    value_type: DataTypeDefXsd = Field(
        ..., alias="valueType", description="Data type of the qualifier value"
    )
    value: ValueDataType | None = Field(
        default=None, description="The qualifier value"
    )
    value_id: Reference | None = Field(
        default=None,
        alias="valueId",
        description="Reference to the qualifier value definition",
    )


class Extension(HasSemanticsMixin):
    """An extension adds proprietary data to an element.

    Extensions are used to add vendor-specific or application-specific
    data that is not part of the standard AAS metamodel.
    """

    name: Annotated[str, Field(min_length=1, max_length=128)] = Field(
        ..., description="Name of the extension"
    )
    value_type: DataTypeDefXsd | None = Field(
        default=None, alias="valueType", description="Data type of the extension value"
    )
    value: ValueDataType | None = Field(
        default=None, description="The extension value"
    )
    refers_to: list[Reference] | None = Field(
        default=None,
        alias="refersTo",
        description="References to elements this extension refers to",
    )


class HasExtensionsMixin(StrictModel):
    """Mixin for elements that can have extensions."""

    extensions: list[Extension] | None = Field(
        default=None, description="List of extensions"
    )


class HasQualifiersMixin(StrictModel):
    """Mixin for elements that can have qualifiers."""

    qualifiers: list[Qualifier] | None = Field(
        default=None, description="List of qualifiers"
    )
