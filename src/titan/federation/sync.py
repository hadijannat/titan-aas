"""Federation synchronization primitives."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from titan.federation.peer import PeerRegistry

logger = logging.getLogger(__name__)


class SyncMode(str, Enum):
    """Synchronization modes."""

    PULL = "pull"
    PUSH = "push"
    BIDIRECTIONAL = "bidirectional"


@dataclass
class FederationSync:
    """Coordinates data synchronization across federated peers.

    This is a minimal scaffold for future federation capabilities.
    """

    registry: PeerRegistry
    mode: SyncMode = SyncMode.PULL

    async def sync_once(self) -> dict[str, Any]:
        """Run a single sync cycle.

        Returns a summary payload suitable for logging/metrics.
        """
        peers = self.registry.list_healthy()
        logger.info("Federation sync started", extra={"peers": len(peers)})
        return {
            "mode": self.mode.value,
            "peers": len(peers),
            "status": "skipped",
            "reason": "federation sync not implemented",
        }
