"""Tests for API versioning and deprecation support."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from titan.api.versioning import (
    CURRENT_VERSION,
    ApiVersion,
    DeprecatedRoute,
    EndpointDeprecation,
    VersionHeaderMiddleware,
    VersionInfo,
    create_versioned_app,
    deprecated,
    get_all_version_prefixes,
    get_version_info,
    negotiate_version,
)


class TestApiVersion:
    """Tests for ApiVersion enum."""

    def test_version_values(self) -> None:
        """Version values match expected format."""
        assert ApiVersion.V1.value == "v1"

    def test_version_prefix(self) -> None:
        """Version prefix generates correct URL path."""
        assert ApiVersion.V1.prefix == "/api/v1"

    def test_version_is_deprecated_default(self) -> None:
        """Versions are not deprecated by default."""
        # V1 is not in DEPRECATED_VERSIONS by default
        assert not ApiVersion.V1.is_deprecated

    def test_version_sunset_date_default(self) -> None:
        """Sunset date is None for non-deprecated versions."""
        assert ApiVersion.V1.sunset_date is None


class TestVersionInfo:
    """Tests for VersionInfo dataclass."""

    def test_non_deprecated_headers(self) -> None:
        """Non-deprecated version produces minimal headers."""
        info = VersionInfo(
            version=ApiVersion.V1,
            deprecated=False,
        )

        headers = info.to_headers()

        assert headers["X-API-Version"] == "v1"
        assert "Deprecation" not in headers
        assert "Sunset" not in headers
        assert "Link" not in headers

    def test_deprecated_headers(self) -> None:
        """Deprecated version produces deprecation headers."""
        sunset = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)
        info = VersionInfo(
            version=ApiVersion.V1,
            deprecated=True,
            sunset_date=sunset,
            successor=None,  # No successor in current implementation
        )

        headers = info.to_headers()

        assert headers["X-API-Version"] == "v1"
        assert headers["Deprecation"] == "true"
        assert "31 Dec 2025" in headers["Sunset"]

    def test_deprecated_with_successor(self) -> None:
        """Deprecated version with successor includes Link header."""
        info = VersionInfo(
            version=ApiVersion.V1,
            deprecated=True,
            successor=ApiVersion.V1,  # Just for testing
        )

        headers = info.to_headers()

        assert "Link" in headers
        assert 'rel="successor-version"' in headers["Link"]


class TestGetVersionInfo:
    """Tests for get_version_info function."""

    def test_get_current_version_info(self) -> None:
        """Getting info for current version."""
        info = get_version_info(ApiVersion.V1)

        assert info.version == ApiVersion.V1
        assert info.deprecated == ApiVersion.V1.is_deprecated


class TestVersionHeaderMiddleware:
    """Tests for VersionHeaderMiddleware."""

    def test_middleware_adds_version_header(self) -> None:
        """Middleware adds X-API-Version header to responses."""
        app = FastAPI()
        app.add_middleware(VersionHeaderMiddleware, version=ApiVersion.V1)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-API-Version"] == "v1"


class TestNegotiateVersion:
    """Tests for version negotiation from Accept header."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test FastAPI app."""
        app = FastAPI()

        @app.get("/negotiate")
        async def negotiate_endpoint(request: Request) -> dict[str, str]:
            version = negotiate_version(request)
            return {"version": version.value}

        return app

    def test_default_version(self, app: FastAPI) -> None:
        """Returns current version when no version specified."""
        client = TestClient(app)
        response = client.get("/negotiate")

        data = response.json()
        assert data["version"] == CURRENT_VERSION.value

    def test_version_parameter(self, app: FastAPI) -> None:
        """Parses version from Accept header parameter."""
        client = TestClient(app)
        response = client.get(
            "/negotiate",
            headers={"Accept": "application/json; version=v1"},
        )

        data = response.json()
        assert data["version"] == "v1"

    def test_vendor_media_type(self, app: FastAPI) -> None:
        """Parses version from vendor media type."""
        client = TestClient(app)
        response = client.get(
            "/negotiate",
            headers={"Accept": "application/vnd.titan.v1+json"},
        )

        data = response.json()
        assert data["version"] == "v1"

    def test_invalid_version_falls_back(self, app: FastAPI) -> None:
        """Invalid version falls back to current."""
        client = TestClient(app)
        response = client.get(
            "/negotiate",
            headers={"Accept": "application/json; version=invalid"},
        )

        data = response.json()
        assert data["version"] == CURRENT_VERSION.value


class TestDeprecatedDecorator:
    """Tests for @deprecated decorator."""

    def test_decorator_stores_metadata(self) -> None:
        """Decorator stores deprecation metadata on function."""
        sunset = datetime(2025, 12, 31, tzinfo=UTC)

        @deprecated(sunset_date=sunset, successor_path="/new/path")
        async def old_endpoint() -> dict[str, str]:
            return {"message": "ok"}

        assert hasattr(old_endpoint, "__deprecation__")
        dep: EndpointDeprecation = old_endpoint.__deprecation__  # type: ignore[attr-defined]
        assert dep.deprecated is True
        assert dep.sunset_date == sunset
        assert dep.successor_path == "/new/path"


class TestDeprecatedRoute:
    """Tests for DeprecatedRoute class."""

    def test_deprecated_route_adds_headers(self) -> None:
        """DeprecatedRoute adds deprecation headers."""
        from fastapi import APIRouter

        sunset = datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)

        # Create router with deprecated route class
        router = APIRouter(route_class=DeprecatedRoute)

        @router.get("/deprecated")
        async def deprecated_endpoint() -> dict[str, str]:
            return {"message": "deprecated"}

        # Update the route with deprecation info
        for route in router.routes:
            if hasattr(route, "sunset_date"):
                route.sunset_date = sunset  # type: ignore[attr-defined]
                route.successor_path = "/api/v2/new"  # type: ignore[attr-defined]

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/deprecated")

        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"


class TestCreateVersionedApp:
    """Tests for create_versioned_app function."""

    def test_creates_app_with_version_middleware(self) -> None:
        """Creates FastAPI app with version header middleware."""
        app = create_versioned_app(ApiVersion.V1)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-API-Version"] == "v1"

    def test_creates_app_with_correct_title(self) -> None:
        """Creates app with version in title."""
        app = create_versioned_app(ApiVersion.V1, title="Test API")

        assert "V1" in app.title

    def test_creates_app_with_openapi(self) -> None:
        """Creates app with OpenAPI documentation."""
        app = create_versioned_app(ApiVersion.V1)

        assert app.openapi_url == "/openapi.json"
        assert app.docs_url == "/docs"


class TestGetAllVersionPrefixes:
    """Tests for get_all_version_prefixes function."""

    def test_returns_all_prefixes(self) -> None:
        """Returns prefixes for all versions."""
        prefixes = get_all_version_prefixes()

        assert "/api/v1" in prefixes
        assert len(prefixes) == len(ApiVersion)


class TestV1App:
    """Tests for v1 API application."""

    def test_v1_app_has_version_header(self) -> None:
        """V1 app adds version header to responses."""
        from titan.api.v1 import create_v1_app

        app = create_v1_app()

        # Add a test endpoint that doesn't require database
        @app.get("/test-version")
        async def test_endpoint() -> dict[str, str]:
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test-version")

        assert response.status_code == 200
        assert response.headers.get("X-API-Version") == "v1"

    def test_v1_app_has_openapi(self) -> None:
        """V1 app has OpenAPI documentation."""
        from titan.api.v1 import create_v1_app

        app = create_v1_app()
        client = TestClient(app)

        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "V1" in data["info"]["title"]
