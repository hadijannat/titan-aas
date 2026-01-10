"""Edge deployment support for Titan-AAS.

Enables:
- Offline-first operation
- Background sync when connected
- Delta-only sync (bandwidth optimization)
- Conflict queue for disconnected updates
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """Network connection state."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    LIMITED = "limited"  # Connected but with constraints


class SyncPriority(str, Enum):
    """Priority for pending sync items."""

    HIGH = "high"  # Sync immediately when connected
    NORMAL = "normal"  # Sync in next batch
    LOW = "low"  # Sync when bandwidth available


@dataclass
class PendingChange:
    """A change waiting to be synced to hub."""

    id: str
    entity_type: str
    entity_id: str
    action: str  # "create", "update", "delete"
    data: bytes | None = None
    etag: str | None = None
    priority: SyncPriority = SyncPriority.NORMAL
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    attempts: int = 0
    last_error: str | None = None


@dataclass
class EdgeConfig:
    """Configuration for edge deployment."""

    hub_url: str | None = None
    sync_interval: int = 60  # seconds
    max_offline_queue: int = 1000
    bandwidth_limit: int | None = None  # bytes per sync
    retry_attempts: int = 3
    auto_reconnect: bool = True
    reconnect_delay: int = 10  # seconds


@dataclass
class EdgeStatus:
    """Current status of edge node."""

    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    hub_url: str | None = None
    last_sync: datetime | None = None
    pending_changes: int = 0
    conflicts: int = 0
    bytes_pending: int = 0


class EdgeController:
    """Controls edge deployment behavior."""

    def __init__(self, config: EdgeConfig | None = None) -> None:
        """Initialize edge controller.

        Args:
            config: Edge deployment configuration
        """
        self.config = config or EdgeConfig()
        self._connection_state = ConnectionState.DISCONNECTED
        self._pending_queue: list[PendingChange] = []
        self._conflict_queue: list[dict[str, Any]] = []
        self._sync_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._last_sync: datetime | None = None
        self._last_sync_cursor: str | None = None

    @property
    def status(self) -> EdgeStatus:
        """Get current edge status."""
        return EdgeStatus(
            connection_state=self._connection_state,
            hub_url=self.config.hub_url,
            last_sync=self._last_sync,
            pending_changes=len(self._pending_queue),
            conflicts=len(self._conflict_queue),
            bytes_pending=sum(len(c.data or b"") for c in self._pending_queue),
        )

    @property
    def is_connected(self) -> bool:
        """Check if connected to hub."""
        return self._connection_state == ConnectionState.CONNECTED

    async def start(self) -> None:
        """Start edge controller."""
        if self.config.hub_url:
            await self._connect()
        logger.info("Edge controller started")

    async def stop(self) -> None:
        """Stop edge controller."""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        logger.info("Edge controller stopped")

    async def queue_change(self, change: PendingChange) -> None:
        """Queue a change for sync to hub.

        Args:
            change: The change to queue
        """
        if len(self._pending_queue) >= self.config.max_offline_queue:
            # Remove oldest low-priority items
            low_priority = [c for c in self._pending_queue if c.priority == SyncPriority.LOW]
            if low_priority:
                self._pending_queue.remove(low_priority[0])
                logger.warning("Dropped oldest low-priority change from queue")
            else:
                logger.warning("Pending queue full, cannot add change")
                return

        self._pending_queue.append(change)
        logger.debug(f"Queued change: {change.entity_type}/{change.entity_id}")

        # If connected and high priority, trigger immediate sync
        if self.is_connected and change.priority == SyncPriority.HIGH:
            asyncio.create_task(self._sync_high_priority())

    async def sync_now(self) -> dict[str, Any]:
        """Trigger immediate sync with hub.

        Returns:
            Sync result summary
        """
        if not self.is_connected:
            return {"success": False, "error": "Not connected to hub"}

        return await self._sync_to_hub()

    def get_pending_changes(self) -> list[PendingChange]:
        """Get all pending changes."""
        return self._pending_queue.copy()

    def get_conflicts(self) -> list[dict[str, Any]]:
        """Get pending conflicts."""
        return self._conflict_queue.copy()

    def clear_pending(self) -> int:
        """Clear all pending changes.

        Returns:
            Number of cleared changes
        """
        count = len(self._pending_queue)
        self._pending_queue.clear()
        return count

    async def _connect(self) -> bool:
        """Attempt to connect to hub."""
        if not self.config.hub_url:
            return False

        self._connection_state = ConnectionState.CONNECTING
        logger.info(f"Connecting to hub: {self.config.hub_url}")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.config.hub_url}/health/ready")
                if response.status_code == 200:
                    self._connection_state = ConnectionState.CONNECTED
                    logger.info("Connected to hub")

                    # Start sync loop
                    self._sync_task = asyncio.create_task(self._sync_loop())
                    return True

        except Exception as e:
            logger.error(f"Failed to connect to hub: {e}")

        self._connection_state = ConnectionState.DISCONNECTED

        if self.config.auto_reconnect:
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        return False

    async def _reconnect_loop(self) -> None:
        """Background reconnection loop."""
        while self._connection_state == ConnectionState.DISCONNECTED:
            try:
                await asyncio.sleep(self.config.reconnect_delay)
                if await self._connect():
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconnect error: {e}")

    async def _sync_loop(self) -> None:
        """Background sync loop."""
        while self._connection_state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self.config.sync_interval)
                await self._sync_to_hub()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                self._connection_state = ConnectionState.DISCONNECTED
                if self.config.auto_reconnect:
                    self._reconnect_task = asyncio.create_task(self._reconnect_loop())
                break

    async def _sync_to_hub(self) -> dict[str, Any]:
        """Sync pending changes to hub."""
        if not self.config.hub_url:
            return {"success": False, "error": "No hub configured"}

        result = {"pushed": 0, "pulled": 0, "errors": []}

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Push pending changes
                pushed_ids = []
                for change in self._pending_queue[:]:
                    if change.attempts >= self.config.retry_attempts:
                        continue

                    try:
                        success = await self._push_change(client, change)
                        if success:
                            pushed_ids.append(change.id)
                            result["pushed"] += 1
                        else:
                            change.attempts += 1
                    except Exception as e:
                        change.attempts += 1
                        change.last_error = str(e)
                        result["errors"].append(str(e))

                # Remove successfully pushed changes
                self._pending_queue = [c for c in self._pending_queue if c.id not in pushed_ids]

                # Pull updates from hub (delta sync)
                pulled = await self._pull_from_hub(client)
                result["pulled"] = pulled

                self._last_sync = datetime.now(UTC)

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"Sync to hub failed: {e}")

        return result

    async def _push_change(self, client: Any, change: PendingChange) -> bool:
        """Push a single change to hub."""
        if not self.config.hub_url or not change.data:
            return False

        endpoint = f"{self.config.hub_url}"
        if change.entity_type == "aas":
            endpoint += "/shells"
        elif change.entity_type == "submodel":
            endpoint += "/submodels"
        else:
            return False

        if change.action == "create":
            response = await client.post(
                endpoint,
                content=change.data,
                headers={"Content-Type": "application/json"},
            )
        elif change.action == "update":
            import base64

            encoded = base64.urlsafe_b64encode(change.entity_id.encode()).decode().rstrip("=")
            response = await client.put(
                f"{endpoint}/{encoded}",
                content=change.data,
                headers={"Content-Type": "application/json"},
            )
        elif change.action == "delete":
            import base64

            encoded = base64.urlsafe_b64encode(change.entity_id.encode()).decode().rstrip("=")
            response = await client.delete(f"{endpoint}/{encoded}")
        else:
            return False

        return response.status_code in (200, 201, 204)

    async def _pull_from_hub(self, client: Any) -> int:
        """Pull updates from hub using cursor-based delta sync.

        Fetches new/updated entities since last sync cursor.
        Detects conflicts when local and remote versions differ.

        Returns:
            Number of items pulled
        """
        if not self.config.hub_url:
            return 0

        total_pulled = 0

        # Pull shells
        shells_pulled = await self._pull_entity_type(client, "aas", "/shells")
        total_pulled += shells_pulled

        # Pull submodels
        submodels_pulled = await self._pull_entity_type(client, "submodel", "/submodels")
        total_pulled += submodels_pulled

        return total_pulled

    async def _pull_entity_type(
        self, client: Any, entity_type: str, endpoint: str
    ) -> int:
        """Pull a specific entity type from hub.

        Args:
            client: HTTP client
            entity_type: Type of entity (aas, submodel)
            endpoint: API endpoint path

        Returns:
            Number of items pulled
        """
        if not self.config.hub_url:
            return 0

        pulled = 0
        cursor = self._get_sync_cursor(entity_type)
        url = f"{self.config.hub_url}{endpoint}"

        try:
            while True:
                # Build query with cursor pagination
                params: dict[str, Any] = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.error(
                        f"Failed to pull {entity_type}: {response.status_code}"
                    )
                    break

                data = response.json()
                items = data.get("result", [])

                if not items:
                    break

                for item in items:
                    try:
                        await self._process_pulled_item(entity_type, item)
                        pulled += 1
                    except Exception as e:
                        logger.error(f"Error processing {entity_type} item: {e}")

                # Update cursor for next page
                paging = data.get("paging_metadata", {})
                next_cursor = paging.get("cursor")

                if next_cursor:
                    cursor = next_cursor
                    self._set_sync_cursor(entity_type, cursor)
                else:
                    # No more pages
                    break

        except Exception as e:
            logger.error(f"Pull {entity_type} failed: {e}")

        return pulled

    async def _process_pulled_item(
        self, entity_type: str, item: dict[str, Any]
    ) -> None:
        """Process a single pulled item.

        Checks for conflicts and either applies update or queues conflict.

        Args:
            entity_type: Type of entity
            item: The pulled item data
        """
        item_id = item.get("id", "")
        remote_etag = item.get("_etag", "")  # May be in response headers

        # Check if we have a local version
        local_item = await self._get_local_item(entity_type, item_id)

        if local_item is None:
            # New item - apply directly
            await self._apply_pulled_item(entity_type, item)
            logger.debug(f"Applied new {entity_type}: {item_id}")
        else:
            local_etag = local_item.get("_etag", "")

            if local_etag == remote_etag:
                # Same version - no update needed
                pass
            elif local_etag and remote_etag and local_etag != remote_etag:
                # Conflict detected
                await self._handle_conflict(
                    entity_type=entity_type,
                    entity_id=item_id,
                    local_doc=local_item,
                    local_etag=local_etag,
                    remote_doc=item,
                    remote_etag=remote_etag,
                )
            else:
                # No local etag or no conflict - apply update
                await self._apply_pulled_item(entity_type, item)
                logger.debug(f"Applied update {entity_type}: {item_id}")

    async def _get_local_item(
        self, entity_type: str, item_id: str
    ) -> dict[str, Any] | None:
        """Get local version of an item.

        Args:
            entity_type: Type of entity
            item_id: Entity identifier

        Returns:
            Local item data or None if not found
        """
        # This is a stub - actual implementation requires repository access
        # In production, this would query the local database
        return None

    async def _apply_pulled_item(
        self, entity_type: str, item: dict[str, Any]
    ) -> None:
        """Apply a pulled item to local storage.

        Args:
            entity_type: Type of entity
            item: Item data to apply
        """
        # This is a stub - actual implementation requires repository access
        # In production, this would upsert to the local database
        pass

    async def _handle_conflict(
        self,
        entity_type: str,
        entity_id: str,
        local_doc: dict[str, Any],
        local_etag: str,
        remote_doc: dict[str, Any],
        remote_etag: str,
    ) -> None:
        """Handle a sync conflict.

        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            local_doc: Local version
            local_etag: Local ETag
            remote_doc: Remote version
            remote_etag: Remote ETag
        """
        conflict = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "local_doc": local_doc,
            "local_etag": local_etag,
            "remote_doc": remote_doc,
            "remote_etag": remote_etag,
            "detected_at": datetime.now(UTC).isoformat(),
        }
        self._conflict_queue.append(conflict)
        logger.warning(
            f"Conflict detected for {entity_type}/{entity_id}: "
            f"local={local_etag[:8]}... remote={remote_etag[:8]}..."
        )

    def _get_sync_cursor(self, entity_type: str) -> str | None:
        """Get sync cursor for entity type.

        Args:
            entity_type: Type of entity

        Returns:
            Cursor string or None
        """
        # For now, use in-memory cursor
        # In production, this would read from federation_sync_state table
        if entity_type == "aas":
            return getattr(self, "_aas_cursor", None)
        elif entity_type == "submodel":
            return getattr(self, "_submodel_cursor", None)
        return None

    def _set_sync_cursor(self, entity_type: str, cursor: str) -> None:
        """Set sync cursor for entity type.

        Args:
            entity_type: Type of entity
            cursor: Cursor string
        """
        # For now, use in-memory cursor
        # In production, this would update federation_sync_state table
        if entity_type == "aas":
            self._aas_cursor = cursor
        elif entity_type == "submodel":
            self._submodel_cursor = cursor
        self._last_sync_cursor = cursor

    async def _sync_high_priority(self) -> None:
        """Sync only high-priority items."""
        high_priority = [c for c in self._pending_queue if c.priority == SyncPriority.HIGH]
        if not high_priority:
            return

        logger.debug(f"Syncing {len(high_priority)} high-priority changes")
        await self._sync_to_hub()
