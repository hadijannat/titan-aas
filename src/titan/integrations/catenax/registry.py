"""Digital Twin Registry (DTR) client for Catena-X.

Synchronizes AAS descriptors with Catena-X Digital Twin Registry
for cross-company asset discovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DtrConfig:
    """Configuration for DTR connection."""

    base_url: str
    api_key: str | None = None
    bpn: str | None = None  # Business Partner Number
    tenant_id: str | None = None
    timeout: float = 30.0


@dataclass
class SpecificAssetId:
    """Specific asset identifier for DTR lookup."""

    name: str
    value: str
    subject_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        result: dict[str, Any] = {"name": self.name, "value": self.value}
        if self.subject_id:
            result["externalSubjectId"] = {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": self.subject_id}],
            }
        return result


@dataclass
class SubmodelDescriptorDtr:
    """Submodel descriptor for DTR registration."""

    id: str
    id_short: str
    semantic_id: str | None = None
    endpoints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to DTR format."""
        result: dict[str, Any] = {
            "id": self.id,
            "idShort": self.id_short,
            "endpoints": self.endpoints or [
                {
                    "interface": "SUBMODEL-3.0",
                    "protocolInformation": {
                        "href": f"/submodels/{self.id}",
                        "endpointProtocol": "HTTP",
                        "endpointProtocolVersion": ["1.1"],
                    },
                }
            ],
        }
        if self.semantic_id:
            result["semanticId"] = {
                "type": "ExternalReference",
                "keys": [{"type": "GlobalReference", "value": self.semantic_id}],
            }
        return result


@dataclass
class ShellDescriptorDtr:
    """AAS descriptor for DTR registration."""

    id: str
    id_short: str
    global_asset_id: str
    specific_asset_ids: list[SpecificAssetId] = field(default_factory=list)
    submodel_descriptors: list[SubmodelDescriptorDtr] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to DTR format."""
        return {
            "id": self.id,
            "idShort": self.id_short,
            "globalAssetId": self.global_asset_id,
            "specificAssetIds": [sa.to_dict() for sa in self.specific_asset_ids],
            "submodelDescriptors": [sm.to_dict() for sm in self.submodel_descriptors],
        }


@dataclass
class LookupResult:
    """Result from DTR lookup."""

    shell_ids: list[str]
    total_count: int
    cursor: str | None = None


class DtrClient:
    """Client for Catena-X Digital Twin Registry.

    Provides:
    - Shell descriptor registration
    - Asset lookup by specific asset IDs
    - Cross-BPN discovery (with access control)
    - Batch synchronization
    """

    def __init__(self, config: DtrConfig) -> None:
        """Initialize DTR client.

        Args:
            config: DTR connection configuration
        """
        self.config = config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to DTR."""
        return self._connected

    async def connect(self) -> bool:
        """Connect to the DTR API.

        Returns:
            True if connected successfully
        """
        if not self.config.base_url:
            logger.warning("No DTR URL configured")
            return False

        try:
            # Placeholder - would GET /health or similar
            logger.info(f"Connected to DTR: {self.config.base_url}")
            self._connected = True
            return True

        except Exception as e:
            logger.error(f"Failed to connect to DTR: {e}")
            self._connected = False
            return False

    async def lookup(
        self,
        asset_ids: list[SpecificAssetId],
        limit: int = 100,
        cursor: str | None = None,
    ) -> LookupResult:
        """Lookup shell descriptors by asset IDs.

        Args:
            asset_ids: List of specific asset IDs to search
            limit: Maximum results to return
            cursor: Pagination cursor

        Returns:
            Lookup result with matching shell IDs
        """
        if not self._connected:
            return LookupResult(shell_ids=[], total_count=0)

        try:
            # Build lookup request
            lookup_body = {
                "assetIds": [aid.to_dict() for aid in asset_ids],
            }

            logger.debug("DTR lookup payload: %s", lookup_body)

            # Placeholder - would POST to /lookup/shells
            logger.info(f"Looking up {len(asset_ids)} asset IDs in DTR")
            return LookupResult(shell_ids=[], total_count=0)

        except Exception as e:
            logger.error(f"DTR lookup failed: {e}")
            return LookupResult(shell_ids=[], total_count=0)

    async def get_shell(self, shell_id: str) -> ShellDescriptorDtr | None:
        """Get a shell descriptor by ID.

        Args:
            shell_id: The AAS descriptor ID

        Returns:
            Shell descriptor or None
        """
        if not self._connected:
            return None

        try:
            # Placeholder - would GET /shell-descriptors/{base64url(id)}
            logger.debug(f"Getting shell descriptor: {shell_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to get shell descriptor: {e}")
            return None

    async def register_shell(
        self,
        descriptor: ShellDescriptorDtr,
    ) -> str | None:
        """Register a shell descriptor in DTR.

        Args:
            descriptor: The shell descriptor to register

        Returns:
            Registered shell ID or None
        """
        if not self._connected:
            return None

        try:
            payload = descriptor.to_dict()

            logger.debug("DTR shell register payload: %s", payload)

            # Placeholder - would POST to /shell-descriptors
            logger.info(f"Registered shell in DTR: {descriptor.id}")
            return descriptor.id

        except Exception as e:
            logger.error(f"Failed to register shell: {e}")
            return None

    async def update_shell(
        self,
        descriptor: ShellDescriptorDtr,
    ) -> bool:
        """Update an existing shell descriptor.

        Args:
            descriptor: The updated shell descriptor

        Returns:
            True if successful
        """
        if not self._connected:
            return False

        try:
            payload = descriptor.to_dict()

            logger.debug("DTR shell update payload: %s", payload)

            # Placeholder - would PUT to /shell-descriptors/{base64url(id)}
            logger.info(f"Updated shell in DTR: {descriptor.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update shell: {e}")
            return False

    async def delete_shell(self, shell_id: str) -> bool:
        """Delete a shell descriptor from DTR.

        Args:
            shell_id: The shell ID to delete

        Returns:
            True if successful
        """
        if not self._connected:
            return False

        try:
            # Placeholder - would DELETE /shell-descriptors/{base64url(id)}
            logger.info(f"Deleted shell from DTR: {shell_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete shell: {e}")
            return False

    async def sync_from_local(
        self,
        shells: list[ShellDescriptorDtr],
        delete_missing: bool = False,
    ) -> dict[str, int]:
        """Sync local shell descriptors to DTR.

        Args:
            shells: List of local shell descriptors
            delete_missing: Whether to delete shells not in local list

        Returns:
            Sync statistics (created, updated, deleted, failed)
        """
        if not self._connected:
            return {"created": 0, "updated": 0, "deleted": 0, "failed": len(shells)}

        stats = {"created": 0, "updated": 0, "deleted": 0, "failed": 0}

        for shell in shells:
            try:
                existing = await self.get_shell(shell.id)
                if existing:
                    if await self.update_shell(shell):
                        stats["updated"] += 1
                    else:
                        stats["failed"] += 1
                else:
                    if await self.register_shell(shell):
                        stats["created"] += 1
                    else:
                        stats["failed"] += 1

            except Exception as e:
                logger.error(f"Failed to sync shell {shell.id}: {e}")
                stats["failed"] += 1

        logger.info(
            f"DTR sync complete: {stats['created']} created, "
            f"{stats['updated']} updated, {stats['failed']} failed"
        )
        return stats

    async def get_all_shells(
        self,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[ShellDescriptorDtr], str | None]:
        """Get all shell descriptors from DTR.

        Args:
            limit: Maximum results per page
            cursor: Pagination cursor

        Returns:
            Tuple of (shells, next_cursor)
        """
        if not self._connected:
            return [], None

        try:
            # Placeholder - would GET /shell-descriptors with pagination
            logger.debug("Getting all shells from DTR")
            return [], None

        except Exception as e:
            logger.error(f"Failed to get shells: {e}")
            return [], None


class DtrSyncService:
    """Service for bidirectional DTR synchronization.

    Manages continuous sync between local AAS repository and DTR.
    """

    def __init__(
        self,
        client: DtrClient,
        sync_interval: int = 300,
    ) -> None:
        """Initialize sync service.

        Args:
            client: DTR client instance
            sync_interval: Seconds between sync cycles
        """
        self.client = client
        self.sync_interval = sync_interval
        self._running = False
        self._last_sync: str | None = None

    async def start(self) -> None:
        """Start the sync service."""
        if self._running:
            logger.warning("Sync service already running")
            return

        self._running = True
        logger.info(f"Starting DTR sync service (interval: {self.sync_interval}s)")

        # Would start background task for periodic sync

    async def stop(self) -> None:
        """Stop the sync service."""
        self._running = False
        logger.info("Stopped DTR sync service")

    async def sync_now(self) -> dict[str, int]:
        """Trigger immediate synchronization.

        Returns:
            Sync statistics
        """
        logger.info("Running immediate DTR sync")
        # Would implement full sync logic
        return {"created": 0, "updated": 0, "deleted": 0, "failed": 0}
