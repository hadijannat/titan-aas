from __future__ import annotations

from fastapi import Response


def json_bytes_response(payload: bytes, status_code: int | None = None) -> Response:
    if status_code is None:
        return Response(content=payload, media_type="application/json")
    return Response(content=payload, media_type="application/json", status_code=status_code)
