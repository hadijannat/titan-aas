"""Tests for federation synchronization."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from titan.federation import ChangeQueue, FederationSync, SyncChange, SyncMode, SyncTopology
from titan.federation.conflicts import ConflictManager, ResolutionStrategy
from titan.federation.peer import Peer, PeerCapabilities, PeerRegistry, PeerStatus
from titan.federation.sync import SyncResult, _compute_simple_etag, _url_encode_id


class TestSyncMode:
    """Test sync mode enum."""

    def test_mode_values(self) -> None:
        """All expected modes are defined."""
        assert SyncMode.PULL.value == "pull"
        assert SyncMode.PUSH.value == "push"
        assert SyncMode.BIDIRECTIONAL.value == "bidirectional"


class TestSyncResult:
    """Test SyncResult dataclass."""

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        result = SyncResult(peer_id="peer-001", success=True)
        assert result.pushed == 0
        assert result.pulled == 0
        assert result.conflicts == 0
        assert result.errors == []
        assert result.duration_ms == 0

    def test_with_values(self) -> None:
        """Values can be set."""
        result = SyncResult(
            peer_id="peer-001",
            success=True,
            pushed=10,
            pulled=5,
            conflicts=1,
            errors=["error1"],
            duration_ms=100.5,
        )
        assert result.pushed == 10
        assert result.pulled == 5
        assert result.conflicts == 1
        assert result.errors == ["error1"]
        assert result.duration_ms == 100.5


class TestFederationSync:
    """Test FederationSync class."""

    @pytest.fixture
    def registry(self) -> PeerRegistry:
        """Create a peer registry."""
        return PeerRegistry()

    @pytest.fixture
    def conflict_manager(self) -> ConflictManager:
        """Create a conflict manager."""
        return ConflictManager()

    @pytest.fixture
    def sync(self, registry: PeerRegistry, conflict_manager: ConflictManager) -> FederationSync:
        """Create federation sync instance."""
        return FederationSync(
            registry=registry,
            conflict_manager=conflict_manager,
        )

    @pytest.fixture
    def healthy_peer(self) -> Peer:
        """Create a healthy peer."""
        return Peer(
            id="peer-001",
            url="http://peer1.example.com",
            name="Peer 1",
            status=PeerStatus.ONLINE,
            capabilities=PeerCapabilities(),
        )

    @pytest.fixture
    def offline_peer(self) -> Peer:
        """Create an offline peer."""
        return Peer(
            id="peer-002",
            url="http://peer2.example.com",
            name="Peer 2",
            status=PeerStatus.OFFLINE,
            capabilities=PeerCapabilities(),
        )

    def test_default_mode_is_bidirectional(self, sync: FederationSync) -> None:
        """Default sync mode is bidirectional."""
        assert sync.mode == SyncMode.BIDIRECTIONAL

    def test_mode_can_be_changed(self, sync: FederationSync) -> None:
        """Sync mode can be changed."""
        sync.mode = SyncMode.PULL
        assert sync.mode == SyncMode.PULL

    async def test_sync_once_no_peers(self, sync: FederationSync) -> None:
        """Sync with no peers returns skipped status."""
        result = await sync.sync_once()
        assert result["status"] == "skipped"
        assert result["reason"] == "no healthy peers"
        assert result["peers"] == 0

    async def test_sync_once_no_healthy_peers(
        self, sync: FederationSync, registry: PeerRegistry, offline_peer: Peer
    ) -> None:
        """Sync with no healthy peers returns skipped status."""
        registry.register(offline_peer)
        result = await sync.sync_once()
        assert result["status"] == "skipped"
        assert result["reason"] == "no healthy peers"

    @patch("titan.federation.sync.httpx.AsyncClient")
    async def test_sync_once_with_healthy_peer(
        self,
        mock_client_class: MagicMock,
        sync: FederationSync,
        registry: PeerRegistry,
        healthy_peer: Peer,
    ) -> None:
        """Sync with healthy peer attempts sync."""
        registry.register(healthy_peer)

        # Mock the async context manager
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": [], "paging_metadata": {}}
        mock_client.get.return_value = mock_response

        result = await sync.sync_once()
        assert result["peers"] == 1
        assert result["status"] in ("completed", "partial", "failed")

    def test_get_sync_status(
        self, sync: FederationSync, registry: PeerRegistry, healthy_peer: Peer, offline_peer: Peer
    ) -> None:
        """Get sync status returns current state."""
        registry.register(healthy_peer)
        registry.register(offline_peer)

        status = sync.get_sync_status()
        assert status["mode"] == "bidirectional"
        assert status["peers_total"] == 2
        assert status["peers_healthy"] == 1
        assert status["unresolved_conflicts"] == 0

    async def test_resolve_conflicts(
        self, sync: FederationSync, conflict_manager: ConflictManager
    ) -> None:
        """Resolve conflicts delegates to manager."""
        # Add a conflict
        from titan.federation.conflicts import ConflictInfo

        conflict = ConflictInfo(
            id="conflict-001",
            peer_id="peer-001",
            entity_type="aas",
            entity_id="https://example.com/aas/1",
            local_doc={"id": "1"},
            local_etag="etag-local",
            remote_doc={"id": "1"},
            remote_etag="etag-remote",
            detected_at=datetime.now(UTC),
        )
        conflict_manager.add_conflict(conflict)

        result = await sync.resolve_conflicts()
        assert result["total"] == 1
        assert result["resolved"] == 1
        assert result["failed"] == 0
        assert result["strategy"] == "last_write_wins"

    async def test_resolve_conflicts_with_strategy(
        self, sync: FederationSync, conflict_manager: ConflictManager
    ) -> None:
        """Resolve conflicts uses specified strategy."""
        from titan.federation.conflicts import ConflictInfo

        conflict = ConflictInfo(
            id="conflict-001",
            peer_id="peer-001",
            entity_type="aas",
            entity_id="https://example.com/aas/1",
            local_doc={"id": "1"},
            local_etag="etag-local",
            remote_doc={"id": "1"},
            remote_etag="etag-remote",
            detected_at=datetime.now(UTC),
        )
        conflict_manager.add_conflict(conflict)

        result = await sync.resolve_conflicts(strategy=ResolutionStrategy.REMOTE_PREFERRED)
        assert result["strategy"] == "remote_preferred"


class TestPeer:
    """Test Peer class."""

    def test_is_healthy_online(self) -> None:
        """Online peer is healthy."""
        peer = Peer(id="peer-001", url="http://example.com", status=PeerStatus.ONLINE)
        assert peer.is_healthy is True

    def test_is_healthy_offline(self) -> None:
        """Offline peer is not healthy."""
        peer = Peer(id="peer-001", url="http://example.com", status=PeerStatus.OFFLINE)
        assert peer.is_healthy is False

    def test_is_healthy_degraded(self) -> None:
        """Degraded peer is not healthy."""
        peer = Peer(id="peer-001", url="http://example.com", status=PeerStatus.DEGRADED)
        assert peer.is_healthy is False

    def test_to_dict(self) -> None:
        """Peer converts to dictionary."""
        now = datetime.now(UTC)
        peer = Peer(
            id="peer-001",
            url="http://example.com",
            name="Test Peer",
            status=PeerStatus.ONLINE,
            last_seen=now,
            version="0.1.0",
        )
        d = peer.to_dict()
        assert d["id"] == "peer-001"
        assert d["url"] == "http://example.com"
        assert d["name"] == "Test Peer"
        assert d["status"] == "online"
        assert d["lastSeen"] == now.isoformat()
        assert d["version"] == "0.1.0"


class TestPeerRegistry:
    """Test PeerRegistry class."""

    @pytest.fixture
    def registry(self) -> PeerRegistry:
        """Create a peer registry."""
        return PeerRegistry()

    @pytest.fixture
    def peer1(self) -> Peer:
        """Create first peer."""
        return Peer(
            id="peer-001",
            url="http://peer1.example.com",
            status=PeerStatus.ONLINE,
        )

    @pytest.fixture
    def peer2(self) -> Peer:
        """Create second peer."""
        return Peer(
            id="peer-002",
            url="http://peer2.example.com",
            status=PeerStatus.OFFLINE,
        )

    def test_register(self, registry: PeerRegistry, peer1: Peer) -> None:
        """Registering a peer adds it to the registry."""
        registry.register(peer1)
        assert registry.get("peer-001") is peer1

    def test_unregister(self, registry: PeerRegistry, peer1: Peer) -> None:
        """Unregistering a peer removes it."""
        registry.register(peer1)
        assert registry.unregister("peer-001") is True
        assert registry.get("peer-001") is None

    def test_unregister_not_found(self, registry: PeerRegistry) -> None:
        """Unregistering non-existent peer returns False."""
        assert registry.unregister("non-existent") is False

    def test_list_all(self, registry: PeerRegistry, peer1: Peer, peer2: Peer) -> None:
        """List all returns all peers."""
        registry.register(peer1)
        registry.register(peer2)
        peers = registry.list_all()
        assert len(peers) == 2

    def test_list_healthy(self, registry: PeerRegistry, peer1: Peer, peer2: Peer) -> None:
        """List healthy returns only healthy peers."""
        registry.register(peer1)
        registry.register(peer2)
        healthy = registry.list_healthy()
        assert len(healthy) == 1
        assert healthy[0].id == "peer-001"


class TestSyncTopology:
    """Test SyncTopology enum."""

    def test_topology_values(self) -> None:
        """All expected topologies are defined."""
        assert SyncTopology.MESH.value == "mesh"
        assert SyncTopology.HUB_SPOKE.value == "hub_spoke"


class TestSyncChange:
    """Test SyncChange dataclass."""

    def test_create_change(self) -> None:
        """Create a sync change."""
        change = SyncChange(
            id="change-001",
            entity_type="aas",
            entity_id="urn:example:shell:1",
            operation="create",
            doc={"id": "urn:example:shell:1"},
            etag="abc123",
        )
        assert change.id == "change-001"
        assert change.entity_type == "aas"
        assert change.operation == "create"
        assert change.timestamp is not None

    def test_to_dict(self) -> None:
        """Convert change to dictionary."""
        change = SyncChange(
            id="change-001",
            entity_type="submodel",
            entity_id="urn:example:sm:1",
            operation="update",
            doc={"id": "urn:example:sm:1"},
        )
        d = change.to_dict()
        assert d["changeId"] == "change-001"
        assert d["entityType"] == "submodel"
        assert d["operation"] == "update"
        assert "timestamp" in d


class TestChangeQueue:
    """Test ChangeQueue class."""

    def test_add_and_get_pending(self) -> None:
        """Add changes and retrieve pending."""
        queue = ChangeQueue()
        change1 = SyncChange(id="c1", entity_type="aas", entity_id="id1", operation="create")
        change2 = SyncChange(id="c2", entity_type="submodel", entity_id="id2", operation="update")

        queue.add(change1)
        queue.add(change2)

        pending = queue.get_pending()
        assert len(pending) == 2

    def test_get_pending_since(self) -> None:
        """Get pending changes since a timestamp."""
        queue = ChangeQueue()

        # Add old change
        old_time = datetime.now(UTC) - timedelta(hours=1)
        old_change = SyncChange(id="old", entity_type="aas", entity_id="id1", operation="create")
        old_change = SyncChange(
            id="old",
            entity_type="aas",
            entity_id="id1",
            operation="create",
            timestamp=old_time,
        )
        queue.add(old_change)

        # Add new change
        new_change = SyncChange(id="new", entity_type="aas", entity_id="id2", operation="create")
        queue.add(new_change)

        # Get changes since 30 minutes ago
        since = datetime.now(UTC) - timedelta(minutes=30)
        pending = queue.get_pending(since=since)

        assert len(pending) == 1
        assert pending[0].id == "new"

    def test_mark_synced(self) -> None:
        """Mark changes as synced removes them."""
        queue = ChangeQueue()
        change1 = SyncChange(id="c1", entity_type="aas", entity_id="id1", operation="create")
        change2 = SyncChange(id="c2", entity_type="aas", entity_id="id2", operation="update")

        queue.add(change1)
        queue.add(change2)

        removed = queue.mark_synced(["c1"])
        assert removed == 1
        assert len(queue) == 1

        pending = queue.get_pending()
        assert pending[0].id == "c2"

    def test_clear(self) -> None:
        """Clear removes all changes."""
        queue = ChangeQueue()
        for i in range(5):
            queue.add(
                SyncChange(id=f"c{i}", entity_type="aas", entity_id=f"id{i}", operation="create")
            )

        assert len(queue) == 5
        queue.clear()
        assert len(queue) == 0

    def test_max_size_drops_oldest(self) -> None:
        """Queue overflow drops oldest changes."""
        queue = ChangeQueue(_max_size=3)

        for i in range(5):
            queue.add(
                SyncChange(id=f"c{i}", entity_type="aas", entity_id=f"id{i}", operation="create")
            )

        assert len(queue) == 3
        # Should have c2, c3, c4 (oldest dropped)
        pending = queue.get_pending()
        ids = [c.id for c in pending]
        assert "c0" not in ids
        assert "c1" not in ids


class TestFederationSyncTrackChange:
    """Test FederationSync.track_change method."""

    @pytest.fixture
    def sync(self) -> FederationSync:
        """Create federation sync."""
        return FederationSync(registry=PeerRegistry())

    def test_track_change_adds_to_queue(self, sync: FederationSync) -> None:
        """Tracking a change adds it to the queue."""
        sync.track_change(
            entity_type="aas",
            entity_id="urn:example:shell:1",
            operation="create",
            doc={"id": "urn:example:shell:1"},
            etag="abc123",
        )

        assert len(sync.change_queue) == 1
        pending = sync.change_queue.get_pending()
        assert pending[0].entity_type == "aas"
        assert pending[0].operation == "create"

    def test_track_change_updates_etag_store(self, sync: FederationSync) -> None:
        """Tracking a change updates the etag store."""
        sync.track_change(
            entity_type="submodel",
            entity_id="urn:example:sm:1",
            operation="update",
            etag="xyz789",
        )

        key = "submodel:urn:example:sm:1"
        assert sync._etag_store.get(key) == "xyz789"


class TestFederationSyncTopology:
    """Test FederationSync topology behavior."""

    @pytest.fixture
    def registry(self) -> PeerRegistry:
        """Create peer registry with peers."""
        registry = PeerRegistry()
        registry.register(Peer(id="hub", url="http://hub.example.com", status=PeerStatus.ONLINE))
        registry.register(
            Peer(id="spoke1", url="http://spoke1.example.com", status=PeerStatus.ONLINE)
        )
        registry.register(
            Peer(id="spoke2", url="http://spoke2.example.com", status=PeerStatus.ONLINE)
        )
        return registry

    def test_mesh_topology_syncs_all_peers(self, registry: PeerRegistry) -> None:
        """Mesh topology syncs with all healthy peers."""
        sync = FederationSync(registry=registry, topology=SyncTopology.MESH)
        peers = sync._get_sync_peers()
        assert len(peers) == 3

    def test_hub_spoke_as_spoke(self, registry: PeerRegistry) -> None:
        """Hub-spoke as spoke syncs only with hub."""
        sync = FederationSync(
            registry=registry,
            topology=SyncTopology.HUB_SPOKE,
            hub_peer_id="hub",
        )
        peers = sync._get_sync_peers()
        assert len(peers) == 1
        assert peers[0].id == "hub"

    def test_hub_spoke_as_hub(self, registry: PeerRegistry) -> None:
        """Hub-spoke as hub syncs with all peers."""
        sync = FederationSync(
            registry=registry,
            topology=SyncTopology.HUB_SPOKE,
            hub_peer_id=None,  # We are the hub
        )
        peers = sync._get_sync_peers()
        assert len(peers) == 3


class TestFederationSyncPush:
    """Test FederationSync push operations."""

    @pytest.fixture
    def sync(self) -> FederationSync:
        """Create federation sync."""
        registry = PeerRegistry()
        registry.register(
            Peer(id="peer1", url="http://peer1.example.com", status=PeerStatus.ONLINE)
        )
        return FederationSync(registry=registry, mode=SyncMode.PUSH)

    @patch("titan.federation.sync.httpx.AsyncClient")
    async def test_push_creates(self, mock_client_class: MagicMock, sync: FederationSync) -> None:
        """Push create operation posts to peer."""
        # Track a create change
        sync.track_change(
            entity_type="aas",
            entity_id="urn:example:shell:1",
            operation="create",
            doc={"id": "urn:example:shell:1"},
        )

        # Mock HTTP client
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        # Mock successful POST
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_client.post.return_value = mock_response

        result = await sync.sync_once()

        assert result["pushed"] == 1
        mock_client.post.assert_called()

    @patch("titan.federation.sync.httpx.AsyncClient")
    async def test_push_updates(self, mock_client_class: MagicMock, sync: FederationSync) -> None:
        """Push update operation puts to peer."""
        sync.track_change(
            entity_type="submodel",
            entity_id="urn:example:sm:1",
            operation="update",
            doc={"id": "urn:example:sm:1"},
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.put.return_value = mock_response

        result = await sync.sync_once()

        assert result["pushed"] == 1
        mock_client.put.assert_called()

    @patch("titan.federation.sync.httpx.AsyncClient")
    async def test_push_deletes(self, mock_client_class: MagicMock, sync: FederationSync) -> None:
        """Push delete operation deletes on peer."""
        sync.track_change(
            entity_type="aas",
            entity_id="urn:example:shell:1",
            operation="delete",
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_client.delete.return_value = mock_response

        result = await sync.sync_once()

        assert result["pushed"] == 1
        mock_client.delete.assert_called()


class TestDeltaSync:
    """Test delta sync behavior."""

    @pytest.fixture
    def sync(self) -> FederationSync:
        """Create federation sync."""
        registry = PeerRegistry()
        peer = Peer(id="peer1", url="http://peer1.example.com", status=PeerStatus.ONLINE)
        peer.last_sync = datetime.now(UTC) - timedelta(hours=1)
        registry.register(peer)
        return FederationSync(registry=registry, delta_sync_enabled=True)

    def test_delta_sync_filters_old_changes(self, sync: FederationSync) -> None:
        """Delta sync only pushes changes since last sync."""
        # Add old change (before last sync)
        old_time = datetime.now(UTC) - timedelta(hours=2)
        old_change = SyncChange(
            id="old",
            entity_type="aas",
            entity_id="id1",
            operation="create",
            timestamp=old_time,
        )
        sync.change_queue.add(old_change)

        # Add new change (after last sync)
        new_change = SyncChange(
            id="new",
            entity_type="aas",
            entity_id="id2",
            operation="create",
        )
        sync.change_queue.add(new_change)

        # Get pending for peer (last sync was 1 hour ago)
        peer = sync.registry.list_healthy()[0]
        changes = sync.change_queue.get_pending(since=peer.last_sync)

        assert len(changes) == 1
        assert changes[0].id == "new"


class TestHelperFunctions:
    """Test helper functions."""

    def test_url_encode_id(self) -> None:
        """URL encode ID uses base64url."""
        encoded = _url_encode_id("urn:example:shell:1")
        assert encoded  # Non-empty
        assert "=" not in encoded  # No padding
        assert "+" not in encoded  # URL safe
        assert "/" not in encoded  # URL safe

    def test_compute_simple_etag(self) -> None:
        """Compute simple etag is consistent."""
        doc = {"id": "test", "value": 123}

        etag1 = _compute_simple_etag(doc)
        etag2 = _compute_simple_etag(doc)

        assert etag1 == etag2
        assert len(etag1) == 16  # Truncated hash

    def test_compute_simple_etag_different_for_different_docs(self) -> None:
        """Different docs produce different etags."""
        doc1 = {"id": "test1"}
        doc2 = {"id": "test2"}

        etag1 = _compute_simple_etag(doc1)
        etag2 = _compute_simple_etag(doc2)

        assert etag1 != etag2


class TestSyncStatusExtended:
    """Test extended sync status."""

    def test_status_includes_topology(self) -> None:
        """Status includes topology information."""
        sync = FederationSync(
            registry=PeerRegistry(),
            topology=SyncTopology.HUB_SPOKE,
            hub_peer_id="hub-001",
        )
        status = sync.get_sync_status()

        assert status["topology"] == "hub_spoke"
        assert status["hub_peer_id"] == "hub-001"
        assert status["delta_sync_enabled"] is True

    def test_status_includes_pending_changes(self) -> None:
        """Status includes pending changes count."""
        sync = FederationSync(registry=PeerRegistry())
        sync.track_change("aas", "id1", "create")
        sync.track_change("aas", "id2", "update")

        status = sync.get_sync_status()
        assert status["pending_changes"] == 2

    def test_clear_pending_changes(self) -> None:
        """Clear pending changes empties queue."""
        sync = FederationSync(registry=PeerRegistry())
        sync.track_change("aas", "id1", "create")
        sync.track_change("aas", "id2", "update")

        count = sync.clear_pending_changes()
        assert count == 2
        assert len(sync.change_queue) == 0
