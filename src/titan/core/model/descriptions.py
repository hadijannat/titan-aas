"""IDTA-01001 Part 1 v3.1.2: Multi-language string types.

This module defines the language string types used for internationalized
text content in the AAS metamodel.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel


class LangStringTextType(StrictModel):
    """A single language string with text content (max 1023 chars)."""

    language: Annotated[str, Field(min_length=2, max_length=5, pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
    text: Annotated[str, Field(max_length=1023)]


class LangStringNameType(StrictModel):
    """A single language string with name content (max 128 chars)."""

    language: Annotated[str, Field(min_length=2, max_length=5, pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
    text: Annotated[str, Field(max_length=128)]


class LangStringDefinitionType(StrictModel):
    """A single language string with definition content (max 1023 chars)."""

    language: Annotated[str, Field(min_length=2, max_length=5, pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
    text: Annotated[str, Field(max_length=1023)]


class LangStringPreferredNameType(StrictModel):
    """A single language string for preferred name (max 255 chars)."""

    language: Annotated[str, Field(min_length=2, max_length=5, pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
    text: Annotated[str, Field(max_length=255)]


class LangStringShortNameType(StrictModel):
    """A single language string for short name (max 18 chars)."""

    language: Annotated[str, Field(min_length=2, max_length=5, pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
    text: Annotated[str, Field(max_length=18)]


# Type aliases for collections of language strings
MultiLanguageTextType = Annotated[list[LangStringTextType], Field(min_length=1)]
MultiLanguageNameType = Annotated[list[LangStringNameType], Field(min_length=1)]
MultiLanguageDefinitionType = Annotated[list[LangStringDefinitionType], Field(min_length=1)]
MultiLanguagePreferredNameType = Annotated[list[LangStringPreferredNameType], Field(min_length=1)]
MultiLanguageShortNameType = Annotated[list[LangStringShortNameType], Field(min_length=1)]
