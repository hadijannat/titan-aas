"""Compression middleware for Titan-AAS.

Provides Gzip and Brotli compression for API responses.
Intelligently filters by content type and size.
"""

from __future__ import annotations

import gzip
import io

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp

# Try to import brotli, fall back to gzip-only if not available
try:
    import brotli

    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False


# Content types that benefit from compression
COMPRESSIBLE_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "text/plain",
        "text/html",
        "text/xml",
        "text/css",
        "text/javascript",
        "application/javascript",
    }
)


class CompressionMiddleware(BaseHTTPMiddleware):
    """Smart compression middleware with content-type and size filtering.

    Features:
    - Brotli compression (if available) for best ratio
    - Gzip fallback for broad compatibility
    - Size threshold to avoid compressing small responses
    - Content-type filtering
    - Streaming response passthrough
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compression_level: int = 6,
    ) -> None:
        super().__init__(app)
        self.minimum_size = minimum_size
        self.gzip_level = min(compression_level, 9)
        self.brotli_quality = min(compression_level, 11)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Compress response if appropriate."""
        # Check if client accepts compression
        accept_encoding = request.headers.get("accept-encoding", "")

        response = await call_next(request)

        # Skip streaming responses (they handle their own encoding)
        if isinstance(response, StreamingResponse):
            return response

        # Skip if already compressed
        if "content-encoding" in response.headers:
            return response

        # Skip if not compressible content type
        if not self._is_compressible(response):
            return response

        # Get response body
        body = bytes(response.body)

        # Skip small responses
        if len(body) < self.minimum_size:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # Compress based on Accept-Encoding
        compressed_body: bytes
        encoding: str

        if BROTLI_AVAILABLE and "br" in accept_encoding:
            compressed_body = brotli.compress(body, quality=self.brotli_quality)
            encoding = "br"
        elif "gzip" in accept_encoding:
            compressed_body = self._gzip_compress(body)
            encoding = "gzip"
        else:
            # Client doesn't accept compression
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # Only use compressed version if it's actually smaller
        if len(compressed_body) >= len(body):
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # Build compressed response
        headers = dict(response.headers)
        headers["Content-Encoding"] = encoding
        headers["Content-Length"] = str(len(compressed_body))

        # Ensure Vary includes Accept-Encoding
        vary = headers.get("Vary", "")
        if "Accept-Encoding" not in vary:
            if vary:
                headers["Vary"] = f"{vary}, Accept-Encoding"
            else:
                headers["Vary"] = "Accept-Encoding"

        return Response(
            content=compressed_body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )

    def _is_compressible(self, response: Response) -> bool:
        """Check if response content type is compressible."""
        content_type = response.media_type or ""
        # Check if content type starts with any compressible type
        return any(ct in content_type for ct in COMPRESSIBLE_TYPES)

    def _gzip_compress(self, data: bytes) -> bytes:
        """Compress data with gzip."""
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=self.gzip_level) as f:
            f.write(data)
        return buf.getvalue()
