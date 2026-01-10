"""Integration tests for SubmodelElement CRUD endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from titan.core.ids import encode_id_to_b64url as encode_id

# Skip if testcontainers not available
pytest.importorskip("testcontainers")


class TestSubmodelElementCrud:
    """CRUD tests for SubmodelElement endpoints."""

    @pytest.fixture
    def base_submodel(self) -> dict:
        return {
            "id": "urn:example:submodel:elements",
            "idShort": "ElementSubmodel",
            "submodelElements": [],
        }

    @pytest.mark.asyncio
    async def test_create_root_element(self, test_client: AsyncClient, base_submodel: dict) -> None:
        """POST /submodels/{id}/submodel-elements creates root element."""
        await test_client.post("/submodels", json=base_submodel)
        encoded_id = encode_id(base_submodel["id"])

        element = {
            "modelType": "Property",
            "idShort": "Pressure",
            "valueType": "xs:string",
            "value": "1",
        }

        response = await test_client.post(
            f"/submodels/{encoded_id}/submodel-elements",
            json=element,
        )

        assert response.status_code == 201
        assert "Location" in response.headers

        get_response = await test_client.get(
            f"/submodels/{encoded_id}/submodel-elements/Pressure"
        )
        assert get_response.status_code == 200
        body = get_response.json()
        assert body["idShort"] == "Pressure"
        assert body["value"] == "1"

    @pytest.mark.asyncio
    async def test_create_nested_element(self, test_client: AsyncClient) -> None:
        """POST /submodels/{id}/submodel-elements/{path} creates nested element."""
        submodel = {
            "id": "urn:example:submodel:collection",
            "idShort": "CollectionSubmodel",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementCollection",
                    "idShort": "Collection",
                    "value": [],
                }
            ],
        }
        await test_client.post("/submodels", json=submodel)
        encoded_id = encode_id(submodel["id"])

        element = {
            "modelType": "Property",
            "idShort": "Nested",
            "valueType": "xs:string",
            "value": "nested",
        }

        response = await test_client.post(
            f"/submodels/{encoded_id}/submodel-elements/Collection",
            json=element,
        )

        assert response.status_code == 201
        location = response.headers.get("Location")
        assert location is not None
        assert location.endswith("Collection.Nested")

        get_response = await test_client.get(
            f"/submodels/{encoded_id}/submodel-elements/Collection.Nested"
        )
        assert get_response.status_code == 200
        body = get_response.json()
        assert body["idShort"] == "Nested"
        assert body["value"] == "nested"

    @pytest.mark.asyncio
    async def test_create_list_element_with_index(self, test_client: AsyncClient) -> None:
        """POST into SubmodelElementList returns indexed path."""
        submodel = {
            "id": "urn:example:submodel:list",
            "idShort": "ListSubmodel",
            "submodelElements": [
                {
                    "modelType": "SubmodelElementList",
                    "idShort": "Measurements",
                    "orderRelevant": True,
                    "typeValueListElement": "Property",
                    "valueTypeListElement": "xs:string",
                    "value": [],
                }
            ],
        }
        await test_client.post("/submodels", json=submodel)
        encoded_id = encode_id(submodel["id"])

        element = {
            "modelType": "Property",
            "valueType": "xs:string",
            "value": "10",
        }

        response = await test_client.post(
            f"/submodels/{encoded_id}/submodel-elements/Measurements",
            json=element,
        )

        assert response.status_code == 201
        location = response.headers.get("Location")
        assert location is not None
        assert location.endswith("Measurements[0]")

        get_response = await test_client.get(
            f"/submodels/{encoded_id}/submodel-elements/Measurements[0]"
        )
        assert get_response.status_code == 200
        body = get_response.json()
        assert body["value"] == "10"

    @pytest.mark.asyncio
    async def test_update_patch_delete_element(self, test_client: AsyncClient) -> None:
        """PUT, PATCH, PATCH $value, and DELETE work for elements."""
        submodel = {
            "id": "urn:example:submodel:update",
            "idShort": "UpdateSubmodel",
            "submodelElements": [
                {
                    "modelType": "Property",
                    "idShort": "Target",
                    "valueType": "xs:string",
                    "value": "old",
                }
            ],
        }
        await test_client.post("/submodels", json=submodel)
        encoded_id = encode_id(submodel["id"])

        # Replace
        replacement = {
            "modelType": "Property",
            "idShort": "Target",
            "valueType": "xs:string",
            "value": "replaced",
        }
        response = await test_client.put(
            f"/submodels/{encoded_id}/submodel-elements/Target",
            json=replacement,
        )
        assert response.status_code == 200

        # Patch element
        patch_response = await test_client.patch(
            f"/submodels/{encoded_id}/submodel-elements/Target",
            json={"value": "patched"},
        )
        assert patch_response.status_code == 200

        # Patch only value
        value_response = await test_client.patch(
            f"/submodels/{encoded_id}/submodel-elements/Target/$value",
            json="value-only",
        )
        assert value_response.status_code == 200

        get_response = await test_client.get(
            f"/submodels/{encoded_id}/submodel-elements/Target"
        )
        assert get_response.status_code == 200
        assert get_response.json()["value"] == "value-only"

        # Delete
        delete_response = await test_client.delete(
            f"/submodels/{encoded_id}/submodel-elements/Target"
        )
        assert delete_response.status_code == 204

        missing_response = await test_client.get(
            f"/submodels/{encoded_id}/submodel-elements/Target"
        )
        assert missing_response.status_code == 404
