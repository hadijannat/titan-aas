from __future__ import annotations

import base64
from typing import Final


_B64URL_ALPHABET: Final[str] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


class InvalidBase64Url(ValueError):
    pass


def encode_id_to_b64url(value: str) -> str:
    """Encode identifier to Base64URL without padding."""
    raw = value.encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    return encoded.rstrip("=")


def decode_id_from_b64url(value: str) -> str:
    """Decode Base64URL identifier without padding."""
    if not value:
        raise InvalidBase64Url("empty value")
    if any(ch not in _B64URL_ALPHABET for ch in value):
        raise InvalidBase64Url("invalid base64url alphabet")
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        return decoded.decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        raise InvalidBase64Url("invalid base64url value") from exc
