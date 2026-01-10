"""OpenAPI contract tests.

Validates that API responses match the expected structure
defined by IDTA-01002 Part 2.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_live_returns_ok(self, api_client: AsyncClient) -> None:
        """Test /health/live returns status ok."""
        response = await api_client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires Redis/Database - run with integration tests")
    async def test_health_ready_returns_ok(self, api_client: AsyncClient) -> None:
        """Test /health/ready returns status ok."""
        response = await api_client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestDescriptionEndpoint:
    """Test /description endpoint per IDTA-01002 Part 2."""

    @pytest.mark.asyncio
    async def test_description_returns_profiles(self, api_client: AsyncClient) -> None:
        """Test /description returns list of service profiles."""
        response = await api_client.get("/description")

        assert response.status_code == 200
        data = response.json()

        # Must have profiles array
        assert "profiles" in data
        assert isinstance(data["profiles"], list)
        assert len(data["profiles"]) > 0

        # Each profile must be a valid URI
        for profile in data["profiles"]:
            assert profile.startswith("https://admin-shell.io/")

    @pytest.mark.asyncio
    async def test_description_returns_modifiers(self, api_client: AsyncClient) -> None:
        """Test /description returns modifiers."""
        response = await api_client.get("/description")

        assert response.status_code == 200
        data = response.json()

        # Must have modifiers array
        assert "modifiers" in data
        modifiers = data["modifiers"]
        assert isinstance(modifiers, list)
        assert "$value" in modifiers
        assert "$metadata" in modifiers

    @pytest.mark.asyncio
    async def test_description_profiles_list(self, api_client: AsyncClient) -> None:
        """Test /description/profiles returns list of profile URIs."""
        response = await api_client.get("/description/profiles")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert all(isinstance(p, str) for p in data)


@pytest.mark.skip(reason="Requires Redis - run with integration tests instead")
class TestAasRepository:
    """Test AAS Repository endpoints per IDTA-01002 Part 2.

    Note: These tests require Redis connectivity and should be run
    with integration tests that have testcontainers.
    """

    @pytest.mark.asyncio
    async def test_shells_list_returns_paginated_response(self, api_client: AsyncClient) -> None:
        """Test GET /shells returns paginated response."""
        response = await api_client.get("/shells")

        assert response.status_code == 200
        data = response.json()

        # Per IDTA-01002, list endpoints return { result, paging_metadata }
        assert "result" in data
        assert isinstance(data["result"], list)
        assert "paging_metadata" in data

    @pytest.mark.asyncio
    async def test_shell_not_found_returns_404(self, api_client: AsyncClient) -> None:
        """Test GET /shells/{id} returns 404 for non-existent AAS."""
        # Base64URL encoded "nonexistent"
        encoded_id = "bm9uZXhpc3RlbnQ"
        response = await api_client.get(f"/shells/{encoded_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_base64_returns_400(self, api_client: AsyncClient) -> None:
        """Test invalid Base64URL ID returns 400 Bad Request."""
        response = await api_client.get("/shells/!!!invalid!!!")

        assert response.status_code == 400


@pytest.mark.skip(reason="Requires Redis - run with integration tests instead")
class TestSubmodelRepository:
    """Test Submodel Repository endpoints per IDTA-01002 Part 2.

    Note: These tests require Redis connectivity and should be run
    with integration tests that have testcontainers.
    """

    @pytest.mark.asyncio
    async def test_submodels_list_returns_paginated_response(self, api_client: AsyncClient) -> None:
        """Test GET /submodels returns paginated response."""
        response = await api_client.get("/submodels")

        assert response.status_code == 200
        data = response.json()

        assert "result" in data
        assert isinstance(data["result"], list)
        assert "paging_metadata" in data

    @pytest.mark.asyncio
    async def test_submodel_not_found_returns_404(self, api_client: AsyncClient) -> None:
        """Test GET /submodels/{id} returns 404 for non-existent Submodel."""
        encoded_id = "bm9uZXhpc3RlbnQ"
        response = await api_client.get(f"/submodels/{encoded_id}")

        assert response.status_code == 404


class TestOpenAPISpec:
    """Test OpenAPI specification is accessible."""

    @pytest.mark.asyncio
    async def test_openapi_json_accessible(self, api_client: AsyncClient) -> None:
        """Test /openapi.json returns valid OpenAPI spec."""
        response = await api_client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()

        # Basic OpenAPI structure
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

        # Version should be 3.x
        assert data["openapi"].startswith("3.")

    @pytest.mark.asyncio
    async def test_docs_accessible(self, api_client: AsyncClient) -> None:
        """Test /docs (Swagger UI) is accessible."""
        response = await api_client.get("/docs")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redoc_accessible(self, api_client: AsyncClient) -> None:
        """Test /redoc is accessible."""
        response = await api_client.get("/redoc")

        assert response.status_code == 200
