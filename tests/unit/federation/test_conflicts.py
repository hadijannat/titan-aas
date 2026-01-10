"""Tests for federation conflict resolution."""

from datetime import UTC, datetime

import pytest

from titan.federation.conflicts import (
    ConflictInfo,
    ConflictManager,
    ConflictResolver,
    ResolutionResult,
    ResolutionStrategy,
)


class TestResolutionStrategy:
    """Test resolution strategy enum."""

    def test_strategy_values(self) -> None:
        """All expected strategies are defined."""
        assert ResolutionStrategy.LAST_WRITE_WINS.value == "last_write_wins"
        assert ResolutionStrategy.LOCAL_PREFERRED.value == "local_preferred"
        assert ResolutionStrategy.REMOTE_PREFERRED.value == "remote_preferred"
        assert ResolutionStrategy.MANUAL.value == "manual"


class TestConflictInfo:
    """Test ConflictInfo dataclass."""

    @pytest.fixture
    def conflict(self) -> ConflictInfo:
        """Create a sample conflict."""
        return ConflictInfo(
            id="conflict-001",
            peer_id="peer-001",
            entity_type="aas",
            entity_id="https://example.com/aas/1",
            local_doc={"id": "https://example.com/aas/1", "updated_at": "2024-01-01T10:00:00Z"},
            local_etag="etag-local-123",
            remote_doc={"id": "https://example.com/aas/1", "updated_at": "2024-01-01T12:00:00Z"},
            remote_etag="etag-remote-456",
            detected_at=datetime.now(UTC),
        )

    def test_is_resolved_false(self, conflict: ConflictInfo) -> None:
        """Unresolved conflict returns False."""
        assert conflict.is_resolved is False

    def test_is_resolved_true(self, conflict: ConflictInfo) -> None:
        """Resolved conflict returns True."""
        conflict.resolved_at = datetime.now(UTC)
        assert conflict.is_resolved is True


class TestConflictResolver:
    """Test ConflictResolver class."""

    @pytest.fixture
    def resolver(self) -> ConflictResolver:
        """Create a resolver with default strategy."""
        return ConflictResolver()

    @pytest.fixture
    def conflict_with_timestamps(self) -> ConflictInfo:
        """Create a conflict with timestamps."""
        return ConflictInfo(
            id="conflict-001",
            peer_id="peer-001",
            entity_type="aas",
            entity_id="https://example.com/aas/1",
            local_doc={
                "id": "https://example.com/aas/1",
                "updated_at": "2024-01-01T10:00:00+00:00",
            },
            local_etag="etag-local",
            remote_doc={
                "id": "https://example.com/aas/1",
                "updated_at": "2024-01-01T12:00:00+00:00",
            },
            remote_etag="etag-remote",
            detected_at=datetime.now(UTC),
        )

    @pytest.fixture
    def conflict_without_timestamps(self) -> ConflictInfo:
        """Create a conflict without timestamps."""
        return ConflictInfo(
            id="conflict-002",
            peer_id="peer-001",
            entity_type="submodel",
            entity_id="https://example.com/submodel/1",
            local_doc={"id": "https://example.com/submodel/1"},
            local_etag="etag-local",
            remote_doc={"id": "https://example.com/submodel/1"},
            remote_etag="etag-remote",
            detected_at=datetime.now(UTC),
        )

    def test_default_strategy_is_last_write_wins(self, resolver: ConflictResolver) -> None:
        """Default strategy is last-write-wins."""
        assert resolver.default_strategy == ResolutionStrategy.LAST_WRITE_WINS

    def test_last_write_wins_remote_newer(
        self, resolver: ConflictResolver, conflict_with_timestamps: ConflictInfo
    ) -> None:
        """Last-write-wins chooses remote when it's newer."""
        result = resolver.resolve(conflict_with_timestamps)
        assert result.success is True
        assert result.strategy_applied == ResolutionStrategy.LAST_WRITE_WINS
        assert result.chosen_doc == conflict_with_timestamps.remote_doc

    def test_last_write_wins_local_newer(self, resolver: ConflictResolver) -> None:
        """Last-write-wins chooses local when it's newer."""
        conflict = ConflictInfo(
            id="conflict-003",
            peer_id="peer-001",
            entity_type="aas",
            entity_id="https://example.com/aas/1",
            local_doc={"id": "1", "updated_at": "2024-01-01T14:00:00+00:00"},
            local_etag="etag-local",
            remote_doc={"id": "1", "updated_at": "2024-01-01T12:00:00+00:00"},
            remote_etag="etag-remote",
            detected_at=datetime.now(UTC),
        )
        result = resolver.resolve(conflict)
        assert result.success is True
        assert result.chosen_doc == conflict.local_doc

    def test_last_write_wins_no_timestamps_defaults_to_local(
        self, resolver: ConflictResolver, conflict_without_timestamps: ConflictInfo
    ) -> None:
        """Last-write-wins defaults to local when no timestamps."""
        result = resolver.resolve(conflict_without_timestamps)
        assert result.success is True
        assert result.chosen_doc == conflict_without_timestamps.local_doc

    def test_local_preferred_strategy(
        self, resolver: ConflictResolver, conflict_with_timestamps: ConflictInfo
    ) -> None:
        """Local-preferred always chooses local."""
        result = resolver.resolve(conflict_with_timestamps, ResolutionStrategy.LOCAL_PREFERRED)
        assert result.success is True
        assert result.strategy_applied == ResolutionStrategy.LOCAL_PREFERRED
        assert result.chosen_doc == conflict_with_timestamps.local_doc

    def test_remote_preferred_strategy(
        self, resolver: ConflictResolver, conflict_with_timestamps: ConflictInfo
    ) -> None:
        """Remote-preferred always chooses remote."""
        result = resolver.resolve(conflict_with_timestamps, ResolutionStrategy.REMOTE_PREFERRED)
        assert result.success is True
        assert result.strategy_applied == ResolutionStrategy.REMOTE_PREFERRED
        assert result.chosen_doc == conflict_with_timestamps.remote_doc

    def test_manual_strategy_returns_failure(
        self, resolver: ConflictResolver, conflict_with_timestamps: ConflictInfo
    ) -> None:
        """Manual strategy returns failure requiring manual intervention."""
        result = resolver.resolve(conflict_with_timestamps, ResolutionStrategy.MANUAL)
        assert result.success is False
        assert result.strategy_applied == ResolutionStrategy.MANUAL
        assert result.error == "Manual resolution required"


class TestConflictManager:
    """Test ConflictManager class."""

    @pytest.fixture
    def manager(self) -> ConflictManager:
        """Create a conflict manager."""
        return ConflictManager()

    @pytest.fixture
    def conflict1(self) -> ConflictInfo:
        """Create first conflict."""
        return ConflictInfo(
            id="conflict-001",
            peer_id="peer-001",
            entity_type="aas",
            entity_id="https://example.com/aas/1",
            local_doc={"id": "1", "updated_at": "2024-01-01T10:00:00+00:00"},
            local_etag="etag-local-1",
            remote_doc={"id": "1", "updated_at": "2024-01-01T12:00:00+00:00"},
            remote_etag="etag-remote-1",
            detected_at=datetime.now(UTC),
        )

    @pytest.fixture
    def conflict2(self) -> ConflictInfo:
        """Create second conflict."""
        return ConflictInfo(
            id="conflict-002",
            peer_id="peer-002",
            entity_type="submodel",
            entity_id="https://example.com/submodel/1",
            local_doc={"id": "1"},
            local_etag="etag-local-2",
            remote_doc={"id": "1"},
            remote_etag="etag-remote-2",
            detected_at=datetime.now(UTC),
        )

    def test_add_conflict(self, manager: ConflictManager, conflict1: ConflictInfo) -> None:
        """Adding a conflict stores it."""
        manager.add_conflict(conflict1)
        assert manager.get_conflict("conflict-001") is conflict1

    def test_get_conflict_not_found(self, manager: ConflictManager) -> None:
        """Getting non-existent conflict returns None."""
        assert manager.get_conflict("non-existent") is None

    def test_list_unresolved(
        self, manager: ConflictManager, conflict1: ConflictInfo, conflict2: ConflictInfo
    ) -> None:
        """List unresolved returns only unresolved conflicts."""
        manager.add_conflict(conflict1)
        manager.add_conflict(conflict2)

        unresolved = manager.list_unresolved()
        assert len(unresolved) == 2

    def test_list_unresolved_by_peer(
        self, manager: ConflictManager, conflict1: ConflictInfo, conflict2: ConflictInfo
    ) -> None:
        """List unresolved filters by peer ID."""
        manager.add_conflict(conflict1)
        manager.add_conflict(conflict2)

        unresolved = manager.list_unresolved(peer_id="peer-001")
        assert len(unresolved) == 1
        assert unresolved[0].id == "conflict-001"

    def test_resolve_conflict(self, manager: ConflictManager, conflict1: ConflictInfo) -> None:
        """Resolving a conflict marks it as resolved."""
        manager.add_conflict(conflict1)
        result = manager.resolve_conflict("conflict-001", resolved_by="test")

        assert result.success is True
        conflict = manager.get_conflict("conflict-001")
        assert conflict is not None
        assert conflict.is_resolved is True
        assert conflict.resolved_by == "test"

    def test_resolve_conflict_not_found(self, manager: ConflictManager) -> None:
        """Resolving non-existent conflict returns failure."""
        result = manager.resolve_conflict("non-existent")
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    def test_resolve_already_resolved(
        self, manager: ConflictManager, conflict1: ConflictInfo
    ) -> None:
        """Resolving already resolved conflict returns failure."""
        manager.add_conflict(conflict1)
        manager.resolve_conflict("conflict-001")

        result = manager.resolve_conflict("conflict-001")
        assert result.success is False
        assert "already resolved" in (result.error or "").lower()

    def test_resolve_all(
        self, manager: ConflictManager, conflict1: ConflictInfo, conflict2: ConflictInfo
    ) -> None:
        """Resolve all resolves all unresolved conflicts."""
        manager.add_conflict(conflict1)
        manager.add_conflict(conflict2)

        results = manager.resolve_all(resolved_by="batch")
        assert len(results) == 2
        assert all(r.success for r in results.values())

    def test_clear_resolved(
        self, manager: ConflictManager, conflict1: ConflictInfo, conflict2: ConflictInfo
    ) -> None:
        """Clear resolved removes only resolved conflicts."""
        manager.add_conflict(conflict1)
        manager.add_conflict(conflict2)
        manager.resolve_conflict("conflict-001")

        cleared = manager.clear_resolved()
        assert cleared == 1
        assert manager.get_conflict("conflict-001") is None
        assert manager.get_conflict("conflict-002") is not None
