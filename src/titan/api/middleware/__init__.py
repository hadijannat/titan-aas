"""Middleware for Titan-AAS API.

Provides production-ready middleware:
- HTTP caching headers
- Gzip/Brotli compression
- Request rate limiting
- CORS configuration
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
"""

from titan.api.middleware.caching import CachingMiddleware
from titan.api.middleware.compression import CompressionMiddleware
from titan.api.middleware.cors import CORSConfig, add_cors_middleware
from titan.api.middleware.rate_limit import RateLimitMiddleware
from titan.api.middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "CachingMiddleware",
    "CompressionMiddleware",
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
    "CORSConfig",
    "add_cors_middleware",
]
