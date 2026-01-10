"""Tests for federation synchronization."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from titan.federation import FederationSync, SyncMode
from titan.federation.conflicts import ConflictManager, ResolutionStrategy
from titan.federation.peer import Peer, PeerCapabilities, PeerRegistry, PeerStatus
from titan.federation.sync import SyncResult


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
