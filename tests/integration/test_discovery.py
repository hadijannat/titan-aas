"""Integration tests for Discovery API endpoints.

Tests the Discovery Service endpoints per IDTA-01002 Part 2 v3.1.1:
- SSP-002 (READ Profile): Lookup operations
- SSP-001 (FULL Profile): Create/Delete asset links

Covers positive cases, negative cases, and integration scenarios.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from titan.core.ids import encode_id_to_b64url as encode_id


class TestDiscoveryLookupByAssetLink:
    """Tests for POST /lookup/shellsByAssetLink (SSP-002 READ Profile)."""

    @pytest.fixture
    def sample_aas_descriptor(self) -> dict:
        """Create sample AAS Descriptor with asset information."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:discovery-test-{unique_id}",
            "idShort": f"DiscoveryTestAAS{unique_id}",
            "endpoints": [
                {
                    "interface": "AAS-3.0",
                    "protocolInformation": {
                        "href": f"https://example.com/shells/{unique_id}",
                        "endpointProtocol": "HTTPS",
                    },
                }
            ],
            "assetKind": "Instance",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"urn:example:asset:global-{unique_id}",
                "specificAssetIds": [
                    {"name": "serialNumber", "value": f"SN-{unique_id}"},
                    {"name": "batchNumber", "value": f"BATCH-{unique_id}"},
                ],
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-LOOKUP-001")
    async def test_lookup_shells_by_global_asset_id(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """POST /lookup/shellsByAssetLink finds AAS by globalAssetId."""
        # Create descriptor first
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        # Lookup by global asset ID (per AASd-116)
        global_asset_id = sample_aas_descriptor["assetInformation"]["globalAssetId"]
        asset_links = [{"name": "globalAssetId", "value": global_asset_id}]

        response = await test_client.post("/lookup/shellsByAssetLink", json=asset_links)

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert isinstance(data["result"], list)
        assert len(data["result"]) >= 1

        # Result should contain Base64URL-encoded AAS ID
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])
        assert encoded_aas_id in data["result"]

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-LOOKUP-002")
    async def test_lookup_shells_by_specific_asset_id(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """POST /lookup/shellsByAssetLink finds AAS by specificAssetId."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        # Lookup by specific asset ID
        serial_number = sample_aas_descriptor["assetInformation"]["specificAssetIds"][0]["value"]
        asset_links = [{"name": "serialNumber", "value": serial_number}]

        response = await test_client.post("/lookup/shellsByAssetLink", json=asset_links)

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])
        assert encoded_aas_id in data["result"]

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-LOOKUP-003")
    async def test_lookup_shells_multiple_asset_links(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """POST /lookup/shellsByAssetLink with multiple asset links."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        # Lookup with multiple asset links
        asset_links = [
            {
                "name": "globalAssetId",
                "value": sample_aas_descriptor["assetInformation"]["globalAssetId"],
            },
            {"name": "serialNumber", "value": "SN-nonexistent"},
        ]

        response = await test_client.post("/lookup/shellsByAssetLink", json=asset_links)

        assert response.status_code == 200
        data = response.json()
        # Should find AAS by globalAssetId even though serialNumber doesn't match
        encoded_aas_id = encode_id(sample_aas_descriptor["id"])
        assert encoded_aas_id in data["result"]

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-LOOKUP-004")
    async def test_lookup_shells_no_match_returns_empty(self, test_client: AsyncClient) -> None:
        """POST /lookup/shellsByAssetLink returns empty for non-existent asset."""
        asset_links = [{"name": "globalAssetId", "value": "urn:nonexistent:asset:xyz"}]

        response = await test_client.post("/lookup/shellsByAssetLink", json=asset_links)

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == []

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-LOOKUP-005")
    async def test_lookup_shells_empty_array(self, test_client: AsyncClient) -> None:
        """POST /lookup/shellsByAssetLink with empty array returns empty result."""
        response = await test_client.post("/lookup/shellsByAssetLink", json=[])

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == []


class TestDiscoveryGetAssetLinks:
    """Tests for GET /lookup/shells/{aasIdentifier} (SSP-002 READ Profile)."""

    @pytest.fixture
    def sample_aas_descriptor(self) -> dict:
        """Create sample AAS Descriptor with asset information."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:get-links-{unique_id}",
            "idShort": f"GetLinksAAS{unique_id}",
            "endpoints": [],
            "assetKind": "Instance",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"urn:example:asset:getlinks-{unique_id}",
                "specificAssetIds": [
                    {"name": "serialNumber", "value": f"SN-GETLINKS-{unique_id}"},
                ],
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-GETLINKS-001")
    async def test_get_asset_links_returns_all_links(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """GET /lookup/shells/{id} returns globalAssetId and specificAssetIds."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        encoded_id = encode_id(sample_aas_descriptor["id"])
        response = await test_client.get(f"/lookup/shells/{encoded_id}")

        assert response.status_code == 200
        data = response.json()

        # Should contain globalAssetId as name="globalAssetId"
        global_asset_link = next((link for link in data if link["name"] == "globalAssetId"), None)
        assert global_asset_link is not None
        expected_global_id = sample_aas_descriptor["assetInformation"]["globalAssetId"]
        assert global_asset_link["value"] == expected_global_id

        # Should contain specificAssetIds
        serial_link = next((link for link in data if link["name"] == "serialNumber"), None)
        assert serial_link is not None
        expected_serial = sample_aas_descriptor["assetInformation"]["specificAssetIds"][0]["value"]
        assert serial_link["value"] == expected_serial

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-GETLINKS-002")
    async def test_get_asset_links_not_found(self, test_client: AsyncClient) -> None:
        """GET /lookup/shells/{id} returns 404 for non-existent AAS."""
        encoded_id = encode_id("urn:example:aas:nonexistent-discovery")
        response = await test_client.get(f"/lookup/shells/{encoded_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-GETLINKS-003")
    async def test_get_asset_links_invalid_base64url(self, test_client: AsyncClient) -> None:
        """GET /lookup/shells/{id} returns 400 for invalid Base64URL."""
        response = await test_client.get("/lookup/shells/!!!invalid-base64!!!")

        assert response.status_code == 400


class TestDiscoveryPostAssetLinks:
    """Tests for POST /lookup/shells/{aasIdentifier} (SSP-001 FULL Profile)."""

    @pytest.fixture
    def sample_aas_descriptor(self) -> dict:
        """Create sample AAS Descriptor."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:post-links-{unique_id}",
            "idShort": f"PostLinksAAS{unique_id}",
            "endpoints": [],
            "assetKind": "Instance",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"urn:example:asset:original-{unique_id}",
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-POSTLINKS-001")
    async def test_post_asset_links_creates_links(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """POST /lookup/shells/{id} creates new asset links."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        encoded_id = encode_id(sample_aas_descriptor["id"])

        # Set new asset links
        new_links = [
            {"name": "globalAssetId", "value": "urn:example:asset:new-global"},
            {"name": "serialNumber", "value": "NEW-SERIAL-123"},
            {"name": "batchNumber", "value": "NEW-BATCH-456"},
        ]

        response = await test_client.post(f"/lookup/shells/{encoded_id}", json=new_links)

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 3

        # Verify links were set by retrieving them
        get_response = await test_client.get(f"/lookup/shells/{encoded_id}")
        assert get_response.status_code == 200
        get_data = get_response.json()

        # Check globalAssetId was updated
        global_link = next((lnk for lnk in get_data if lnk["name"] == "globalAssetId"), None)
        assert global_link is not None
        assert global_link["value"] == "urn:example:asset:new-global"

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-POSTLINKS-002")
    async def test_post_asset_links_replaces_existing(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """POST /lookup/shells/{id} replaces existing links."""
        # Create with initial links
        sample_aas_descriptor["assetInformation"]["specificAssetIds"] = [
            {"name": "oldKey", "value": "oldValue"},
        ]
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        encoded_id = encode_id(sample_aas_descriptor["id"])

        # Replace with new links (no oldKey)
        new_links = [
            {"name": "globalAssetId", "value": "urn:new:asset"},
            {"name": "newKey", "value": "newValue"},
        ]

        response = await test_client.post(f"/lookup/shells/{encoded_id}", json=new_links)
        assert response.status_code == 201

        # Verify old links are gone
        get_response = await test_client.get(f"/lookup/shells/{encoded_id}")
        get_data = get_response.json()

        link_names = [lnk["name"] for lnk in get_data]
        assert "oldKey" not in link_names
        assert "newKey" in link_names

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-POSTLINKS-003")
    async def test_post_asset_links_not_found(self, test_client: AsyncClient) -> None:
        """POST /lookup/shells/{id} returns 404 for non-existent AAS."""
        encoded_id = encode_id("urn:example:aas:nonexistent-post")
        new_links = [{"name": "key", "value": "value"}]

        response = await test_client.post(f"/lookup/shells/{encoded_id}", json=new_links)

        assert response.status_code == 404


class TestDiscoveryDeleteAssetLinks:
    """Tests for DELETE /lookup/shells/{aasIdentifier} (SSP-001 FULL Profile)."""

    @pytest.fixture
    def sample_aas_descriptor(self) -> dict:
        """Create sample AAS Descriptor with asset information."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:delete-links-{unique_id}",
            "idShort": f"DeleteLinksAAS{unique_id}",
            "endpoints": [],
            "assetKind": "Instance",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"urn:example:asset:deletable-{unique_id}",
                "specificAssetIds": [
                    {"name": "serialNumber", "value": f"SN-DELETE-{unique_id}"},
                ],
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-DELETE-001")
    async def test_delete_asset_links(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """DELETE /lookup/shells/{id} removes all asset links."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        encoded_id = encode_id(sample_aas_descriptor["id"])

        # Delete asset links
        response = await test_client.delete(f"/lookup/shells/{encoded_id}")

        assert response.status_code == 204

        # Verify links are cleared
        get_response = await test_client.get(f"/lookup/shells/{encoded_id}")
        assert get_response.status_code == 200
        get_data = get_response.json()

        # globalAssetId should be cleared (no globalAssetId link)
        global_link = next((lnk for lnk in get_data if lnk["name"] == "globalAssetId"), None)
        assert global_link is None or global_link["value"] is None

        # specificAssetIds should be empty
        non_global_links = [lnk for lnk in get_data if lnk["name"] != "globalAssetId"]
        assert len(non_global_links) == 0

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-DELETE-002")
    async def test_delete_asset_links_not_found(self, test_client: AsyncClient) -> None:
        """DELETE /lookup/shells/{id} returns 404 for non-existent AAS."""
        encoded_id = encode_id("urn:example:aas:nonexistent-delete")
        response = await test_client.delete(f"/lookup/shells/{encoded_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-DELETE-003")
    async def test_delete_asset_links_makes_undiscoverable(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """DELETE /lookup/shells/{id} makes AAS undiscoverable by asset ID."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        encoded_id = encode_id(sample_aas_descriptor["id"])
        global_asset_id = sample_aas_descriptor["assetInformation"]["globalAssetId"]

        # Verify discoverable before delete
        lookup_response = await test_client.post(
            "/lookup/shellsByAssetLink",
            json=[{"name": "globalAssetId", "value": global_asset_id}],
        )
        assert encoded_id in lookup_response.json()["result"]

        # Delete asset links
        await test_client.delete(f"/lookup/shells/{encoded_id}")

        # Verify no longer discoverable
        lookup_response = await test_client.post(
            "/lookup/shellsByAssetLink",
            json=[{"name": "globalAssetId", "value": global_asset_id}],
        )
        assert encoded_id not in lookup_response.json()["result"]


class TestDiscoveryLegacyLookup:
    """Tests for GET /lookup/shells (deprecated legacy endpoint)."""

    @pytest.fixture
    def sample_aas_descriptor(self) -> dict:
        """Create sample AAS Descriptor."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:aas:legacy-lookup-{unique_id}",
            "idShort": f"LegacyLookupAAS{unique_id}",
            "endpoints": [],
            "assetKind": "Instance",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"urn:example:asset:legacy-{unique_id}",
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-LEGACY-001")
    async def test_lookup_shells_get_returns_all_ids(
        self, test_client: AsyncClient, sample_aas_descriptor: dict
    ) -> None:
        """GET /lookup/shells returns all AAS identifiers when no filter."""
        await test_client.post("/shell-descriptors", json=sample_aas_descriptor)

        response = await test_client.get("/lookup/shells")

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert isinstance(data["result"], list)

        encoded_id = encode_id(sample_aas_descriptor["id"])
        assert encoded_id in data["result"]

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-LEGACY-002")
    async def test_lookup_shells_get_with_limit(self, test_client: AsyncClient) -> None:
        """GET /lookup/shells respects limit parameter."""
        # Create multiple descriptors
        unique_prefix = uuid4().hex[:8]
        for i in range(5):
            descriptor = {
                "id": f"urn:example:aas:limit-test-{unique_prefix}-{i}",
                "idShort": f"LimitTest{unique_prefix}{i}",
                "endpoints": [],
                "assetKind": "Instance",
            }
            await test_client.post("/shell-descriptors", json=descriptor)

        response = await test_client.get("/lookup/shells?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["result"]) <= 2


class TestDiscoverySubmodelLookup:
    """Tests for GET /lookup/submodels."""

    @pytest.fixture
    def sample_submodel_descriptor(self) -> dict:
        """Create sample Submodel Descriptor with semantic ID."""
        unique_id = uuid4().hex[:8]
        return {
            "id": f"urn:example:submodel:sm-lookup-{unique_id}",
            "idShort": f"SubmodelLookup{unique_id}",
            "endpoints": [],
            "semanticId": {
                "type": "ExternalReference",
                "keys": [
                    {
                        "type": "GlobalReference",
                        "value": f"urn:example:semantic:lookup-{unique_id}",
                    }
                ],
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-SM-001")
    async def test_lookup_submodels_returns_all(
        self, test_client: AsyncClient, sample_submodel_descriptor: dict
    ) -> None:
        """GET /lookup/submodels returns all Submodel identifiers."""
        await test_client.post("/submodel-descriptors", json=sample_submodel_descriptor)

        response = await test_client.get("/lookup/submodels")

        assert response.status_code == 200
        data = response.json()
        assert "result" in data

        encoded_id = encode_id(sample_submodel_descriptor["id"])
        assert encoded_id in data["result"]


class TestDiscoveryIntegrationWorkflow:
    """End-to-end integration tests for discovery workflows."""

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-E2E-001")
    async def test_full_discovery_workflow(self, test_client: AsyncClient) -> None:
        """Complete workflow: create, discover, update, delete asset links."""
        unique_id = uuid4().hex[:8]

        # Step 1: Create AAS descriptor
        descriptor = {
            "id": f"urn:example:aas:workflow-{unique_id}",
            "idShort": f"WorkflowAAS{unique_id}",
            "endpoints": [],
            "assetKind": "Instance",
            "assetInformation": {
                "assetKind": "Instance",
                "globalAssetId": f"urn:example:asset:workflow-{unique_id}",
                "specificAssetIds": [
                    {"name": "partNumber", "value": f"PN-{unique_id}"},
                ],
            },
        }
        await test_client.post("/shell-descriptors", json=descriptor)

        encoded_id = encode_id(descriptor["id"])

        # Step 2: Discover by globalAssetId
        global_id = descriptor["assetInformation"]["globalAssetId"]
        lookup_response = await test_client.post(
            "/lookup/shellsByAssetLink",
            json=[{"name": "globalAssetId", "value": global_id}],
        )
        assert lookup_response.status_code == 200
        assert encoded_id in lookup_response.json()["result"]

        # Step 3: Get current asset links
        get_response = await test_client.get(f"/lookup/shells/{encoded_id}")
        assert get_response.status_code == 200
        links = get_response.json()
        assert any(lnk["name"] == "globalAssetId" for lnk in links)
        assert any(lnk["name"] == "partNumber" for lnk in links)

        # Step 4: Update asset links
        new_links = [
            {"name": "globalAssetId", "value": f"urn:example:asset:updated-{unique_id}"},
            {"name": "serialNumber", "value": f"SN-UPDATED-{unique_id}"},
        ]
        post_response = await test_client.post(f"/lookup/shells/{encoded_id}", json=new_links)
        assert post_response.status_code == 201

        # Step 5: Verify old asset ID no longer finds it
        old_lookup = await test_client.post(
            "/lookup/shellsByAssetLink",
            json=[{"name": "globalAssetId", "value": global_id}],
        )
        assert encoded_id not in old_lookup.json()["result"]

        # Step 6: Verify new asset ID finds it
        new_lookup = await test_client.post(
            "/lookup/shellsByAssetLink",
            json=[{"name": "globalAssetId", "value": f"urn:example:asset:updated-{unique_id}"}],
        )
        assert encoded_id in new_lookup.json()["result"]

        # Step 7: Delete asset links
        delete_response = await test_client.delete(f"/lookup/shells/{encoded_id}")
        assert delete_response.status_code == 204

        # Step 8: Verify no longer discoverable
        final_lookup = await test_client.post(
            "/lookup/shellsByAssetLink",
            json=[{"name": "globalAssetId", "value": f"urn:example:asset:updated-{unique_id}"}],
        )
        assert encoded_id not in final_lookup.json()["result"]

    @pytest.mark.asyncio
    @pytest.mark.ssp("SSP-DISC-E2E-002")
    async def test_multiple_aas_same_asset(self, test_client: AsyncClient) -> None:
        """Multiple AAS can reference the same asset identifier."""
        unique_id = uuid4().hex[:8]
        shared_asset = f"urn:example:asset:shared-{unique_id}"

        # Create two descriptors referencing same asset
        for i in range(2):
            descriptor = {
                "id": f"urn:example:aas:shared-{unique_id}-{i}",
                "idShort": f"SharedAAS{unique_id}{i}",
                "endpoints": [],
                "assetKind": "Instance",
                "assetInformation": {
                    "assetKind": "Instance",
                    "globalAssetId": shared_asset,
                },
            }
            await test_client.post("/shell-descriptors", json=descriptor)

        # Lookup should find both
        lookup_response = await test_client.post(
            "/lookup/shellsByAssetLink",
            json=[{"name": "globalAssetId", "value": shared_asset}],
        )
        assert lookup_response.status_code == 200
        results = lookup_response.json()["result"]

        encoded_id_0 = encode_id(f"urn:example:aas:shared-{unique_id}-0")
        encoded_id_1 = encode_id(f"urn:example:aas:shared-{unique_id}-1")

        assert encoded_id_0 in results
        assert encoded_id_1 in results
