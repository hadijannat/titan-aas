"""API versioning and deprecation support.

Provides URL-based API versioning with:
- Version routing (/api/v1, /api/v2, etc.)
- Deprecation headers per RFC 8594
- Sunset date announcements
- Version negotiation via Accept header (optional)

Example:
    # Mount versioned APIs
    from titan.api.versioning import create_versioned_app

    v1 = create_versioned_app(ApiVersion.V1)
    v1.include_router(aas_repository.router)

    app.mount("/api/v1", v1)

    # Add deprecation to specific endpoints
    @v1_router.get("/old-endpoint")
    @deprecated(sunset_date=datetime(2025, 12, 31))
    async def old_endpoint():
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar

from fastapi import FastAPI, Request, Response
from fastapi.responses import ORJSONResponse
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class ApiVersion(str, Enum):
    """Supported API versions."""

    V1 = "v1"
    # V2 = "v2"  # Future version placeholder

    @property
    def prefix(self) -> str:
        """URL prefix for this version (e.g., '/api/v1')."""
        return f"/api/{self.value}"

    @property
    def is_deprecated(self) -> bool:
        """Check if this version is deprecated."""
        return self in DEPRECATED_VERSIONS

    @property
    def sunset_date(self) -> datetime | None:
        """Get sunset date for deprecated version."""
        return DEPRECATED_VERSIONS.get(self)


# Version deprecation schedule
# Add versions here when they're deprecated
DEPRECATED_VERSIONS: dict[ApiVersion, datetime] = {
    # Example: ApiVersion.V1: datetime(2026, 12, 31, tzinfo=timezone.utc),
}

# Current stable version (for Accept header negotiation)
CURRENT_VERSION = ApiVersion.V1


@dataclass
class VersionInfo:
    """Version information for API responses."""

    version: ApiVersion
    deprecated: bool = False
    sunset_date: datetime | None = None
    successor: ApiVersion | None = None

    def to_headers(self) -> dict[str, str]:
        """Generate HTTP headers for this version.

        Returns headers per RFC 8594 (Sunset Header):
        - Deprecation: true/false
        - Sunset: HTTP-date when API will be removed
        - Link: successor version with rel="successor-version"
        """
        headers: dict[str, str] = {
            "X-API-Version": self.version.value,
        }

        if self.deprecated:
            headers["Deprecation"] = "true"

            if self.sunset_date:
                # Format: Sun, 31 Dec 2025 23:59:59 GMT
                headers["Sunset"] = self.sunset_date.strftime(
                    "%a, %d %b %Y %H:%M:%S GMT"
                )

            if self.successor:
                # Link header for successor version
                headers["Link"] = (
                    f"<{self.successor.prefix}>; rel=\"successor-version\""
                )

        return headers


def get_version_info(version: ApiVersion) -> VersionInfo:
    """Get version information including deprecation status."""
    deprecated = version.is_deprecated
    sunset_date = version.sunset_date

    # Find successor version
    successor: ApiVersion | None = None
    if deprecated:
        versions = list(ApiVersion)
        idx = versions.index(version)
        if idx < len(versions) - 1:
            successor = versions[idx + 1]

    return VersionInfo(
        version=version,
        deprecated=deprecated,
        sunset_date=sunset_date,
        successor=successor,
    )


class VersionHeaderMiddleware(BaseHTTPMiddleware):
    """Middleware that adds version headers to all responses.

    Adds:
    - X-API-Version: current version
    - Deprecation: true (if deprecated)
    - Sunset: date (if sunset scheduled)
    - Link: successor version (if available)
    """

    def __init__(self, app: Any, version: ApiVersion) -> None:
        super().__init__(app)
        self.version = version
        self.version_info = get_version_info(version)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        # Add version headers
        for name, value in self.version_info.to_headers().items():
            response.headers[name] = value

        return response


@dataclass
class EndpointDeprecation:
    """Deprecation metadata for an endpoint."""

    deprecated: bool = True
    sunset_date: datetime | None = None
    successor_path: str | None = None
    message: str | None = None


def deprecated(
    sunset_date: datetime | None = None,
    successor_path: str | None = None,
    message: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to mark an endpoint as deprecated.

    Adds deprecation headers to the response:
    - Deprecation: true
    - Sunset: HTTP-date (if provided)
    - Link: successor path (if provided)

    Args:
        sunset_date: When the endpoint will be removed
        successor_path: Path to the replacement endpoint
        message: Custom deprecation message

    Example:
        @router.get("/old-shells")
        @deprecated(
            sunset_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            successor_path="/api/v2/shells",
            message="Use /api/v2/shells instead"
        )
        async def get_old_shells():
            ...
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        # Store deprecation info on function for documentation
        func.__deprecation__ = EndpointDeprecation(  # type: ignore[attr-defined]
            deprecated=True,
            sunset_date=sunset_date,
            successor_path=successor_path,
            message=message,
        )

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Get the Response object to add headers
            response: Response | None = None
            for arg in args:
                if isinstance(arg, Response):
                    response = arg
                    break
            for value in kwargs.values():
                if isinstance(value, Response):
                    response = value
                    break

            # Call the original function
            result = await func(*args, **kwargs)

            # If we have a Response, add deprecation headers
            if response is not None:
                response.headers["Deprecation"] = "true"
                if sunset_date:
                    response.headers["Sunset"] = sunset_date.strftime(
                        "%a, %d %b %Y %H:%M:%S GMT"
                    )
                if successor_path:
                    response.headers["Link"] = (
                        f"<{successor_path}>; rel=\"successor-version\""
                    )

            return result

        return wrapper

    return decorator


class DeprecatedRoute(APIRoute):
    """Custom route class that adds deprecation headers.

    Use this for routes that need deprecation headers:

        router = APIRouter(route_class=DeprecatedRoute)
    """

    def __init__(
        self,
        *args: Any,
        sunset_date: datetime | None = None,
        successor_path: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.sunset_date = sunset_date
        self.successor_path = successor_path

    def get_route_handler(self) -> Callable[[Request], Any]:
        original_handler = super().get_route_handler()

        async def handler(request: Request) -> Response:
            response = await original_handler(request)

            # Add deprecation headers
            response.headers["Deprecation"] = "true"
            if self.sunset_date:
                response.headers["Sunset"] = self.sunset_date.strftime(
                    "%a, %d %b %Y %H:%M:%S GMT"
                )
            if self.successor_path:
                response.headers["Link"] = (
                    f"<{self.successor_path}>; rel=\"successor-version\""
                )

            return response

        return handler


def negotiate_version(request: Request) -> ApiVersion:
    """Negotiate API version from Accept header.

    Supports content negotiation using Accept header:
    - Accept: application/json; version=v1
    - Accept: application/vnd.titan.v1+json

    Falls back to CURRENT_VERSION if no version specified.
    """
    accept = request.headers.get("Accept", "")

    # Check for version parameter
    if "version=" in accept:
        for part in accept.split(";"):
            if "version=" in part:
                version_str = part.split("=")[1].strip()
                try:
                    return ApiVersion(version_str)
                except ValueError:
                    pass

    # Check for vendor media type (e.g., application/vnd.titan.v1+json)
    if "vnd.titan." in accept:
        for version in ApiVersion:
            if f"vnd.titan.{version.value}" in accept:
                return version

    return CURRENT_VERSION


def create_versioned_app(
    version: ApiVersion,
    title: str = "Titan-AAS",
    **kwargs: Any,
) -> FastAPI:
    """Create a FastAPI sub-application for a specific API version.

    The sub-application can be mounted at the version prefix.

    Args:
        version: API version for this app
        title: Application title
        **kwargs: Additional FastAPI constructor arguments

    Returns:
        Configured FastAPI application for this version

    Example:
        v1 = create_versioned_app(ApiVersion.V1)
        v1.include_router(aas_repository.router)
        main_app.mount("/api/v1", v1)
    """
    version_info = get_version_info(version)

    app = FastAPI(
        title=f"{title} API {version.value.upper()}",
        version=version.value,
        default_response_class=ORJSONResponse,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        deprecated=version_info.deprecated,
        **kwargs,
    )

    # Add version header middleware
    app.add_middleware(VersionHeaderMiddleware, version=version)

    return app


def get_all_version_prefixes() -> list[str]:
    """Get all API version prefixes for routing."""
    return [v.prefix for v in ApiVersion]
