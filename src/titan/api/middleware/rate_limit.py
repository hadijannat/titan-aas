"""Rate limiting middleware for Titan-AAS.

Provides Redis-backed sliding window rate limiting.
Supports both IP-based and token-based limiting.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

if TYPE_CHECKING:
    from redis.asyncio import Redis


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    # Maximum requests per window
    requests_per_window: int = 100
    # Window duration in seconds
    window_seconds: int = 60
    # Path prefixes to bypass (health checks, metrics)
    bypass_prefixes: list[str] = field(
        default_factory=lambda: ["/health", "/metrics"]
    )
    # IPs to bypass (internal services)
    bypass_ips: list[str] = field(default_factory=list)


class SlidingWindowRateLimiter:
    """Redis-backed sliding window rate limiter.

    Uses sorted sets to implement accurate sliding window counting.
    """

    def __init__(self, redis: Redis, config: RateLimitConfig):
        self.redis = redis
        self.config = config

    async def is_allowed(self, key: str) -> tuple[bool, dict[str, str]]:
        """Check if request is allowed.

        Returns:
            Tuple of (allowed, headers) where headers contains
            rate limit information.
        """
        now = time.time()
        window_start = now - self.config.window_seconds

        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()

        # Remove old entries outside the window
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current requests in window
        pipe.zcard(key)

        # Add this request
        pipe.zadd(key, {str(now): now})

        # Set TTL to clean up old keys
        pipe.expire(key, self.config.window_seconds + 1)

        results = await pipe.execute()
        current_count = results[1]

        limit = self.config.requests_per_window
        remaining = max(0, limit - current_count - 1)
        reset_at = int(now) + self.config.window_seconds

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }

        allowed = current_count < limit
        if not allowed:
            headers["Retry-After"] = str(self.config.window_seconds)

        return allowed, headers


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with IP and token support.

    Features:
    - Sliding window algorithm for accurate limiting
    - IP-based rate limiting for unauthenticated requests
    - Token-based rate limiting for authenticated requests
    - Bypass paths for health checks and metrics
    - Standard rate limit headers
    - Lazy Redis initialization (gets Redis at request time)
    """

    def __init__(self, app, config: RateLimitConfig | None = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self._limiter: SlidingWindowRateLimiter | None = None

    def _get_limiter(self, redis: Redis) -> SlidingWindowRateLimiter:
        """Get or create the rate limiter with the given Redis client."""
        if self._limiter is None:
            self._limiter = SlidingWindowRateLimiter(redis, self.config)
        return self._limiter

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting to request."""
        # Check bypass paths
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.config.bypass_prefixes):
            return await call_next(request)

        # Check bypass IPs
        client_ip = self._get_client_ip(request)
        if client_ip in self.config.bypass_ips:
            return await call_next(request)

        # Get rate limit key
        key = self._get_rate_limit_key(request)

        try:
            # Get Redis lazily at request time
            from titan.cache import get_redis
            redis = await get_redis()
            limiter = self._get_limiter(redis)
            allowed, headers = await limiter.is_allowed(key)
        except Exception:
            # If Redis is unavailable, allow the request
            # but don't add rate limit headers
            return await call_next(request)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "messages": [
                        {
                            "code": "TooManyRequests",
                            "messageType": "Error",
                            "text": "Rate limit exceeded. Please retry later.",
                        }
                    ]
                },
                headers=headers,
            )

        # Process request and add rate limit headers to response
        response = await call_next(request)

        for name, value in headers.items():
            response.headers[name] = value

        return response

    def _get_rate_limit_key(self, request: Request) -> str:
        """Determine rate limit key from request.

        Uses token hash for authenticated requests,
        IP address for unauthenticated requests.
        """
        # Try API token first (from Authorization header)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            # Hash token for privacy
            token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
            return f"ratelimit:token:{token_hash}"

        # Fall back to IP address
        client_ip = self._get_client_ip(request)
        return f"ratelimit:ip:{client_ip}"

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, handling proxies.

        Checks standard proxy headers in order of preference.
        """
        # Check X-Forwarded-For (common for load balancers)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the first IP (original client)
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP (nginx)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct client IP
        if request.client:
            return request.client.host

        return "unknown"
