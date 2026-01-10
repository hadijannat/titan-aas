"""Request signing for sensitive operations.

Provides HMAC-based request signing for:
- API-to-API authentication
- Webhook verification
- Sensitive operation confirmation

The signing scheme uses HMAC-SHA256 with a shared secret:
1. Canonical request string is constructed
2. HMAC signature is computed
3. Signature is included in Authorization header or X-Signature header

Example:
    # Sign an outgoing request
    signer = RequestSigner(secret_key)
    headers = signer.sign_request(method, path, body, headers)

    # Verify an incoming request
    verifier = RequestVerifier(secret_key)
    if not verifier.verify_request(request):
        raise HTTPException(401, "Invalid signature")
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.types import Receive, Scope, Send

if TYPE_CHECKING:
    from starlette.requests import Request

# Signature validity window (5 minutes)
TIMESTAMP_TOLERANCE = 300

# Header names
SIGNATURE_HEADER = "X-Signature"
TIMESTAMP_HEADER = "X-Timestamp"
SIGNATURE_VERSION_HEADER = "X-Signature-Version"


@dataclass
class SignatureComponents:
    """Components used in signature computation."""

    method: str
    path: str
    query: str
    timestamp: str
    body_hash: str

    def to_canonical_string(self) -> str:
        """Create the canonical string to sign.

        Format:
            METHOD
            PATH
            QUERY
            TIMESTAMP
            BODY_HASH
        """
        return "\n".join(
            [
                self.method.upper(),
                self.path,
                self.query,
                self.timestamp,
                self.body_hash,
            ]
        )


class RequestSigner:
    """Signs outgoing HTTP requests with HMAC-SHA256.

    Usage:
        signer = RequestSigner(secret_key="your-shared-secret")

        # For requests with body
        headers = signer.sign_request(
            method="POST",
            path="/shells",
            body=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )

        # For GET requests (no body)
        headers = signer.sign_request(
            method="GET",
            path="/shells/abc123",
            query="level=deep",
        )
    """

    def __init__(self, secret_key: str | bytes, algorithm: str = "sha256"):
        if isinstance(secret_key, str):
            secret_key = secret_key.encode("utf-8")
        self.secret_key = secret_key
        self.algorithm = algorithm

    def sign_request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        query: str = "",
        headers: dict[str, str] | None = None,
        timestamp: int | None = None,
    ) -> dict[str, str]:
        """Sign a request and return updated headers.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (e.g., "/shells/abc123")
            body: Request body bytes (optional)
            query: Query string without leading "?" (optional)
            headers: Existing headers to include
            timestamp: Unix timestamp (defaults to current time)

        Returns:
            Updated headers dict with signature headers added
        """
        headers = dict(headers) if headers else {}
        timestamp = timestamp or int(time.time())

        # Compute body hash (empty string for no body)
        body_hash = self._hash_body(body)

        # Create signature components
        components = SignatureComponents(
            method=method,
            path=path,
            query=query,
            timestamp=str(timestamp),
            body_hash=body_hash,
        )

        # Compute signature
        canonical = components.to_canonical_string()
        signature = self._compute_signature(canonical)

        # Add signature headers
        headers[TIMESTAMP_HEADER] = str(timestamp)
        headers[SIGNATURE_HEADER] = signature
        headers[SIGNATURE_VERSION_HEADER] = "1"

        return headers

    def _hash_body(self, body: bytes | None) -> str:
        """Hash the request body."""
        if body is None or len(body) == 0:
            body = b""
        digest = hashlib.sha256(body).digest()
        return base64.b64encode(digest).decode("ascii")

    def _compute_signature(self, canonical: str) -> str:
        """Compute HMAC signature of canonical string."""
        mac = hmac.new(
            self.secret_key,
            canonical.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("ascii")


class RequestVerifier:
    """Verifies incoming request signatures.

    Usage:
        verifier = RequestVerifier(secret_key="your-shared-secret")

        @app.middleware("http")
        async def verify_signature(request: Request, call_next):
            if request.url.path.startswith("/api/"):
                body = await request.body()
                if not verifier.verify_request(request, body):
                    raise HTTPException(401, "Invalid signature")
            return await call_next(request)
    """

    def __init__(
        self,
        secret_key: str | bytes,
        timestamp_tolerance: int = TIMESTAMP_TOLERANCE,
    ):
        if isinstance(secret_key, str):
            secret_key = secret_key.encode("utf-8")
        self.secret_key = secret_key
        self.timestamp_tolerance = timestamp_tolerance
        self._signer = RequestSigner(secret_key)

    def verify_request(
        self,
        request: Request,
        body: bytes | None = None,
    ) -> bool:
        """Verify a request's signature.

        Args:
            request: Starlette/FastAPI request object
            body: Request body bytes (if already read)

        Returns:
            True if signature is valid, False otherwise
        """
        # Get signature from header
        signature = request.headers.get(SIGNATURE_HEADER)
        if not signature:
            return False

        # Get and validate timestamp
        timestamp_str = request.headers.get(TIMESTAMP_HEADER)
        if not timestamp_str:
            return False

        try:
            timestamp = int(timestamp_str)
        except ValueError:
            return False

        # Check timestamp is within tolerance
        current_time = int(time.time())
        if abs(current_time - timestamp) > self.timestamp_tolerance:
            return False

        # Compute expected signature
        path = request.url.path
        query = request.url.query or ""
        method = request.method

        expected_headers = self._signer.sign_request(
            method=method,
            path=path,
            body=body,
            query=query,
            timestamp=timestamp,
        )

        expected_signature = expected_headers[SIGNATURE_HEADER]

        # Compare signatures using constant-time comparison
        return hmac.compare_digest(signature, expected_signature)

    def verify_components(
        self,
        method: str,
        path: str,
        body: bytes | None,
        query: str,
        timestamp: int,
        signature: str,
    ) -> bool:
        """Verify signature from individual components.

        Useful when not working with a Request object directly.
        """
        # Check timestamp
        current_time = int(time.time())
        if abs(current_time - timestamp) > self.timestamp_tolerance:
            return False

        # Compute expected signature
        expected_headers = self._signer.sign_request(
            method=method,
            path=path,
            body=body,
            query=query,
            timestamp=timestamp,
        )

        expected_signature = expected_headers[SIGNATURE_HEADER]
        return hmac.compare_digest(signature, expected_signature)


class SignatureMiddleware:
    """FastAPI middleware for request signature verification.

    Verifies signatures on specified paths and rejects invalid requests.

    Usage:
        from fastapi import FastAPI
        from titan.security.signing import SignatureMiddleware

        app = FastAPI()
        app.add_middleware(
            SignatureMiddleware,
            secret_key="your-shared-secret",
            protected_paths=["/api/", "/webhooks/"],
            excluded_paths=["/api/public/"],
        )
    """

    def __init__(
        self,
        app: Any,
        secret_key: str | bytes,
        protected_paths: list[str] | None = None,
        excluded_paths: list[str] | None = None,
        timestamp_tolerance: int = TIMESTAMP_TOLERANCE,
    ):
        self.app = app
        self.verifier = RequestVerifier(secret_key, timestamp_tolerance)
        self.protected_paths = protected_paths or []
        self.excluded_paths = excluded_paths or []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Check if path should be verified
        if not self._should_verify(path):
            await self.app(scope, receive, send)
            return

        # Create request object and read body
        from starlette.requests import Request

        request = Request(scope, receive)
        body = await request.body()

        # Verify signature
        if not self.verifier.verify_request(request, body):
            # Return 401 Unauthorized
            response_body = b'{"error": "Invalid or missing request signature"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [[b"content-type", b"application/json"]],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": response_body,
                }
            )
            return

        # Continue to next middleware/route
        await self.app(scope, receive, send)

    def _should_verify(self, path: str) -> bool:
        """Check if a path should have its signature verified."""
        # Check exclusions first
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return False

        # Check if in protected paths
        if not self.protected_paths:
            return False

        for protected in self.protected_paths:
            if path.startswith(protected):
                return True

        return False


def generate_secret_key(length: int = 32) -> str:
    """Generate a cryptographically secure secret key.

    Args:
        length: Length of key in bytes (will be base64 encoded)

    Returns:
        Base64-encoded secret key
    """
    import secrets

    return base64.b64encode(secrets.token_bytes(length)).decode("ascii")
