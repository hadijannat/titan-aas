"""Middleware for Titan-AAS API.

Provides production-ready middleware:
- HTTP caching headers
- Gzip/Brotli compression
- Request rate limiting
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- Correlation context for request tracing

Note: For CORS, use FastAPI's built-in CORSMiddleware from starlette.middleware.cors
"""

from titan.api.middleware.caching import CachingMiddleware
from titan.api.middleware.compression import CompressionMiddleware
from titan.api.middleware.correlation import CorrelationMiddleware
from titan.api.middleware.rate_limit import RateLimitMiddleware
from titan.api.middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "CachingMiddleware",
    "CompressionMiddleware",
    "CorrelationMiddleware",
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
]
