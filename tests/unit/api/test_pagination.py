"""Tests for cursor-based pagination."""

from datetime import datetime, timezone

from titan.api.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CursorData,
    PagingMetadata,
    decode_cursor,
    encode_cursor,
)


class TestCursorEncoding:
    """Test cursor encoding/decoding."""

    def test_encode_decode_roundtrip(self) -> None:
        """Cursor encodes and decodes correctly."""
        created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        item_id = "abc123"

        encoded = encode_cursor(created_at, item_id)
        decoded = decode_cursor(encoded)

        assert decoded is not None
        assert decoded.id == item_id
        assert decoded.created_at == created_at.isoformat()

    def test_encoded_cursor_is_url_safe(self) -> None:
        """Encoded cursor is URL-safe base64."""
        created_at = datetime.now(timezone.utc)
        encoded = encode_cursor(created_at, "test-id")

        # URL-safe base64 should not contain + or /
        assert "+" not in encoded
        assert "/" not in encoded
        # No padding (stripped)
        assert not encoded.endswith("=")

    def test_decode_invalid_cursor(self) -> None:
        """Invalid cursor returns None."""
        assert decode_cursor("not-valid-base64!!!") is None
        assert decode_cursor("") is None

    def test_decode_malformed_json(self) -> None:
        """Malformed JSON in cursor returns None."""
        import base64

        # Valid base64 but not valid JSON
        invalid = base64.urlsafe_b64encode(b"not json").decode("ascii")
        assert decode_cursor(invalid) is None


class TestCursorData:
    """Test CursorData dataclass."""

    def test_cursor_data(self) -> None:
        """CursorData stores expected fields."""
        data = CursorData(created_at="2024-01-15T10:30:00+00:00", id="test-uuid")
        assert data.created_at == "2024-01-15T10:30:00+00:00"
        assert data.id == "test-uuid"


class TestPagingMetadata:
    """Test PagingMetadata model."""

    def test_paging_metadata_with_cursor(self) -> None:
        """PagingMetadata with cursor."""
        meta = PagingMetadata(cursor="abc123")
        assert meta.cursor == "abc123"

    def test_paging_metadata_without_cursor(self) -> None:
        """PagingMetadata without cursor (last page)."""
        meta = PagingMetadata(cursor=None)
        assert meta.cursor is None


class TestConstants:
    """Test pagination constants."""

    def test_default_limit(self) -> None:
        """Default limit is reasonable."""
        assert DEFAULT_LIMIT == 100

    def test_max_limit(self) -> None:
        """Max limit prevents excessive queries."""
        assert MAX_LIMIT == 1000
