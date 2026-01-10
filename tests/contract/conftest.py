"""Contract test fixtures.

Uses httpx for API testing against the OpenAPI specification.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    """Create an API client for contract testing."""
    from titan.api.app import create_app

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
