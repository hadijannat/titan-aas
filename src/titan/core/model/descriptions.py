"""IDTA-01001 Part 1 v3.0.8: Multi-language string types.

This module defines the language string types used for internationalized
text content in the AAS metamodel per IDTA-01001-3-0-1_schemasV3.0.8.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel

# BCP-47 language tag pattern per IDTA-01001-3-0-1 v3.0.8 JSON schema.
# Supports: language codes (2-3 chars), extlang, script, region, variants,
# extensions, privateuse, and grandfathered tags.
BCP47_PATTERN = (
    r"^(([a-zA-Z]{2,3}(-[a-zA-Z]{3}(-[a-zA-Z]{3}){0,2})?|[a-zA-Z]{4}|[a-zA-Z]{5,8})"
    r"(-[a-zA-Z]{4})?(-([a-zA-Z]{2}|[0-9]{3}))?"
    r"(-(([a-zA-Z0-9]){5,8}|[0-9]([a-zA-Z0-9]){3}))*"
    r"(-[0-9A-WY-Za-wy-z](-([a-zA-Z0-9]){2,8})+)*"
    r"(-[xX](-([a-zA-Z0-9]){1,8})+)?|[xX](-([a-zA-Z0-9]){1,8})+|"
    r"((en-GB-oed|i-ami|i-bnn|i-default|i-enochian|i-hak|i-klingon|i-lux|"
    r"i-mingo|i-navajo|i-pwn|i-tao|i-tay|i-tsu|sgn-BE-FR|sgn-BE-NL|sgn-CH-DE)|"
    r"(art-lojban|cel-gaulish|no-bok|no-nyn|zh-guoyu|zh-hakka|zh-min|zh-min-nan|zh-xiang)))$"
)


class LangStringTextType(StrictModel):
    """A single language string with text content (max 1023 chars)."""

    language: Annotated[str, Field(pattern=BCP47_PATTERN)]
    text: Annotated[str, Field(min_length=1, max_length=1023)]


class LangStringNameType(StrictModel):
    """A single language string with name content (max 128 chars)."""

    language: Annotated[str, Field(pattern=BCP47_PATTERN)]
    text: Annotated[str, Field(min_length=1, max_length=128)]


class LangStringDefinitionType(StrictModel):
    """A single language string with definition content (max 1023 chars)."""

    language: Annotated[str, Field(pattern=BCP47_PATTERN)]
    text: Annotated[str, Field(min_length=1, max_length=1023)]


class LangStringPreferredNameType(StrictModel):
    """A single language string for preferred name (max 255 chars)."""

    language: Annotated[str, Field(pattern=BCP47_PATTERN)]
    text: Annotated[str, Field(min_length=1, max_length=255)]


class LangStringShortNameType(StrictModel):
    """A single language string for short name (max 18 chars)."""

    language: Annotated[str, Field(pattern=BCP47_PATTERN)]
    text: Annotated[str, Field(min_length=1, max_length=18)]


# Type aliases for collections of language strings
MultiLanguageTextType = Annotated[list[LangStringTextType], Field(min_length=1)]
MultiLanguageNameType = Annotated[list[LangStringNameType], Field(min_length=1)]
MultiLanguageDefinitionType = Annotated[list[LangStringDefinitionType], Field(min_length=1)]
MultiLanguagePreferredNameType = Annotated[list[LangStringPreferredNameType], Field(min_length=1)]
MultiLanguageShortNameType = Annotated[list[LangStringShortNameType], Field(min_length=1)]
