"""Conflict resolution for federation sync.

Provides strategies and utilities for resolving sync conflicts
when local and remote versions of an entity differ.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ResolutionStrategy(str, Enum):
    """Conflict resolution strategies."""

    LAST_WRITE_WINS = "last_write_wins"
    LOCAL_PREFERRED = "local_preferred"
    REMOTE_PREFERRED = "remote_preferred"
    MANUAL = "manual"


@dataclass
class ConflictInfo:
    """Information about a sync conflict."""

    id: str
    peer_id: str
    entity_type: str
    entity_id: str
    local_doc: dict[str, Any]
    local_etag: str
    remote_doc: dict[str, Any]
    remote_etag: str
    detected_at: datetime
    resolution_strategy: ResolutionStrategy | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None

    @property
    def is_resolved(self) -> bool:
        """Check if conflict has been resolved."""
        return self.resolved_at is not None


@dataclass
class ResolutionResult:
    """Result of conflict resolution."""

    success: bool
    chosen_doc: dict[str, Any] | None = None
    strategy_applied: ResolutionStrategy | None = None
    error: str | None = None


class ConflictResolver:
    """Resolves sync conflicts using configured strategies."""

    def __init__(self, default_strategy: ResolutionStrategy = ResolutionStrategy.LAST_WRITE_WINS):
        """Initialize resolver with default strategy.

        Args:
            default_strategy: Strategy to use when not specified
        """
        self.default_strategy = default_strategy

    def resolve(
        self,
        conflict: ConflictInfo,
        strategy: ResolutionStrategy | None = None,
    ) -> ResolutionResult:
        """Resolve a conflict using the specified strategy.

        Args:
            conflict: The conflict to resolve
            strategy: Resolution strategy (uses default if None)

        Returns:
            Resolution result with chosen document
        """
        strategy = strategy or self.default_strategy

        if strategy == ResolutionStrategy.MANUAL:
            return ResolutionResult(
                success=False,
                error="Manual resolution required",
                strategy_applied=strategy,
            )

        try:
            if strategy == ResolutionStrategy.LAST_WRITE_WINS:
                return self._resolve_last_write_wins(conflict)
            elif strategy == ResolutionStrategy.LOCAL_PREFERRED:
                return self._resolve_local_preferred(conflict)
            elif strategy == ResolutionStrategy.REMOTE_PREFERRED:
                return self._resolve_remote_preferred(conflict)
            else:
                return ResolutionResult(
                    success=False,
                    error=f"Unknown strategy: {strategy}",
                    strategy_applied=strategy,
                )
        except Exception as e:
            logger.error(f"Resolution failed: {e}")
            return ResolutionResult(
                success=False,
                error=str(e),
                strategy_applied=strategy,
            )

    def _resolve_last_write_wins(self, conflict: ConflictInfo) -> ResolutionResult:
        """Resolve using last-write-wins based on updated_at timestamp.

        Args:
            conflict: The conflict to resolve

        Returns:
            Resolution result
        """
        local_updated = self._extract_timestamp(conflict.local_doc)
        remote_updated = self._extract_timestamp(conflict.remote_doc)

        if remote_updated and local_updated:
            if remote_updated > local_updated:
                return ResolutionResult(
                    success=True,
                    chosen_doc=conflict.remote_doc,
                    strategy_applied=ResolutionStrategy.LAST_WRITE_WINS,
                )
            else:
                return ResolutionResult(
                    success=True,
                    chosen_doc=conflict.local_doc,
                    strategy_applied=ResolutionStrategy.LAST_WRITE_WINS,
                )
        elif remote_updated:
            return ResolutionResult(
                success=True,
                chosen_doc=conflict.remote_doc,
                strategy_applied=ResolutionStrategy.LAST_WRITE_WINS,
            )
        else:
            # Default to local if no timestamps available
            return ResolutionResult(
                success=True,
                chosen_doc=conflict.local_doc,
                strategy_applied=ResolutionStrategy.LAST_WRITE_WINS,
            )

    def _resolve_local_preferred(self, conflict: ConflictInfo) -> ResolutionResult:
        """Resolve by keeping local version.

        Args:
            conflict: The conflict to resolve

        Returns:
            Resolution result
        """
        return ResolutionResult(
            success=True,
            chosen_doc=conflict.local_doc,
            strategy_applied=ResolutionStrategy.LOCAL_PREFERRED,
        )

    def _resolve_remote_preferred(self, conflict: ConflictInfo) -> ResolutionResult:
        """Resolve by accepting remote version.

        Args:
            conflict: The conflict to resolve

        Returns:
            Resolution result
        """
        return ResolutionResult(
            success=True,
            chosen_doc=conflict.remote_doc,
            strategy_applied=ResolutionStrategy.REMOTE_PREFERRED,
        )

    def _extract_timestamp(self, doc: dict[str, Any]) -> datetime | None:
        """Extract updated_at timestamp from document.

        Args:
            doc: Document to extract timestamp from

        Returns:
            Datetime or None if not found
        """
        # Try common timestamp field names
        for field in ["updated_at", "updatedAt", "_updated_at", "modified"]:
            value = doc.get(field)
            if value:
                try:
                    if isinstance(value, datetime):
                        return value
                    elif isinstance(value, str):
                        # Try ISO format parsing
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
        return None


class ConflictManager:
    """Manages conflict storage and resolution workflow."""

    def __init__(
        self,
        resolver: ConflictResolver | None = None,
        default_strategy: ResolutionStrategy = ResolutionStrategy.LAST_WRITE_WINS,
    ):
        """Initialize conflict manager.

        Args:
            resolver: Conflict resolver instance
            default_strategy: Default resolution strategy
        """
        self.resolver = resolver or ConflictResolver(default_strategy)
        self._conflicts: dict[str, ConflictInfo] = {}

    def add_conflict(self, conflict: ConflictInfo) -> None:
        """Add a new conflict to track.

        Args:
            conflict: Conflict information
        """
        self._conflicts[conflict.id] = conflict
        logger.info(
            f"Conflict added: {conflict.entity_type}/{conflict.entity_id} "
            f"(local={conflict.local_etag[:8]}..., remote={conflict.remote_etag[:8]}...)"
        )

    def get_conflict(self, conflict_id: str) -> ConflictInfo | None:
        """Get a conflict by ID.

        Args:
            conflict_id: Conflict identifier

        Returns:
            Conflict info or None
        """
        return self._conflicts.get(conflict_id)

    def list_unresolved(self, peer_id: str | None = None) -> list[ConflictInfo]:
        """List unresolved conflicts.

        Args:
            peer_id: Filter by peer ID (optional)

        Returns:
            List of unresolved conflicts
        """
        conflicts = [c for c in self._conflicts.values() if not c.is_resolved]
        if peer_id:
            conflicts = [c for c in conflicts if c.peer_id == peer_id]
        return conflicts

    def resolve_conflict(
        self,
        conflict_id: str,
        strategy: ResolutionStrategy | None = None,
        resolved_by: str | None = None,
    ) -> ResolutionResult:
        """Resolve a specific conflict.

        Args:
            conflict_id: Conflict identifier
            strategy: Resolution strategy (uses default if None)
            resolved_by: User/system that resolved the conflict

        Returns:
            Resolution result
        """
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return ResolutionResult(
                success=False,
                error=f"Conflict not found: {conflict_id}",
            )

        if conflict.is_resolved:
            return ResolutionResult(
                success=False,
                error="Conflict already resolved",
                strategy_applied=conflict.resolution_strategy,
            )

        result = self.resolver.resolve(conflict, strategy)

        if result.success:
            conflict.resolution_strategy = result.strategy_applied
            conflict.resolved_at = datetime.now(UTC)
            conflict.resolved_by = resolved_by
            logger.info(
                f"Conflict resolved: {conflict.entity_type}/{conflict.entity_id} "
                f"using {result.strategy_applied}"
            )

        return result

    def resolve_all(
        self,
        peer_id: str | None = None,
        strategy: ResolutionStrategy | None = None,
        resolved_by: str | None = None,
    ) -> dict[str, ResolutionResult]:
        """Resolve all unresolved conflicts.

        Args:
            peer_id: Filter by peer ID (optional)
            strategy: Resolution strategy (uses default if None)
            resolved_by: User/system resolving conflicts

        Returns:
            Map of conflict ID to resolution result
        """
        results: dict[str, ResolutionResult] = {}
        unresolved = self.list_unresolved(peer_id)

        for conflict in unresolved:
            results[conflict.id] = self.resolve_conflict(conflict.id, strategy, resolved_by)

        return results

    def clear_resolved(self) -> int:
        """Remove resolved conflicts from memory.

        Returns:
            Number of conflicts removed
        """
        resolved_ids = [cid for cid, c in self._conflicts.items() if c.is_resolved]
        for cid in resolved_ids:
            del self._conflicts[cid]
        return len(resolved_ids)
