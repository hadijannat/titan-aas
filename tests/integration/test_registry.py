"""Integration tests for Registry API endpoints.

Tests the AAS Registry and Submodel Registry endpoints with real database.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from titan.core.ids import encode_id_to_b64url as encode_id


class TestAasDescriptorEndpoints:
    """Tests for AAS Descriptor (Shell Descriptor) Registry endpoints."""

    @pytest.fixture
    def sample_aas_descriptor(self) -> dict:
        """Create sample AAS Descriptor payload with unique ID."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:descriptor-test-{unique_id}",
            "idShort": f"DescriptorTestAAS{unique_id}",
            "endpoints": [
                {
                    "interface": "AAS-3.0",
                    "protocolInformation": {
                        "href": "https://example.com/shells/test",
                        "endpointProtocol": "HTTPS",
                    },
                }
            ],
            "assetKind": "Instance",
            "globalAssetId": f"urn:example:asset:descriptor-test-{unique_id}",
        }

    @pytest.mark.asyncio
    async def test_create_aas_descriptor(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test POST /shell-descriptors creates an AAS descriptor."""
        response = await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        assert response.status_code in (200, 201)
        data = response.json()
        assert data["id"] == sample_aas_descriptor["id"]
        assert data["idShort"] == sample_aas_descriptor["idShort"]
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    async def test_get_aas_descriptor(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test GET /shell-descriptors/{id} retrieves an AAS descriptor."""
        # Create first
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        # Get by encoded ID
        encoded_id = encode_id(sample_aas_descriptor["id"])
        response = await test_client.get(f"/shell-descriptors/{encoded_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_aas_descriptor["id"]
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    async def test_get_aas_descriptor_not_found(self, test_client: AsyncClient) -> None:
        """Test GET /shell-descriptors/{id} returns 404 for missing descriptor."""
        encoded_id = encode_id("urn:example:aas:nonexistent")
        response = await test_client.get(f"/shell-descriptors/{encoded_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_aas_descriptors(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test GET /shell-descriptors returns list of descriptors."""
        # Create a descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        response = await test_client.get("/shell-descriptors")

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert isinstance(data["result"], list)

    @pytest.mark.asyncio
    async def test_update_aas_descriptor(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test PUT /shell-descriptors/{id} updates a descriptor."""
        # Create first
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        # Update
        updated = {**sample_aas_descriptor, "idShort": "UpdatedDescriptor"}
        encoded_id = encode_id(sample_aas_descriptor["id"])
        response = await test_client.put(f"/shell-descriptors/{encoded_id}", json=updated)

        assert response.status_code in (200, 204)

        # Verify update
        get_response = await test_client.get(f"/shell-descriptors/{encoded_id}")
        data = get_response.json()
        assert data["idShort"] == "UpdatedDescriptor"

    @pytest.mark.asyncio
    async def test_delete_aas_descriptor(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test DELETE /shell-descriptors/{id} removes a descriptor."""
        # Create first
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        # Delete
        encoded_id = encode_id(sample_aas_descriptor["id"])
        response = await test_client.delete(f"/shell-descriptors/{encoded_id}")

        assert response.status_code == 204

        # Verify deletion
        get_response = await test_client.get(f"/shell-descriptors/{encoded_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_descriptor_returns_conflict(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test POST /shell-descriptors returns 409 for duplicate ID."""
        # Create first
        response1 = await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        assert response1.status_code in (200, 201)

        # Try to create duplicate
        response2 = await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_if_match_success(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test If-Match header with correct ETag succeeds."""
        # Create and get ETag
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_id = encode_id(sample_aas_descriptor["id"])

        get_response = await test_client.get(f"/shell-descriptors/{encoded_id}")
        etag = get_response.headers.get("ETag")

        # Update with correct ETag
        updated = {**sample_aas_descriptor, "idShort": "UpdatedWithETag"}
        response = await test_client.put(
            f"/shell-descriptors/{encoded_id}",
            json=updated,
            headers={"If-Match": etag},
        )

        assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_if_match_failure(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test If-Match header with incorrect ETag returns 412."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_id = encode_id(sample_aas_descriptor["id"])

        # Update with wrong ETag
        updated = {**sample_aas_descriptor, "idShort": "UpdatedWithWrongETag"}
        response = await test_client.put(
            f"/shell-descriptors/{encoded_id}",
            json=updated,
            headers={"If-Match": '"wrong-etag"'},
        )

        assert response.status_code == 412


class TestSubmodelDescriptorEndpoints:
    """Tests for Submodel Descriptor Registry endpoints."""

    @pytest.fixture
    def sample_submodel_descriptor(self) -> dict:
        """Create sample Submodel Descriptor payload with unique ID."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:submodel:descriptor-test-{unique_id}",
            "idShort": f"SubmodelDescriptorTest{unique_id}",
            "endpoints": [
                {
                    "interface": "SUBMODEL-3.0",
                    "protocolInformation": {
                        "href": "https://example.com/submodels/test",
                        "endpointProtocol": "HTTPS",
                    },
                }
            ],
            "semanticId": {
                "type": "ExternalReference",
                "keys": [
                    {
                        "type": "GlobalReference",
                        "value": f"urn:example:semantic:{unique_id}",
                    }
                ],
            },
        }

    @pytest.mark.asyncio
    async def test_create_submodel_descriptor(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test POST /submodel-descriptors creates a descriptor."""
        response = await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)

        assert response.status_code in (200, 201)
        data = response.json()
        assert data["id"] == sample_submodel_descriptor["id"]
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    async def test_get_submodel_descriptor(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test GET /submodel-descriptors/{id} retrieves a descriptor."""
        await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)

        encoded_id = encode_id(sample_submodel_descriptor["id"])
        response = await test_client.get(f"/submodel-descriptors/{encoded_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_submodel_descriptor["id"]

    @pytest.mark.asyncio
    async def test_get_submodel_descriptor_not_found(self, test_client: AsyncClient) -> None:
        """Test GET /submodel-descriptors/{id} returns 404 for missing descriptor."""
        encoded_id = encode_id("urn:example:submodel:nonexistent")
        response = await test_client.get(f"/submodel-descriptors/{encoded_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_submodel_descriptors(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test GET /submodel-descriptors returns list of descriptors."""
        await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)

        response = await test_client.get("/submodel-descriptors")

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert isinstance(data["result"], list)

    @pytest.mark.asyncio
    async def test_update_submodel_descriptor(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test PUT /submodel-descriptors/{id} updates a descriptor."""
        await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)

        updated = {**sample_submodel_descriptor, "idShort": "UpdatedSubmodelDescriptor"}
        encoded_id = encode_id(sample_submodel_descriptor["id"])
        response = await test_client.put(f"/submodel-descriptors/{encoded_id}", json=updated)

        assert response.status_code in (200, 204)

        get_response = await test_client.get(f"/submodel-descriptors/{encoded_id}")
        data = get_response.json()
        assert data["idShort"] == "UpdatedSubmodelDescriptor"

    @pytest.mark.asyncio
    async def test_delete_submodel_descriptor(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test DELETE /submodel-descriptors/{id} removes a descriptor."""
        await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)

        encoded_id = encode_id(sample_submodel_descriptor["id"])
        response = await test_client.delete(f"/submodel-descriptors/{encoded_id}")

        assert response.status_code == 204

        get_response = await test_client.get(f"/submodel-descriptors/{encoded_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_duplicate_submodel_descriptor_returns_conflict(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test POST /submodel-descriptors returns 409 for duplicate ID."""
        response1 = await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)
        assert response1.status_code in (200, 201)

        response2 = await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)
        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_filter_by_semantic_id(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test GET /submodel-descriptors with semanticId filter."""
        # Create descriptor with semantic ID
        await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)

        # Create another descriptor without semantic ID
        unique_id = uuid4().hex[:8]
        other_descriptor = {
            "id": f"urn:example:submodel:no-semantic-{unique_id}",
            "idShort": f"NoSemanticSubmodel{unique_id}",
            "endpoints": [],
        }
        await test_client.post("/submodel-descriptors", json=other_descriptor)

        # Get the semantic ID from the fixture
        semantic_id = sample_submodel_descriptor["semanticId"]["keys"][0]["value"]

        # Filter by semantic ID
        response = await test_client.get(f"/submodel-descriptors?semantic_id={semantic_id}")

        assert response.status_code == 200
        data = response.json()
        results = data["result"]

        # Should only contain the descriptor with matching semantic ID
        ids = [r["id"] for r in results]
        assert sample_submodel_descriptor["id"] in ids


class TestRegistryPagination:
    """Tests for registry pagination."""

    @pytest.mark.asyncio
    async def test_shell_descriptors_pagination(self, test_client: AsyncClient) -> None:
        """Test /shell-descriptors pagination with limit."""
        unique_prefix = uuid4().hex[:8]
        # Create multiple descriptors
        for i in range(5):
            descriptor = {
                "id": f"urn:example:aas:pagination-{unique_prefix}-{i}",
                "idShort": f"PaginationDescriptor{unique_prefix}{i}",
                "assetKind": "Instance",
                "endpoints": [],
            }
            await test_client.post("/shell-descriptors", json=descriptor)

        # Request with limit
        response = await test_client.get("/shell-descriptors?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]) <= 2
        assert "paging_metadata" in data

    @pytest.mark.asyncio
    async def test_submodel_descriptors_pagination(self, test_client: AsyncClient) -> None:
        """Test /submodel-descriptors pagination with limit."""
        unique_prefix = uuid4().hex[:8]
        # Create multiple descriptors
        for i in range(5):
            descriptor = {
                "id": f"urn:example:submodel:pagination-{unique_prefix}-{i}",
                "idShort": f"SubmodelPagination{unique_prefix}{i}",
                "endpoints": [],
            }
            await test_client.post("/submodel-descriptors", json=descriptor)

        # Request with limit
        response = await test_client.get("/submodel-descriptors?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]) <= 2


class TestRegistryConditionalRequests:
    """Tests for ETag-based conditional requests on registry endpoints."""

    @pytest.fixture
    def sample_descriptor(self) -> dict:
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:conditional-test-{unique_id}",
            "idShort": f"ConditionalTestDescriptor{unique_id}",
            "assetKind": "Instance",
            "endpoints": [],
        }

    @pytest.mark.asyncio
    async def test_if_none_match_returns_304(
        self, test_client: AsyncClient, sample_descriptor: dict
    ) -> None:
        """Test If-None-Match header returns 304 when ETag matches."""
        await test_client.post("/shell-descriptors", json=sample_descriptor)
        encoded_id = encode_id(sample_descriptor["id"])

        # Get ETag
        get_response = await test_client.get(f"/shell-descriptors/{encoded_id}")
        etag = get_response.headers.get("ETag")

        # Request with matching If-None-Match
        response = await test_client.get(
            f"/shell-descriptors/{encoded_id}",
            headers={"If-None-Match": etag},
        )

        assert response.status_code == 304

    @pytest.mark.asyncio
    async def test_if_none_match_returns_200(
        self, test_client: AsyncClient, sample_descriptor: dict
    ) -> None:
        """Test If-None-Match header returns 200 when ETag doesn't match."""
        await test_client.post("/shell-descriptors", json=sample_descriptor)
        encoded_id = encode_id(sample_descriptor["id"])

        # Request with non-matching If-None-Match
        response = await test_client.get(
            f"/shell-descriptors/{encoded_id}",
            headers={"If-None-Match": '"different-etag"'},
        )

        assert response.status_code == 200


class TestNestedSubmodelDescriptorEndpoints:
    """Tests for nested Submodel Descriptor endpoints under AAS Descriptors (SSP-001)."""

    @pytest.fixture
    def sample_aas_descriptor(self) -> dict:
        """Create sample AAS Descriptor payload with unique ID."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:nested-test-{unique_id}",
            "idShort": f"NestedTestAAS{unique_id}",
            "endpoints": [
                {
                    "interface": "AAS-3.0",
                    "protocolInformation": {
                        "href": "https://example.com/shells/test",
                        "endpointProtocol": "HTTPS",
                    },
                }
            ],
            "assetKind": "Instance",
            "globalAssetId": f"urn:example:asset:nested-test-{unique_id}",
        }

    @pytest.fixture
    def sample_submodel_descriptor(self) -> dict:
        """Create sample Submodel Descriptor payload with unique ID."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:submodel:nested-test-{unique_id}",
            "idShort": f"NestedSubmodelTest{unique_id}",
            "endpoints": [
                {
                    "interface": "SUBMODEL-3.0",
                    "protocolInformation": {
                        "href": "https://example.com/submodels/test",
                        "endpointProtocol": "HTTPS",
                    },
                }
            ],
        }

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-LIST-001")
    async def test_get_nested_submodel_descriptors(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test GET /shell-descriptors/{id}/submodel-descriptors lists submodels."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Get nested submodel descriptors (should be empty)
        response = await test_client.get(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors"
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert isinstance(data["result"], list)
        assert len(data["result"]) == 0

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-POST-001")
    async def test_post_nested_submodel_descriptor(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test POST /shell-descriptors/{id}/submodel-descriptors adds submodel."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Add nested submodel descriptor
        response = await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == sample_submodel_descriptor["id"]
        assert "ETag" in response.headers

        # Verify it's in the list
        list_response = await test_client.get(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors"
        )
        list_data = list_response.json()
        assert len(list_data["result"]) == 1
        assert list_data["result"][0]["id"] == sample_submodel_descriptor["id"]

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-POST-002")
    async def test_post_duplicate_nested_submodel_returns_conflict(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test POST duplicate nested submodel returns 409 Conflict."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Add nested submodel descriptor
        await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        # Try to add duplicate
        response = await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-GET-001")
    async def test_get_nested_submodel_descriptor_by_id(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test GET /shell-descriptors/{id}/submodel-descriptors/{smId} retrieves one."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Add nested submodel descriptor
        await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        # Get specific nested submodel descriptor
        encoded_sm_id = encode_id(sample_submodel_descriptor["id"])
        response = await test_client.get(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_submodel_descriptor["id"]
        assert "ETag" in response.headers

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-GET-002")
    async def test_get_nested_submodel_descriptor_not_found(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test GET nested submodel returns 404 when not found."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Try to get non-existent submodel descriptor
        encoded_sm_id = encode_id("urn:example:submodel:nonexistent")
        response = await test_client.get(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-PUT-001")
    async def test_update_nested_submodel_descriptor(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test PUT /shell-descriptors/{id}/submodel-descriptors/{smId} updates."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Add nested submodel descriptor
        await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        # Update the submodel descriptor
        updated = {**sample_submodel_descriptor, "idShort": "UpdatedNestedSubmodel"}
        encoded_sm_id = encode_id(sample_submodel_descriptor["id"])
        response = await test_client.put(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}",
            json=updated,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["idShort"] == "UpdatedNestedSubmodel"

        # Verify update persisted
        get_response = await test_client.get(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}"
        )
        get_data = get_response.json()
        assert get_data["idShort"] == "UpdatedNestedSubmodel"

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-PUT-002")
    async def test_update_nested_submodel_aas_not_found(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """Test PUT nested submodel returns 404 if AAS doesn't exist."""
        encoded_aas_id = encode_id("urn:example:aas:nonexistent")
        encoded_sm_id = encode_id(sample_submodel_descriptor["id"])

        response = await test_client.put(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}",
            json=sample_submodel_descriptor,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-PUT-003")
    async def test_update_nested_submodel_not_linked(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test PUT nested submodel returns 404 if submodel not linked to AAS."""
        # Create AAS descriptor (without the submodel)
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])
        encoded_sm_id = encode_id(sample_submodel_descriptor["id"])

        # Try to update non-existent nested submodel
        response = await test_client.put(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}",
            json=sample_submodel_descriptor,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-PUT-004")
    async def test_update_nested_submodel_if_match(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test PUT with If-Match header for optimistic concurrency."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Add nested submodel descriptor
        await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        # Get ETag
        encoded_sm_id = encode_id(sample_submodel_descriptor["id"])
        get_response = await test_client.get(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}"
        )
        etag = get_response.headers.get("ETag")

        # Update with correct ETag
        updated = {**sample_submodel_descriptor, "idShort": "UpdatedWithETag"}
        response = await test_client.put(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}",
            json=updated,
            headers={"If-Match": etag},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-PUT-005")
    async def test_update_nested_submodel_if_match_failure(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test PUT with incorrect If-Match returns 412 Precondition Failed."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Add nested submodel descriptor
        await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        # Update with wrong ETag
        encoded_sm_id = encode_id(sample_submodel_descriptor["id"])
        updated = {**sample_submodel_descriptor, "idShort": "WrongETagUpdate"}
        response = await test_client.put(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}",
            json=updated,
            headers={"If-Match": '"wrong-etag"'},
        )

        assert response.status_code == 412

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-DELETE-001")
    async def test_delete_nested_submodel_descriptor(
        self,
        test_client: AsyncClient,
        sample_aas_descriptor: dict,
        sample_submodel_descriptor: dict,
    ) -> None:
        """Test DELETE /shell-descriptors/{id}/submodel-descriptors/{smId} removes."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Add nested submodel descriptor
        await test_client.post(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors",
            json=sample_submodel_descriptor,
        )

        # Delete the nested submodel descriptor
        encoded_sm_id = encode_id(sample_submodel_descriptor["id"])
        response = await test_client.delete(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}"
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = await test_client.get(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}"
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-REG-NESTED-DELETE-002")
    async def test_delete_nested_submodel_not_found(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """Test DELETE nested submodel returns 404 when not found."""
        # Create AAS descriptor
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])

        # Try to delete non-existent submodel descriptor
        encoded_sm_id = encode_id("urn:example:submodel:nonexistent")
        response = await test_client.delete(
            f"/shell-descriptors/{encoded_aas_id}/submodel-descriptors/{encoded_sm_id}"
        )

        assert response.status_code == 404
