"""Federation synchronization primitives."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx

from titan.federation.conflicts import ConflictManager, ResolutionStrategy
from titan.federation.peer import Peer, PeerRegistry

logger = logging.getLogger(__name__)


class SyncMode(str, Enum):
    """Synchronization modes."""

    PULL = "pull"
    PUSH = "push"
    BIDIRECTIONAL = "bidirectional"


@dataclass
class SyncResult:
    """Result of a sync operation with a single peer."""

    peer_id: str
    success: bool
    pushed: int = 0
    pulled: int = 0
    conflicts: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0


@dataclass
class FederationSync:
    """Coordinates data synchronization across federated peers.

    Orchestrates push/pull operations with multiple peers and
    handles conflict detection and resolution.
    """

    registry: PeerRegistry
    mode: SyncMode = SyncMode.BIDIRECTIONAL
    conflict_manager: ConflictManager = field(default_factory=ConflictManager)
    sync_timeout: float = 30.0

    async def sync_once(self) -> dict[str, Any]:
        """Run a single sync cycle with all healthy peers.

        Iterates through healthy peers and syncs data according to mode:
        - PULL: Only pull updates from peers
        - PUSH: Only push local changes to peers
        - BIDIRECTIONAL: Both push and pull

        Returns a summary payload suitable for logging/metrics.
        """
        peers = self.registry.list_healthy()
        start_time = datetime.now(UTC)

        logger.info(f"Federation sync started: mode={self.mode.value}, peers={len(peers)}")

        if not peers:
            return {
                "mode": self.mode.value,
                "peers": 0,
                "status": "skipped",
                "reason": "no healthy peers",
                "duration_ms": 0,
            }

        results: list[SyncResult] = []
        total_pushed = 0
        total_pulled = 0
        total_conflicts = 0
        total_errors: list[str] = []

        async with httpx.AsyncClient(timeout=self.sync_timeout) as client:
            for peer in peers:
                try:
                    result = await self._sync_with_peer(client, peer)
                    results.append(result)

                    total_pushed += result.pushed
                    total_pulled += result.pulled
                    total_conflicts += result.conflicts
                    total_errors.extend(result.errors)

                    # Update peer last_sync timestamp
                    peer.last_sync = datetime.now(UTC)

                except Exception as e:
                    error_msg = f"Sync with {peer.id} failed: {e}"
                    logger.error(error_msg)
                    total_errors.append(error_msg)
                    results.append(
                        SyncResult(
                            peer_id=peer.id,
                            success=False,
                            errors=[str(e)],
                        )
                    )

        end_time = datetime.now(UTC)
        duration_ms = (end_time - start_time).total_seconds() * 1000

        # Determine overall status
        successful = sum(1 for r in results if r.success)
        if successful == len(results):
            status = "completed"
        elif successful > 0:
            status = "partial"
        else:
            status = "failed"

        summary = {
            "mode": self.mode.value,
            "peers": len(peers),
            "peers_synced": successful,
            "status": status,
            "pushed": total_pushed,
            "pulled": total_pulled,
            "conflicts": total_conflicts,
            "errors": total_errors[:10],  # Limit error list
            "duration_ms": round(duration_ms, 2),
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
        }

        logger.info(
            f"Federation sync completed: status={status}, "
            f"pushed={total_pushed}, pulled={total_pulled}, "
            f"conflicts={total_conflicts}, duration={duration_ms:.0f}ms"
        )

        return summary

    async def _sync_with_peer(self, client: httpx.AsyncClient, peer: Peer) -> SyncResult:
        """Sync with a single peer.

        Args:
            client: HTTP client
            peer: Peer to sync with

        Returns:
            Sync result for this peer
        """
        start_time = datetime.now(UTC)
        result = SyncResult(peer_id=peer.id, success=True)

        try:
            if self.mode in (SyncMode.PUSH, SyncMode.BIDIRECTIONAL):
                pushed = await self._push_to_peer(client, peer)
                result.pushed = pushed

            if self.mode in (SyncMode.PULL, SyncMode.BIDIRECTIONAL):
                pulled, conflicts = await self._pull_from_peer(client, peer)
                result.pulled = pulled
                result.conflicts = conflicts

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            logger.error(f"Sync with peer {peer.id} failed: {e}")

        end_time = datetime.now(UTC)
        result.duration_ms = (end_time - start_time).total_seconds() * 1000

        return result

    async def _push_to_peer(self, client: httpx.AsyncClient, peer: Peer) -> int:
        """Push local changes to a peer.

        Args:
            client: HTTP client
            peer: Target peer

        Returns:
            Number of items pushed
        """
        # This is a stub - actual implementation requires:
        # 1. Get pending changes from local queue
        # 2. Push each change to peer
        # 3. Track success/failure
        logger.debug(f"Push to peer {peer.id} (stub)")
        return 0

    async def _pull_from_peer(self, client: httpx.AsyncClient, peer: Peer) -> tuple[int, int]:
        """Pull updates from a peer.

        Args:
            client: HTTP client
            peer: Source peer

        Returns:
            Tuple of (items_pulled, conflicts_detected)
        """
        pulled = 0
        conflicts = 0

        # Pull AAS shells
        shells_pulled, shells_conflicts = await self._pull_entity_type(
            client, peer, "aas", "/shells"
        )
        pulled += shells_pulled
        conflicts += shells_conflicts

        # Pull submodels
        submodels_pulled, submodels_conflicts = await self._pull_entity_type(
            client, peer, "submodel", "/submodels"
        )
        pulled += submodels_pulled
        conflicts += submodels_conflicts

        return pulled, conflicts

    async def _pull_entity_type(
        self,
        client: httpx.AsyncClient,
        peer: Peer,
        entity_type: str,
        endpoint: str,
    ) -> tuple[int, int]:
        """Pull a specific entity type from a peer.

        Args:
            client: HTTP client
            peer: Source peer
            entity_type: Type of entity
            endpoint: API endpoint

        Returns:
            Tuple of (items_pulled, conflicts_detected)
        """
        pulled = 0
        conflicts = 0
        cursor: str | None = None
        url = f"{peer.url}{endpoint}"

        try:
            while True:
                params: dict[str, Any] = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.warning(
                        f"Pull {entity_type} from {peer.id} failed: {response.status_code}"
                    )
                    break

                data = response.json()
                items = data.get("result", [])

                if not items:
                    break

                for _item in items:
                    # Process each item - check for conflicts
                    # This is simplified; actual impl would check local DB
                    pulled += 1

                # Get next cursor
                paging = data.get("paging_metadata", {})
                next_cursor = paging.get("cursor")
                if next_cursor:
                    cursor = next_cursor
                else:
                    break

        except Exception as e:
            logger.error(f"Pull {entity_type} from {peer.id} failed: {e}")

        return pulled, conflicts

    async def resolve_conflicts(
        self,
        strategy: ResolutionStrategy = ResolutionStrategy.LAST_WRITE_WINS,
        peer_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve all pending conflicts.

        Args:
            strategy: Resolution strategy to apply
            peer_id: Filter conflicts by peer ID (optional)

        Returns:
            Summary of resolution results
        """
        results = self.conflict_manager.resolve_all(
            peer_id=peer_id,
            strategy=strategy,
            resolved_by="federation_sync",
        )

        resolved = sum(1 for r in results.values() if r.success)
        failed = len(results) - resolved

        return {
            "total": len(results),
            "resolved": resolved,
            "failed": failed,
            "strategy": strategy.value,
        }

    def get_sync_status(self) -> dict[str, Any]:
        """Get current sync status.

        Returns:
            Status summary
        """
        healthy_peers = self.registry.list_healthy()
        all_peers = self.registry.list_all()
        unresolved = self.conflict_manager.list_unresolved()

        return {
            "mode": self.mode.value,
            "peers_total": len(all_peers),
            "peers_healthy": len(healthy_peers),
            "unresolved_conflicts": len(unresolved),
        }
