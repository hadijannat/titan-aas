"""Integration tests for API endpoints.

Tests the full request/response cycle with real database and cache.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from titan.core.ids import encode_id_to_b64url as encode_id

# Skip if testcontainers not available
pytest.importorskip("testcontainers")


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, test_client: AsyncClient) -> None:
        """Test /health/live endpoint returns OK."""
        response = await test_client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_ready_endpoint(self, test_client: AsyncClient) -> None:
        """Test /health/ready endpoint returns OK when all services are up."""
        response = await test_client.get("/health/ready")
        # May be 200 or 503 depending on DB/Redis connectivity
        assert response.status_code in (200, 503)


class TestAasEndpoints:
    """Tests for AAS Repository API endpoints."""

    @pytest.fixture
    def sample_aas(self) -> dict:
        """Create sample AAS payload."""
        return {
            "id": "urn:example:aas:integration-test",
            "idShort": "IntegrationTestAAS",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": "urn:example:asset:integration-test",
            },
        }

    @pytest.mark.asyncio
    async def test_create_aas(self, test_client: AsyncClient, sample_aas: dict) -> None:
        """Test POST /shells creates an AAS."""
        response = await test_client.post("/shells", json=sample_aas)

        if response.status_code != 201:
            print(f"Response body: {response.json()}")
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == sample_aas["id"]
        assert data["idShort"] == sample_aas["idShort"]

        # Verify Location header
        assert "Location" in response.headers

    @pytest.mark.asyncio
    async def test_get_aas(self, test_client: AsyncClient, sample_aas: dict) -> None:
        """Test GET /shells/{id} retrieves an AAS."""
        # Create first
        await test_client.post("/shells", json=sample_aas)

        # Get by encoded ID
        encoded_id = encode_id(sample_aas["id"])
        response = await test_client.get(f"/shells/{encoded_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_aas["id"]

        # Verify ETag header
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    async def test_get_aas_not_found(self, test_client: AsyncClient) -> None:
        """Test GET /shells/{id} returns 404 for missing AAS."""
        encoded_id = encode_id("urn:example:aas:nonexistent")
        response = await test_client.get(f"/shells/{encoded_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_aas(self, test_client: AsyncClient, sample_aas: dict) -> None:
        """Test GET /shells returns list of AAS."""
        # Create an AAS
        await test_client.post("/shells", json=sample_aas)

        response = await test_client.get("/shells")

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert isinstance(data["result"], list)

    @pytest.mark.asyncio
    async def test_update_aas(self, test_client: AsyncClient, sample_aas: dict) -> None:
        """Test PUT /shells/{id} updates an AAS."""
        # Create first
        await test_client.post("/shells", json=sample_aas)

        # Update
        updated = {**sample_aas, "idShort": "UpdatedAAS"}
        encoded_id = encode_id(sample_aas["id"])
        response = await test_client.put(f"/shells/{encoded_id}", json=updated)

        assert response.status_code in (200, 204)

        # Verify update
        get_response = await test_client.get(f"/shells/{encoded_id}")
        data = get_response.json()
        assert data["idShort"] == "UpdatedAAS"

    @pytest.mark.asyncio
    async def test_delete_aas(self, test_client: AsyncClient, sample_aas: dict) -> None:
        """Test DELETE /shells/{id} removes an AAS."""
        # Create first
        await test_client.post("/shells", json=sample_aas)

        # Delete
        encoded_id = encode_id(sample_aas["id"])
        response = await test_client.delete(f"/shells/{encoded_id}")

        assert response.status_code in (200, 204)

        # Verify deletion
        get_response = await test_client.get(f"/shells/{encoded_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_aas_returns_conflict(
        self, test_client: AsyncClient, sample_aas: dict
    ) -> None:
        """Test POST /shells returns 409 for duplicate ID."""
        # Create first
        response1 = await test_client.post("/shells", json=sample_aas)
        assert response1.status_code == 201

        # Try to create duplicate
        response2 = await test_client.post("/shells", json=sample_aas)
        assert response2.status_code == 409


class TestSubmodelEndpoints:
    """Tests for Submodel Repository API endpoints."""

    @pytest.fixture
    def sample_submodel(self) -> dict:
        """Create sample Submodel payload."""
        return {
            "id": "urn:example:submodel:integration-test",
            "idShort": "IntegrationTestSubmodel",
            "submodelElements": [
                {
                    "modelType": "Property",
                    "idShort": "TestProperty",
                    "valueType": "xs:string",
                    "value": "integration_test_value",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_create_submodel(self, test_client: AsyncClient, sample_submodel: dict) -> None:
        """Test POST /submodels creates a Submodel."""
        response = await test_client.post("/submodels", json=sample_submodel)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == sample_submodel["id"]

    @pytest.mark.asyncio
    async def test_get_submodel(self, test_client: AsyncClient, sample_submodel: dict) -> None:
        """Test GET /submodels/{id} retrieves a Submodel."""
        await test_client.post("/submodels", json=sample_submodel)

        encoded_id = encode_id(sample_submodel["id"])
        response = await test_client.get(f"/submodels/{encoded_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_submodel["id"]
        assert len(data["submodelElements"]) == 1

    @pytest.mark.asyncio
    async def test_get_submodel_element(
        self, test_client: AsyncClient, sample_submodel: dict
    ) -> None:
        """Test GET /submodels/{id}/submodel-elements/{path} retrieves an element."""
        await test_client.post("/submodels", json=sample_submodel)

        encoded_id = encode_id(sample_submodel["id"])
        response = await test_client.get(f"/submodels/{encoded_id}/submodel-elements/TestProperty")

        assert response.status_code == 200
        data = response.json()
        assert data["idShort"] == "TestProperty"
        assert data["value"] == "integration_test_value"


class TestConditionalRequests:
    """Tests for ETag-based conditional requests."""

    @pytest.fixture
    def sample_aas(self) -> dict:
        return {
            "id": "urn:example:aas:etag-test",
            "idShort": "ETagTestAAS",
            "assetInformation": {"assetKind": "Instance"},
        }

    @pytest.mark.asyncio
    async def test_if_match_success(self, test_client: AsyncClient, sample_aas: dict) -> None:
        """Test If-Match header with correct ETag succeeds."""
        # Create and get ETag
        await test_client.post("/shells", json=sample_aas)
        encoded_id = encode_id(sample_aas["id"])

        get_response = await test_client.get(f"/shells/{encoded_id}")
        etag = get_response.headers.get("ETag")

        # Update with correct ETag
        updated = {**sample_aas, "idShort": "UpdatedWithETag"}
        response = await test_client.put(
            f"/shells/{encoded_id}",
            json=updated,
            headers={"If-Match": etag},
        )

        assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_if_match_failure(self, test_client: AsyncClient, sample_aas: dict) -> None:
        """Test If-Match header with incorrect ETag returns 412."""
        await test_client.post("/shells", json=sample_aas)
        encoded_id = encode_id(sample_aas["id"])

        # Update with wrong ETag
        updated = {**sample_aas, "idShort": "UpdatedWithWrongETag"}
        response = await test_client.put(
            f"/shells/{encoded_id}",
            json=updated,
            headers={"If-Match": '"wrong-etag"'},
        )

        assert response.status_code == 412


class TestPagination:
    """Tests for cursor-based pagination."""

    @pytest.mark.asyncio
    async def test_pagination_with_limit(self, test_client: AsyncClient) -> None:
        """Test pagination returns limited results."""
        # Create multiple AAS
        for i in range(5):
            aas = {
                "id": f"urn:example:aas:pagination-{i}",
                "idShort": f"PaginationAAS{i}",
                "assetInformation": {"assetKind": "Instance"},
            }
            await test_client.post("/shells", json=aas)

        # Request with limit
        response = await test_client.get("/shells?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]) <= 2

        # Should have paging_metadata with cursor for next page
        if len(data["result"]) == 2:
            assert "paging_metadata" in data
