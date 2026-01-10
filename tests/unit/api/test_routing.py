"""Tests for fast/slow path routing."""

from unittest.mock import Mock

import pytest

from titan.api.routing import (
    PathType,
    detect_path_type,
    is_fast_path,
)


def make_request(query_params: dict[str, str] | None = None, path: str = "/shells") -> Mock:
    """Create a mock request with query parameters."""
    request = Mock()
    request.query_params = query_params or {}
    request.url = Mock()
    request.url.path = path
    return request


class TestPathType:
    """Test PathType enum."""

    def test_path_types_exist(self) -> None:
        """PathType has FAST and SLOW."""
        assert PathType.FAST.value == "fast"
        assert PathType.SLOW.value == "slow"


class TestDetectPathType:
    """Test detect_path_type function."""

    def test_no_params_is_fast(self) -> None:
        """Request with no query params is fast path."""
        request = make_request()
        assert detect_path_type(request) == PathType.FAST

    def test_level_param_is_slow(self) -> None:
        """Request with level param is slow path."""
        request = make_request({"level": "deep"})
        assert detect_path_type(request) == PathType.SLOW

    def test_extent_param_is_slow(self) -> None:
        """Request with extent param is slow path."""
        request = make_request({"extent": "withoutBlobValue"})
        assert detect_path_type(request) == PathType.SLOW

    def test_content_param_is_slow(self) -> None:
        """Request with content param is slow path."""
        request = make_request({"content": "metadata"})
        assert detect_path_type(request) == PathType.SLOW

    def test_multiple_modifiers_is_slow(self) -> None:
        """Request with multiple modifiers is slow path."""
        request = make_request({
            "level": "core",
            "content": "value",
        })
        assert detect_path_type(request) == PathType.SLOW

    def test_pagination_params_still_fast(self) -> None:
        """Pagination params don't make request slow."""
        request = make_request({
            "limit": "100",
            "cursor": "abc123",
        })
        assert detect_path_type(request) == PathType.FAST


class TestIsFastPath:
    """Test is_fast_path helper."""

    def test_is_fast_path_no_params(self) -> None:
        """Request with no params is fast."""
        request = make_request()
        assert is_fast_path(request) is True

    def test_is_fast_path_with_modifiers(self) -> None:
        """Request with modifiers is not fast."""
        request = make_request({"level": "core"})
        assert is_fast_path(request) is False

    def test_is_fast_path_with_limit(self) -> None:
        """Request with only limit is still fast."""
        request = make_request({"limit": "50"})
        assert is_fast_path(request) is True
