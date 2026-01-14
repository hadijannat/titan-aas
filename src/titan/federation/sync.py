"""Federation synchronization primitives.

Provides bi-directional sync between federated Titan-AAS instances with:
- Push/Pull operations for shells and submodels
- Delta sync (only sync changes since last sync)
- Conflict detection and resolution
- Hub-spoke topology support
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx

from titan.federation.conflicts import ConflictInfo, ConflictManager, ResolutionStrategy
from titan.federation.peer import Peer, PeerRegistry

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class SyncMode(str, Enum):
    """Synchronization modes."""

    PULL = "pull"
    PUSH = "push"
    BIDIRECTIONAL = "bidirectional"


class SyncTopology(str, Enum):
    """Federation topology modes."""

    MESH = "mesh"  # All peers sync with each other
    HUB_SPOKE = "hub_spoke"  # Central hub syncs with spokes


@dataclass
class SyncChange:
    """A change to be synced to peers."""

    id: str
    entity_type: str  # "aas", "submodel", "concept_description"
    entity_id: str
    operation: str  # "create", "update", "delete"
    doc: dict[str, Any] | None = None
    etag: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API call."""
        return {
            "changeId": self.id,
            "entityType": self.entity_type,
            "entityId": self.entity_id,
            "operation": self.operation,
            "doc": self.doc,
            "etag": self.etag,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ChangeQueue:
    """Queue of pending changes to push to peers.

    Tracks local changes that need to be synchronized to remote peers.
    """

    _changes: list[SyncChange] = field(default_factory=list)
    _max_size: int = 10000

    def add(self, change: SyncChange) -> None:
        """Add a change to the queue."""
        if len(self._changes) >= self._max_size:
            # Drop oldest changes if queue is full
            self._changes = self._changes[-self._max_size + 1 :]
            logger.warning("Change queue overflow, dropped oldest changes")
        self._changes.append(change)

    def get_pending(self, since: datetime | None = None) -> list[SyncChange]:
        """Get pending changes since a timestamp.

        Args:
            since: Get changes after this timestamp (None = all)

        Returns:
            List of pending changes
        """
        if since is None:
            return list(self._changes)
        return [c for c in self._changes if c.timestamp > since]

    def mark_synced(self, change_ids: list[str]) -> int:
        """Remove synced changes from queue.

        Args:
            change_ids: IDs of successfully synced changes

        Returns:
            Number of changes removed
        """
        before = len(self._changes)
        self._changes = [c for c in self._changes if c.id not in change_ids]
        return before - len(self._changes)

    def clear(self) -> None:
        """Clear all pending changes."""
        self._changes.clear()

    def __len__(self) -> int:
        return len(self._changes)


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
    topology: SyncTopology = SyncTopology.MESH
    conflict_manager: ConflictManager = field(default_factory=ConflictManager)
    change_queue: ChangeQueue = field(default_factory=ChangeQueue)
    sync_timeout: float = 30.0
    delta_sync_enabled: bool = True
    hub_peer_id: str | None = None  # Only used for HUB_SPOKE topology
    _etag_store: dict[str, str] = field(default_factory=dict)  # entity_id -> etag
    _local_data_provider: Callable[[str, str], dict | None] | None = None

    def set_local_data_provider(
        self, provider: Callable[[str, str], dict | None]
    ) -> None:
        """Set callback to get local data for conflict detection.

        Args:
            provider: Function(entity_type, entity_id) -> local_doc or None
        """
        self._local_data_provider = provider

    def track_change(
        self,
        entity_type: str,
        entity_id: str,
        operation: str,
        doc: dict[str, Any] | None = None,
        etag: str | None = None,
    ) -> None:
        """Track a local change for synchronization.

        Args:
            entity_type: Type of entity (aas, submodel, concept_description)
            entity_id: Entity identifier
            operation: Operation performed (create, update, delete)
            doc: Document content (None for delete)
            etag: Entity ETag
        """
        change = SyncChange(
            id=str(uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            doc=doc,
            etag=etag,
        )
        self.change_queue.add(change)

        # Update local etag store
        if etag:
            self._etag_store[f"{entity_type}:{entity_id}"] = etag

    async def sync_once(self) -> dict[str, Any]:
        """Run a single sync cycle with all healthy peers.

        Iterates through healthy peers and syncs data according to mode:
        - PULL: Only pull updates from peers
        - PUSH: Only push local changes to peers
        - BIDIRECTIONAL: Both push and pull

        Returns a summary payload suitable for logging/metrics.
        """
        peers = self._get_sync_peers()
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
            "topology": self.topology.value,
            "peers": len(peers),
            "peers_synced": successful,
            "status": status,
            "pushed": total_pushed,
            "pulled": total_pulled,
            "conflicts": total_conflicts,
            "pending_changes": len(self.change_queue),
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

    def _get_sync_peers(self) -> list[Peer]:
        """Get peers to sync with based on topology.

        Returns:
            List of peers to sync with
        """
        if self.topology == SyncTopology.HUB_SPOKE:
            # In hub-spoke, we only sync with hub (if we're a spoke)
            # or all spokes (if we're the hub)
            if self.hub_peer_id:
                hub = self.registry.get(self.hub_peer_id)
                if hub and hub.is_healthy:
                    return [hub]
                return []
            # We are the hub - sync with all healthy peers
            return self.registry.list_healthy()
        else:
            # Mesh topology - sync with all healthy peers
            return self.registry.list_healthy()

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

        Pushes pending changes from the change queue to the peer.
        Only pushes changes that occurred since the last sync with this peer.

        Args:
            client: HTTP client
            peer: Target peer

        Returns:
            Number of items pushed
        """
        pushed = 0

        # Get changes since last sync (delta sync)
        since = peer.last_sync if self.delta_sync_enabled else None
        changes = self.change_queue.get_pending(since=since)

        if not changes:
            logger.debug(f"No pending changes to push to peer {peer.id}")
            return 0

        logger.debug(f"Pushing {len(changes)} changes to peer {peer.id}")

        synced_ids: list[str] = []

        for change in changes:
            try:
                success = await self._push_single_change(client, peer, change)
                if success:
                    pushed += 1
                    synced_ids.append(change.id)
            except Exception as e:
                logger.warning(f"Failed to push change {change.id} to {peer.id}: {e}")

        # Mark successfully synced changes
        if synced_ids:
            self.change_queue.mark_synced(synced_ids)

        return pushed

    async def _push_single_change(
        self,
        client: httpx.AsyncClient,
        peer: Peer,
        change: SyncChange,
    ) -> bool:
        """Push a single change to a peer.

        Args:
            client: HTTP client
            peer: Target peer
            change: Change to push

        Returns:
            True if successful
        """
        endpoint_map = {
            "aas": "/shells",
            "submodel": "/submodels",
            "concept_description": "/concept-descriptions",
        }

        endpoint = endpoint_map.get(change.entity_type)
        if not endpoint:
            logger.warning(f"Unknown entity type: {change.entity_type}")
            return False

        url = f"{peer.url}{endpoint}"

        try:
            if change.operation == "create":
                response = await client.post(url, json=change.doc)
                # 201 Created or 409 Conflict (already exists) both count as success
                return response.status_code in (201, 409)

            elif change.operation == "update":
                # URL encode the entity ID for path
                entity_url = f"{url}/{_url_encode_id(change.entity_id)}"
                response = await client.put(entity_url, json=change.doc)
                return response.status_code in (200, 204)

            elif change.operation == "delete":
                entity_url = f"{url}/{_url_encode_id(change.entity_id)}"
                response = await client.delete(entity_url)
                # 204 No Content or 404 Not Found both count as success
                return response.status_code in (204, 404)

            else:
                logger.warning(f"Unknown operation: {change.operation}")
                return False

        except Exception as e:
            logger.error(f"Push to {peer.id} failed: {e}")
            return False

    async def _pull_from_peer(
        self, client: httpx.AsyncClient, peer: Peer
    ) -> tuple[int, int]:
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

                for item in items:
                    # Check for conflicts
                    has_conflict = await self._check_and_handle_conflict(
                        peer, entity_type, item
                    )
                    if has_conflict:
                        conflicts += 1
                    else:
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

    async def _check_and_handle_conflict(
        self,
        peer: Peer,
        entity_type: str,
        remote_doc: dict[str, Any],
    ) -> bool:
        """Check if remote document conflicts with local version.

        Args:
            peer: Source peer
            entity_type: Type of entity
            remote_doc: Remote document

        Returns:
            True if conflict was detected
        """
        entity_id = remote_doc.get("id", "")
        remote_etag = _compute_simple_etag(remote_doc)

        # Check if we have a local version
        key = f"{entity_type}:{entity_id}"
        local_etag = self._etag_store.get(key)

        if local_etag is None:
            # No local version - no conflict
            return False

        if local_etag == remote_etag:
            # Same version - no conflict
            return False

        # We have different versions - potential conflict
        # Get local document if provider is available
        local_doc: dict[str, Any] | None = None
        if self._local_data_provider:
            local_doc = self._local_data_provider(entity_type, entity_id)

        if local_doc is None:
            # Can't get local doc - treat as no conflict
            return False

        # Create conflict record
        conflict = ConflictInfo(
            id=str(uuid4()),
            peer_id=peer.id,
            entity_type=entity_type,
            entity_id=entity_id,
            local_doc=local_doc,
            local_etag=local_etag,
            remote_doc=remote_doc,
            remote_etag=remote_etag,
            detected_at=datetime.now(UTC),
        )

        self.conflict_manager.add_conflict(conflict)
        logger.info(
            f"Conflict detected for {entity_type}/{entity_id} "
            f"between local and peer {peer.id}"
        )

        return True

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
            "topology": self.topology.value,
            "delta_sync_enabled": self.delta_sync_enabled,
            "peers_total": len(all_peers),
            "peers_healthy": len(healthy_peers),
            "pending_changes": len(self.change_queue),
            "unresolved_conflicts": len(unresolved),
            "hub_peer_id": self.hub_peer_id,
        }

    def clear_pending_changes(self) -> int:
        """Clear all pending changes from the queue.

        Returns:
            Number of changes cleared
        """
        count = len(self.change_queue)
        self.change_queue.clear()
        return count


def _url_encode_id(entity_id: str) -> str:
    """URL-encode an entity ID using Base64URL.

    Args:
        entity_id: Entity identifier

    Returns:
        Base64URL encoded ID
    """
    import base64

    return base64.urlsafe_b64encode(entity_id.encode()).decode().rstrip("=")


def _compute_simple_etag(doc: dict[str, Any]) -> str:
    """Compute a simple ETag for a document.

    Args:
        doc: Document to hash

    Returns:
        Simple hash string
    """
    import hashlib
    import json

    content = json.dumps(doc, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()[:16]
