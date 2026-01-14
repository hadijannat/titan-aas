"""Tests for cache key generation."""

import base64

from titan.cache.keys import CacheKeys


class TestCacheKeys:
    """Test cache key generation."""

    def test_aas_bytes_key(self) -> None:
        """AAS bytes key has correct format."""
        key = CacheKeys.aas_bytes("abc123")
        assert key == "titan:aas:abc123:bytes"

    def test_aas_etag_key(self) -> None:
        """AAS etag key has correct format."""
        key = CacheKeys.aas_etag("abc123")
        assert key == "titan:aas:abc123:etag"

    def test_submodel_bytes_key(self) -> None:
        """Submodel bytes key has correct format."""
        key = CacheKeys.submodel_bytes("xyz789")
        assert key == "titan:sm:xyz789:bytes"

    def test_submodel_etag_key(self) -> None:
        """Submodel etag key has correct format."""
        key = CacheKeys.submodel_etag("xyz789")
        assert key == "titan:sm:xyz789:etag"

    def test_concept_description_bytes_key(self) -> None:
        """ConceptDescription bytes key has correct format."""
        key = CacheKeys.concept_description_bytes("cd123")
        assert key == "titan:cd:cd123:bytes"

    def test_element_value_key(self) -> None:
        """SubmodelElement value key has correct format."""
        key = CacheKeys.submodel_element_value("sm123", "Temperature")
        encoded = base64.urlsafe_b64encode(b"Temperature").decode("ascii").rstrip("=")
        assert key == f"titan:sm:sm123:elem:{encoded}:value"

    def test_element_value_key_with_path(self) -> None:
        """SubmodelElement value key works with nested paths."""
        key = CacheKeys.submodel_element_value("sm123", "Nameplate.SerialNumber")
        encoded = base64.urlsafe_b64encode(b"Nameplate.SerialNumber").decode("ascii").rstrip("=")
        assert key == f"titan:sm:sm123:elem:{encoded}:value"

    def test_parse_valid_key(self) -> None:
        """Valid key is parsed correctly."""
        key = "titan:aas:abc123:bytes"
        result = CacheKeys.parse_key(key)
        assert result is not None
        assert result["prefix"] == "titan"
        assert result["entity_type"] == "aas"
        assert result["identifier_b64"] == "abc123"
        assert result["variant"] == "bytes"

    def test_parse_invalid_key_returns_none(self) -> None:
        """Invalid key returns None."""
        assert CacheKeys.parse_key("invalid") is None
        assert CacheKeys.parse_key("other:prefix:key") is None
