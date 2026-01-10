from __future__ import annotations

from fastapi import Response


def json_bytes_response(payload: bytes) -> Response:
    return Response(content=payload, media_type="application/json")
