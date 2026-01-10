"""Integration tests for Concept Description Repository endpoints."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from titan.core.ids import encode_id_to_b64url as encode_id


class TestConceptDescriptionEndpoints:
    """Tests for Concept Description Repository endpoints."""

    @pytest.fixture
    def sample_concept_description(self) -> dict:
        """Create sample ConceptDescription payload with unique ID."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:cd:test-{unique_id}",
            "idShort": f"ConceptDesc{unique_id}",
            "category": "PROPERTY",
        }

    @pytest.mark.asyncio
    async def test_create_concept_description(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test POST /concept-descriptions creates a ConceptDescription."""
        response = await test_client.post("/concept-descriptions", json=sample_concept_description)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == sample_concept_description["id"]
        assert data["idShort"] == sample_concept_description["idShort"]
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    async def test_get_concept_description(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test GET /concept-descriptions/{id} retrieves a ConceptDescription."""
        await test_client.post("/concept-descriptions", json=sample_concept_description)

        encoded_id = encode_id(sample_concept_description["id"])
        response = await test_client.get(f"/concept-descriptions/{encoded_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_concept_description["id"]
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    async def test_get_concept_description_not_found(self, test_client: AsyncClient) -> None:
        """Test GET /concept-descriptions/{id} returns 404 for missing ConceptDescription."""
        encoded_id = encode_id("urn:example:cd:nonexistent")
        response = await test_client.get(f"/concept-descriptions/{encoded_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_concept_descriptions(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test GET /concept-descriptions returns list of ConceptDescriptions."""
        await test_client.post("/concept-descriptions", json=sample_concept_description)

        response = await test_client.get("/concept-descriptions")

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert isinstance(data["result"], list)

    @pytest.mark.asyncio
    async def test_update_concept_description(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test PUT /concept-descriptions/{id} updates a ConceptDescription."""
        await test_client.post("/concept-descriptions", json=sample_concept_description)

        updated = {**sample_concept_description, "idShort": "UpdatedConceptDesc"}
        encoded_id = encode_id(sample_concept_description["id"])
        response = await test_client.put(f"/concept-descriptions/{encoded_id}", json=updated)

        assert response.status_code in (200, 204)

        get_response = await test_client.get(f"/concept-descriptions/{encoded_id}")
        data = get_response.json()
        assert data["idShort"] == "UpdatedConceptDesc"

    @pytest.mark.asyncio
    async def test_delete_concept_description(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test DELETE /concept-descriptions/{id} removes a ConceptDescription."""
        await test_client.post("/concept-descriptions", json=sample_concept_description)

        encoded_id = encode_id(sample_concept_description["id"])
        response = await test_client.delete(f"/concept-descriptions/{encoded_id}")

        assert response.status_code == 204

        get_response = await test_client.get(f"/concept-descriptions/{encoded_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_concept_description_returns_conflict(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test POST /concept-descriptions returns 409 for duplicate ID."""
        response1 = await test_client.post("/concept-descriptions", json=sample_concept_description)
        assert response1.status_code == 201

        response2 = await test_client.post("/concept-descriptions", json=sample_concept_description)
        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_if_none_match_returns_304(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test If-None-Match header returns 304 when ETag matches."""
        await test_client.post("/concept-descriptions", json=sample_concept_description)
        encoded_id = encode_id(sample_concept_description["id"])

        get_response = await test_client.get(f"/concept-descriptions/{encoded_id}")
        etag = get_response.headers.get("ETag")

        response = await test_client.get(
            f"/concept-descriptions/{encoded_id}",
            headers={"If-None-Match": etag},
        )

        assert response.status_code == 304

    @pytest.mark.asyncio
    async def test_if_match_success(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test If-Match header with correct ETag succeeds."""
        await test_client.post("/concept-descriptions", json=sample_concept_description)
        encoded_id = encode_id(sample_concept_description["id"])

        get_response = await test_client.get(f"/concept-descriptions/{encoded_id}")
        etag = get_response.headers.get("ETag")

        updated = {**sample_concept_description, "idShort": "UpdatedWithETag"}
        response = await test_client.put(
            f"/concept-descriptions/{encoded_id}",
            json=updated,
            headers={"If-Match": etag},
        )

        assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_if_match_failure(
        self, test_client: AsyncClient, sample_concept_description: dict
    ) -> None:
        """Test If-Match header with incorrect ETag returns 412."""
        await test_client.post("/concept-descriptions", json=sample_concept_description)
        encoded_id = encode_id(sample_concept_description["id"])

        updated = {**sample_concept_description, "idShort": "UpdatedWithWrongETag"}
        response = await test_client.put(
            f"/concept-descriptions/{encoded_id}",
            json=updated,
            headers={"If-Match": '"wrong-etag"'},
        )

        assert response.status_code == 412
