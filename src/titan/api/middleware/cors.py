"""CORS (Cross-Origin Resource Sharing) middleware configuration.

Provides configurable CORS settings for the Titan-AAS API:
- Whitelist-based origin validation
- Configurable allowed methods and headers
- Credential support for authenticated requests
- Preflight caching

Security notes:
- Never use "*" for origins in production with credentials
- Validate origins against a whitelist
- Be restrictive with allowed methods and headers
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


@dataclass
class CORSConfig:
    """CORS configuration settings.

    Attributes:
        allow_origins: List of allowed origin patterns (e.g., ["https://example.com"])
        allow_origin_regex: Regex pattern for allowed origins
        allow_methods: Allowed HTTP methods
        allow_headers: Allowed request headers
        allow_credentials: Whether to allow credentials (cookies, auth headers)
        expose_headers: Headers to expose to the browser
        max_age: Preflight cache duration in seconds
    """

    # Origins - be specific in production!
    allow_origins: list[str] = field(default_factory=lambda: ["*"])
    allow_origin_regex: str | None = None

    # Methods - restrict to what's needed
    allow_methods: list[str] = field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    )

    # Headers
    allow_headers: list[str] = field(
        default_factory=lambda: [
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-Correlation-ID",
            "If-Match",
            "If-None-Match",
            "Accept",
            "Accept-Language",
        ]
    )

    # Credentials - enable for authenticated requests
    allow_credentials: bool = False

    # Exposed headers - what the browser can access
    expose_headers: list[str] = field(
        default_factory=lambda: [
            "X-Request-ID",
            "X-Correlation-ID",
            "ETag",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "Content-Disposition",
        ]
    )

    # Preflight cache (10 minutes default)
    max_age: int = 600

    @classmethod
    def development(cls) -> CORSConfig:
        """Create a permissive config for development."""
        return cls(
            allow_origins=["*"],
            allow_credentials=False,  # Can't use credentials with "*" origins
            max_age=3600,
        )

    @classmethod
    def production(
        cls,
        allowed_origins: Sequence[str],
        allow_credentials: bool = True,
    ) -> CORSConfig:
        """Create a restrictive config for production.

        Args:
            allowed_origins: Specific origins to allow
            allow_credentials: Whether to allow credentials

        Example:
            config = CORSConfig.production(
                allowed_origins=[
                    "https://app.example.com",
                    "https://admin.example.com",
                ],
                allow_credentials=True,
            )
        """
        if not allowed_origins:
            raise ValueError("Production config requires at least one allowed origin")

        return cls(
            allow_origins=list(allowed_origins),
            allow_credentials=allow_credentials,
            max_age=3600,  # 1 hour cache
        )

    @classmethod
    def from_env(cls) -> CORSConfig:
        """Create config from environment variables.

        Environment variables:
            CORS_ORIGINS: Comma-separated list of origins
            CORS_CREDENTIALS: "true" or "false"
            CORS_MAX_AGE: Integer seconds
        """
        import os

        origins_str = os.environ.get("CORS_ORIGINS", "*")
        if origins_str == "*":
            origins = ["*"]
        else:
            origins = [o.strip() for o in origins_str.split(",")]

        credentials = os.environ.get("CORS_CREDENTIALS", "false").lower() == "true"

        # Validate: can't use credentials with wildcard origins
        if credentials and "*" in origins:
            raise ValueError(
                "CORS_CREDENTIALS=true cannot be used with CORS_ORIGINS=*. "
                "Specify explicit origins when using credentials."
            )

        max_age = int(os.environ.get("CORS_MAX_AGE", "600"))

        return cls(
            allow_origins=origins,
            allow_credentials=credentials,
            max_age=max_age,
        )


def add_cors_middleware(app: FastAPI, config: CORSConfig | None = None) -> None:
    """Add CORS middleware to the FastAPI application.

    Args:
        app: FastAPI application
        config: CORS configuration (defaults to development config)
    """
    config = config or CORSConfig.development()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.allow_origins,
        allow_origin_regex=config.allow_origin_regex,
        allow_credentials=config.allow_credentials,
        allow_methods=config.allow_methods,
        allow_headers=config.allow_headers,
        expose_headers=config.expose_headers,
        max_age=config.max_age,
    )


def validate_origin(origin: str, allowed_origins: Sequence[str]) -> bool:
    """Validate an origin against the allowed list.

    Args:
        origin: The origin to validate
        allowed_origins: List of allowed origins (may include "*")

    Returns:
        True if origin is allowed
    """
    if "*" in allowed_origins:
        return True

    # Exact match
    if origin in allowed_origins:
        return True

    # Check for subdomain wildcards (e.g., "*.example.com")
    for allowed in allowed_origins:
        if allowed.startswith("*."):
            suffix = allowed[1:]  # ".example.com"
            if origin.endswith(suffix):
                # Ensure there's a proper subdomain
                prefix = origin[: -len(suffix)]
                if prefix and "://" in prefix:
                    return True

    return False
