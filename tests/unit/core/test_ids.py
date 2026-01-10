"""Tests for Base64URL identifier encoding/decoding.

IDTA-01002 Part 2 requires:
- Identifiers in path segments must be Base64URL encoded
- The encoded value shall not contain or end with '=' padding
"""

import pytest

from titan.core.ids import (
    InvalidBase64Url,
    decode_id_from_b64url,
    encode_id_to_b64url,
)


class TestBase64UrlEncoding:
    """Test Base64URL encoding without padding."""

    def test_encode_simple_string(self) -> None:
        """Simple ASCII string encodes correctly."""
        result = encode_id_to_b64url("hello")
        assert result == "aGVsbG8"
        assert "=" not in result  # No padding

    def test_encode_iri(self) -> None:
        """IRI identifier encodes correctly."""
        iri = "https://example.com/aas/1"
        result = encode_id_to_b64url(iri)
        assert "=" not in result
        # Should be reversible
        assert decode_id_from_b64url(result) == iri

    def test_encode_urn(self) -> None:
        """URN identifier encodes correctly."""
        urn = "urn:example:aas:12345"
        result = encode_id_to_b64url(urn)
        assert "=" not in result
        assert decode_id_from_b64url(result) == urn

    def test_encode_unicode(self) -> None:
        """Unicode characters encode correctly."""
        text = "Prüfung mit Ümläuten"
        result = encode_id_to_b64url(text)
        assert "=" not in result
        assert decode_id_from_b64url(result) == text

    def test_encode_empty_string(self) -> None:
        """Empty string encodes to empty string."""
        result = encode_id_to_b64url("")
        assert result == ""

    def test_encode_produces_base64url_alphabet(self) -> None:
        """Encoded value uses only Base64URL alphabet."""
        # String that would produce '+' and '/' in standard base64
        text = "?????"  # Multiple question marks
        result = encode_id_to_b64url(text)
        # Base64URL uses '-' instead of '+' and '_' instead of '/'
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in result)


class TestBase64UrlDecoding:
    """Test Base64URL decoding with padding restoration."""

    def test_decode_simple_string(self) -> None:
        """Simple encoded string decodes correctly."""
        result = decode_id_from_b64url("aGVsbG8")
        assert result == "hello"

    def test_decode_requires_padding_restoration(self) -> None:
        """Strings that need padding are decoded correctly."""
        # "a" in base64 is "YQ==" with padding, "YQ" without
        result = decode_id_from_b64url("YQ")
        assert result == "a"

    def test_decode_with_padding_2(self) -> None:
        """Strings needing 2 padding chars decode correctly."""
        # "ab" in base64 is "YWI=" with padding, "YWI" without
        result = decode_id_from_b64url("YWI")
        assert result == "ab"

    def test_roundtrip_various_lengths(self) -> None:
        """Round-trip works for strings of various lengths."""
        test_strings = [
            "a",
            "ab",
            "abc",
            "abcd",
            "abcde",
            "https://example.com/aas/some-identifier",
            "urn:iec:cdd:0173#01-ABC123",
        ]
        for s in test_strings:
            encoded = encode_id_to_b64url(s)
            decoded = decode_id_from_b64url(encoded)
            assert decoded == s, f"Failed for: {s}"

    def test_decode_empty_raises(self) -> None:
        """Empty string raises InvalidBase64Url."""
        with pytest.raises(InvalidBase64Url, match="empty"):
            decode_id_from_b64url("")

    def test_decode_invalid_alphabet_raises(self) -> None:
        """Invalid characters raise InvalidBase64Url."""
        with pytest.raises(InvalidBase64Url, match="invalid"):
            decode_id_from_b64url("abc+def")  # '+' is not in base64url

    def test_decode_standard_base64_raises(self) -> None:
        """Standard base64 with '+' and '/' raises error."""
        with pytest.raises(InvalidBase64Url):
            decode_id_from_b64url("abc/def")


class TestIdtaCompliance:
    """Test IDTA-specific requirements."""

    def test_no_padding_in_output(self) -> None:
        """IDTA requires no '=' padding in encoded identifiers."""
        # These test cases would produce padding in standard base64
        test_cases = [
            "a",  # Would be "YQ=="
            "ab",  # Would be "YWI="
            "https://example.com",  # Various padding scenarios
        ]
        for text in test_cases:
            encoded = encode_id_to_b64url(text)
            assert not encoded.endswith("="), f"Padding found for: {text}"

    def test_idta_example_identifiers(self) -> None:
        """Test with typical IDTA-style identifiers."""
        identifiers = [
            "https://admin-shell.io/zvei/nameplate/2/0/Nameplate",
            "urn:iec:cdd:0173#01-ABC123#001",
            "https://example.com/aas/1234567890",
            "http://customer.com/assets/serial/XYZ-001",
        ]
        for ident in identifiers:
            encoded = encode_id_to_b64url(ident)
            decoded = decode_id_from_b64url(encoded)
            assert decoded == ident
            assert "=" not in encoded
