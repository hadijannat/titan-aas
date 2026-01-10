"""Metrics endpoint for Prometheus scraping.

Exposes /metrics endpoint in Prometheus exposition format.
"""

from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import Response

from titan.observability.metrics import get_metrics

router = APIRouter(tags=["observability"])


@router.get(
    "/metrics",
    response_class=Response,
    summary="Prometheus metrics",
    description="Prometheus metrics in exposition format",
    responses={
        200: {
            "description": "Prometheus metrics",
            "content": {"text/plain": {}},
        }
    },
)
async def get_prometheus_metrics() -> Response:
    """Return Prometheus metrics in exposition format."""
    metrics = get_metrics()
    content = metrics.generate_latest()

    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
