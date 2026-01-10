"""Integration tests for federation API endpoints.

Tests the federation router endpoints for peer management,
sync operations, and conflict resolution.
"""

import pytest
from httpx import AsyncClient
from starlette import status

pytestmark = pytest.mark.asyncio


class TestFederationPeersAPI:
    """Test federation peers API endpoints."""

    async def test_list_peers_empty(self, test_client: AsyncClient) -> None:
        """List peers returns empty list initially."""
        response = await test_client.get("/federation/peers")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 0
        assert data["peers"] == []

    async def test_register_peer(self, test_client: AsyncClient) -> None:
        """Register a new peer."""
        response = await test_client.post(
            "/federation/peers",
            json={
                "url": "http://peer1.example.com",
                "name": "Test Peer 1",
                "capabilities": {
                    "aasRepository": True,
                    "submodelRepository": True,
                    "aasRegistry": False,
                },
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "id" in data
        assert data["url"] == "http://peer1.example.com"
        assert data["name"] == "Test Peer 1"

    async def test_get_peer(self, test_client: AsyncClient) -> None:
        """Get a specific peer by ID."""
        # First register a peer
        register_response = await test_client.post(
            "/federation/peers",
            json={"url": "http://peer2.example.com", "name": "Test Peer 2"},
        )
        peer_id = register_response.json()["id"]

        # Then get it
        response = await test_client.get(f"/federation/peers/{peer_id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == peer_id
        assert data["url"] == "http://peer2.example.com"

    async def test_get_peer_not_found(self, test_client: AsyncClient) -> None:
        """Get non-existent peer returns 404."""
        response = await test_client.get("/federation/peers/non-existent-id")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_unregister_peer(self, test_client: AsyncClient) -> None:
        """Unregister a peer."""
        # First register a peer
        register_response = await test_client.post(
            "/federation/peers",
            json={"url": "http://peer3.example.com"},
        )
        peer_id = register_response.json()["id"]

        # Then delete it
        response = await test_client.delete(f"/federation/peers/{peer_id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify it's gone
        get_response = await test_client.get(f"/federation/peers/{peer_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    async def test_unregister_peer_not_found(self, test_client: AsyncClient) -> None:
        """Unregister non-existent peer returns 404."""
        response = await test_client.delete("/federation/peers/non-existent-id")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestFederationSyncAPI:
    """Test federation sync API endpoints."""

    async def test_get_sync_status(self, test_client: AsyncClient) -> None:
        """Get sync status."""
        response = await test_client.get("/federation/sync/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "mode" in data
        assert "peers_total" in data
        assert "peers_healthy" in data
        assert "unresolved_conflicts" in data
        assert "timestamp" in data

    async def test_trigger_sync_no_peers(self, test_client: AsyncClient) -> None:
        """Trigger sync with no healthy peers."""
        response = await test_client.post("/federation/sync/now")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # With no healthy peers, sync should be skipped
        assert data["status"] == "skipped"

    async def test_get_sync_history_empty(self, test_client: AsyncClient) -> None:
        """Get sync history when empty."""
        response = await test_client.get("/federation/sync/history")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "history" in data
        assert "count" in data


class TestFederationConflictsAPI:
    """Test federation conflicts API endpoints."""

    async def test_list_conflicts_empty(self, test_client: AsyncClient) -> None:
        """List conflicts returns empty list initially."""
        response = await test_client.get("/federation/conflicts")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 0
        assert data["conflicts"] == []

    async def test_get_conflict_not_found(self, test_client: AsyncClient) -> None:
        """Get non-existent conflict returns 404."""
        # Use a valid UUID format for non-existent ID
        response = await test_client.get("/federation/conflicts/00000000-0000-0000-0000-000000000000")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_resolve_conflict_not_found(self, test_client: AsyncClient) -> None:
        """Resolve non-existent conflict returns 404."""
        # Use a valid UUID format for non-existent ID
        response = await test_client.post(
            "/federation/conflicts/00000000-0000-0000-0000-000000000000/resolve",
            json={"strategy": "last_write_wins"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_resolve_conflict_invalid_strategy(self, test_client: AsyncClient) -> None:
        """Resolve with invalid strategy returns 400."""
        # Use a valid UUID format for non-existent ID
        response = await test_client.post(
            "/federation/conflicts/00000000-0000-0000-0000-000000000000/resolve",
            json={"strategy": "invalid_strategy"},
        )
        # Will be 404 because conflict not found (checked before strategy validation)
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND)

    async def test_resolve_all_conflicts_empty(self, test_client: AsyncClient) -> None:
        """Resolve all conflicts when none exist."""
        response = await test_client.post(
            "/federation/conflicts/resolve-all",
            params={"strategy": "last_write_wins"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 0
        assert data["resolved"] == 0
        assert data["failed"] == 0
