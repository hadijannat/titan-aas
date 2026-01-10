from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Request, Response


async def request_id_middleware(request: Request, call_next: Callable) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response
