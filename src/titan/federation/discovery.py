"""Federated discovery for cross-instance queries.

Enables:
- Distributed asset discovery
- Cross-instance search
- Result aggregation
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from titan.federation.peer import Peer, PeerRegistry

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """Result from a federated discovery query."""

    items: list[dict[str, Any]] = field(default_factory=list)
    sources: dict[str, int] = field(default_factory=dict)  # peer_id -> count
    total: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0


@dataclass
class FederatedQuery:
    """A query to execute across peers."""

    entity_type: str  # "aas", "submodel", "descriptor"
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 100
    include_local: bool = True
    timeout: float = 10.0


class FederatedDiscovery:
    """Enables cross-instance discovery and search."""

    def __init__(
        self,
        peer_registry: PeerRegistry,
        local_query_fn: Any = None,
    ) -> None:
        """Initialize federated discovery.

        Args:
            peer_registry: Registry of federated peers
            local_query_fn: Function to query local instance
        """
        self.peer_registry = peer_registry
        self.local_query_fn = local_query_fn
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Start discovery service."""
        self._client = httpx.AsyncClient(timeout=10.0)
        logger.info("Federated discovery started")

    async def stop(self) -> None:
        """Stop discovery service."""
        if self._client:
            await self._client.aclose()
        logger.info("Federated discovery stopped")

    async def discover_shells(
        self,
        global_asset_id: str | None = None,
        asset_kind: str | None = None,
        id_short: str | None = None,
        limit: int = 100,
        include_local: bool = True,
    ) -> DiscoveryResult:
        """Discover AAS across all federated instances.

        Args:
            global_asset_id: Filter by global asset ID
            asset_kind: Filter by asset kind (Instance/Template)
            id_short: Filter by idShort
            limit: Maximum results per peer
            include_local: Include local results

        Returns:
            Aggregated discovery results
        """
        query = FederatedQuery(
            entity_type="aas",
            filters={
                "globalAssetId": global_asset_id,
                "assetKind": asset_kind,
                "idShort": id_short,
            },
            limit=limit,
            include_local=include_local,
        )
        return await self._execute_query(query, "/shells")

    async def discover_submodels(
        self,
        semantic_id: str | None = None,
        id_short: str | None = None,
        kind: str | None = None,
        limit: int = 100,
        include_local: bool = True,
    ) -> DiscoveryResult:
        """Discover Submodels across all federated instances.

        Args:
            semantic_id: Filter by semantic ID
            id_short: Filter by idShort
            kind: Filter by kind (Instance/Template)
            limit: Maximum results per peer

        Returns:
            Aggregated discovery results
        """
        query = FederatedQuery(
            entity_type="submodel",
            filters={
                "semanticId": semantic_id,
                "idShort": id_short,
                "kind": kind,
            },
            limit=limit,
            include_local=include_local,
        )
        return await self._execute_query(query, "/submodels")

    async def discover_by_asset(
        self,
        global_asset_id: str,
        limit: int = 100,
    ) -> DiscoveryResult:
        """Find all AAS and Submodels related to an asset.

        Args:
            global_asset_id: The asset's global ID
            limit: Maximum results

        Returns:
            All related entities
        """
        start_time = datetime.now(timezone.utc)
        result = DiscoveryResult()

        # Find AAS with this asset
        shells_result = await self.discover_shells(
            global_asset_id=global_asset_id,
            limit=limit,
        )
        result.items.extend(shells_result.items)
        result.sources.update(shells_result.sources)
        result.errors.extend(shells_result.errors)

        # Could extend to find submodels referenced by those AAS
        # For now, just return the shells

        result.total = len(result.items)
        result.duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        return result

    async def lookup_identifier(
        self,
        identifier: str,
        entity_type: str = "any",
    ) -> DiscoveryResult:
        """Look up an entity by identifier across all peers.

        Args:
            identifier: The entity identifier
            entity_type: "aas", "submodel", or "any"

        Returns:
            Matching entities
        """
        start_time = datetime.now(timezone.utc)
        result = DiscoveryResult()

        peers = self.peer_registry.list_healthy()
        tasks = []

        for peer in peers:
            if entity_type in ("aas", "any"):
                tasks.append(self._lookup_at_peer(peer, "/shells", identifier))
            if entity_type in ("submodel", "any"):
                tasks.append(self._lookup_at_peer(peer, "/submodels", identifier))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for response in responses:
            if isinstance(response, Exception):
                result.errors.append(str(response))
            elif response:
                result.items.append(response)

        result.total = len(result.items)
        result.duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        return result

    async def _execute_query(
        self,
        query: FederatedQuery,
        endpoint: str,
    ) -> DiscoveryResult:
        """Execute a query across all peers."""
        start_time = datetime.now(timezone.utc)
        result = DiscoveryResult()

        if not self._client:
            result.errors.append("Client not initialized")
            return result

        # Build query params
        params = {k: v for k, v in query.filters.items() if v is not None}
        params["limit"] = query.limit

        # Query all healthy peers in parallel
        peers = self.peer_registry.list_healthy()
        tasks = [
            self._query_peer(peer, endpoint, params)
            for peer in peers
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        for peer, response in zip(peers, responses):
            if isinstance(response, Exception):
                result.errors.append(f"{peer.id}: {response}")
            elif response:
                items = response.get("result", [])
                result.items.extend(items)
                result.sources[peer.id] = len(items)

        # Deduplicate by ID
        seen_ids = set()
        unique_items = []
        for item in result.items:
            item_id = item.get("id")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                unique_items.append(item)

        result.items = unique_items
        result.total = len(result.items)
        result.duration_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000

        return result

    async def _query_peer(
        self,
        peer: Peer,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Query a single peer."""
        if not self._client:
            return None

        try:
            response = await self._client.get(
                f"{peer.url}{endpoint}",
                params=params,
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"Query to {peer.id} failed: {e}")
            raise

        return None

    async def _lookup_at_peer(
        self,
        peer: Peer,
        endpoint: str,
        identifier: str,
    ) -> dict[str, Any] | None:
        """Look up a specific entity at a peer."""
        if not self._client:
            return None

        # Base64URL encode the identifier
        import base64

        encoded = base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")

        try:
            response = await self._client.get(f"{peer.url}{endpoint}/{encoded}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.debug(f"Lookup at {peer.id} failed: {e}")

        return None
