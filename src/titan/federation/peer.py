"""Peer management for federation.

Handles:
- Peer registration and discovery
- Health monitoring
- Capability exchange
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PeerStatus(str, Enum):
    """Status of a federated peer."""

    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class PeerCapabilities:
    """Capabilities advertised by a peer."""

    aas_repository: bool = True
    submodel_repository: bool = True
    aas_registry: bool = False
    submodel_registry: bool = False
    aasx_server: bool = False
    read_only: bool = False
    max_payload_size: int = 10 * 1024 * 1024  # 10MB default


@dataclass
class Peer:
    """A federated Titan-AAS instance."""

    id: str
    url: str
    name: str | None = None
    status: PeerStatus = PeerStatus.UNKNOWN
    capabilities: PeerCapabilities = field(default_factory=PeerCapabilities)
    last_seen: datetime | None = None
    last_sync: datetime | None = None
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        """Check if peer is healthy."""
        return self.status == PeerStatus.ONLINE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "url": self.url,
            "name": self.name,
            "status": self.status.value,
            "capabilities": {
                "aasRepository": self.capabilities.aas_repository,
                "submodelRepository": self.capabilities.submodel_repository,
                "aasRegistry": self.capabilities.aas_registry,
                "submodelRegistry": self.capabilities.submodel_registry,
                "aasxServer": self.capabilities.aasx_server,
                "readOnly": self.capabilities.read_only,
            },
            "lastSeen": self.last_seen.isoformat() if self.last_seen else None,
            "lastSync": self.last_sync.isoformat() if self.last_sync else None,
            "version": self.version,
        }


class PeerRegistry:
    """Registry of federated peers."""

    def __init__(self) -> None:
        """Initialize peer registry."""
        self._peers: dict[str, Peer] = {}
        self._client: httpx.AsyncClient | None = None
        self._health_check_interval = 30  # seconds
        self._health_check_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the peer registry."""
        self._client = httpx.AsyncClient(timeout=10.0)
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Peer registry started")

    async def stop(self) -> None:
        """Stop the peer registry."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.aclose()

        logger.info("Peer registry stopped")

    def register(self, peer: Peer) -> None:
        """Register a peer."""
        self._peers[peer.id] = peer
        logger.info(f"Registered peer: {peer.id} at {peer.url}")

    def unregister(self, peer_id: str) -> bool:
        """Unregister a peer."""
        if peer_id in self._peers:
            del self._peers[peer_id]
            logger.info(f"Unregistered peer: {peer_id}")
            return True
        return False

    def get(self, peer_id: str) -> Peer | None:
        """Get a peer by ID."""
        return self._peers.get(peer_id)

    def list_all(self) -> list[Peer]:
        """List all registered peers."""
        return list(self._peers.values())

    def list_healthy(self) -> list[Peer]:
        """List all healthy peers."""
        return [p for p in self._peers.values() if p.is_healthy]

    async def check_health(self, peer: Peer) -> PeerStatus:
        """Check health of a specific peer."""
        if not self._client:
            return PeerStatus.UNKNOWN

        try:
            response = await self._client.get(f"{peer.url}/health/ready")
            if response.status_code == 200:
                peer.status = PeerStatus.ONLINE
                peer.last_seen = datetime.now(UTC)

                # Try to get version info
                try:
                    info = response.json()
                    peer.version = info.get("version")
                except Exception:
                    pass
            else:
                peer.status = PeerStatus.DEGRADED

        except httpx.TimeoutException:
            peer.status = PeerStatus.OFFLINE
            logger.warning(f"Peer {peer.id} timed out")
        except httpx.RequestError as e:
            peer.status = PeerStatus.OFFLINE
            logger.warning(f"Peer {peer.id} unreachable: {e}")

        return peer.status

    async def check_all_health(self) -> dict[str, PeerStatus]:
        """Check health of all peers."""
        results = {}
        for peer in self._peers.values():
            results[peer.id] = await self.check_health(peer)
        return results

    async def discover_capabilities(self, peer: Peer) -> PeerCapabilities:
        """Discover capabilities of a peer."""
        if not self._client:
            return peer.capabilities

        try:
            # Check OpenAPI spec for available endpoints
            response = await self._client.get(f"{peer.url}/openapi.json")
            if response.status_code == 200:
                spec = response.json()
                paths = spec.get("paths", {})

                caps = PeerCapabilities()
                caps.aas_repository = "/shells" in paths
                caps.submodel_repository = "/submodels" in paths
                caps.aas_registry = "/shell-descriptors" in paths
                caps.submodel_registry = "/submodel-descriptors" in paths
                caps.aasx_server = "/packages" in paths

                peer.capabilities = caps

        except Exception as e:
            logger.warning(f"Failed to discover capabilities for {peer.id}: {e}")

        return peer.capabilities

    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self.check_all_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
