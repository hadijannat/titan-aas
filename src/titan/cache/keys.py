"""Cache key schema for Titan-AAS.

Key format: {prefix}:{entity_type}:{identifier_b64}:{variant}

Where:
- prefix: "titan" (namespace for multi-tenant Redis)
- entity_type: "aas", "sm" (submodel), "cd" (concept description)
- identifier_b64: Base64URL encoded identifier
- variant: "bytes" (canonical JSON), "etag", etc.
"""

from __future__ import annotations

import base64
from typing import Literal

EntityType = Literal["aas", "sm", "cd", "aas_desc", "sm_desc"]


class CacheKeys:
    """Cache key generator following consistent naming convention."""

    PREFIX = "titan"

    @classmethod
    def aas_bytes(cls, identifier_b64: str) -> str:
        """Key for AAS canonical bytes."""
        return f"{cls.PREFIX}:aas:{identifier_b64}:bytes"

    @classmethod
    def aas_etag(cls, identifier_b64: str) -> str:
        """Key for AAS ETag."""
        return f"{cls.PREFIX}:aas:{identifier_b64}:etag"

    @classmethod
    def submodel_bytes(cls, identifier_b64: str) -> str:
        """Key for Submodel canonical bytes."""
        return f"{cls.PREFIX}:sm:{identifier_b64}:bytes"

    @classmethod
    def submodel_etag(cls, identifier_b64: str) -> str:
        """Key for Submodel ETag."""
        return f"{cls.PREFIX}:sm:{identifier_b64}:etag"

    @classmethod
    def concept_description_bytes(cls, identifier_b64: str) -> str:
        """Key for ConceptDescription canonical bytes."""
        return f"{cls.PREFIX}:cd:{identifier_b64}:bytes"

    @classmethod
    def concept_description_etag(cls, identifier_b64: str) -> str:
        """Key for ConceptDescription ETag."""
        return f"{cls.PREFIX}:cd:{identifier_b64}:etag"

    @classmethod
    def submodel_element_value(cls, submodel_b64: str, id_short_path: str) -> str:
        """Key for SubmodelElement $value cache.

        Used for fast $value reads without full Submodel hydration.
        The idShort path is encoded to avoid delimiter collisions.
        """
        encoded_path = cls._encode_component(id_short_path)
        return f"{cls.PREFIX}:sm:{submodel_b64}:elem:{encoded_path}:value"

    @classmethod
    def _encode_component(cls, value: str) -> str:
        """Encode a key component to avoid delimiter collisions."""
        if not value:
            return ""
        encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
        return encoded.rstrip("=")

    @classmethod
    def parse_key(cls, key: str) -> dict[str, str] | None:
        """Parse a cache key into its components.

        Returns None if the key doesn't match the expected format.
        """
        parts = key.split(":")
        if len(parts) < 4 or parts[0] != cls.PREFIX:
            return None

        return {
            "prefix": parts[0],
            "entity_type": parts[1],
            "identifier_b64": parts[2],
            "variant": parts[3] if len(parts) > 3 else "",
        }

