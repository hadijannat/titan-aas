"""Federation module for Titan-AAS.

Enables multi-instance deployment with:
- Peer-to-peer sync
- Cross-instance discovery
- Edge deployment support
- Conflict resolution
"""

from titan.federation.conflicts import (
    ConflictInfo,
    ConflictManager,
    ConflictResolver,
    ResolutionResult,
    ResolutionStrategy,
)
from titan.federation.discovery import FederatedDiscovery
from titan.federation.edge import EdgeConfig, EdgeController, EdgeStatus
from titan.federation.peer import Peer, PeerRegistry
from titan.federation.sync import (
    ChangeQueue,
    FederationSync,
    SyncChange,
    SyncMode,
    SyncTopology,
)

__all__ = [
    "ChangeQueue",
    "ConflictInfo",
    "ConflictManager",
    "ConflictResolver",
    "EdgeConfig",
    "EdgeController",
    "EdgeStatus",
    "FederatedDiscovery",
    "FederationSync",
    "Peer",
    "PeerRegistry",
    "ResolutionResult",
    "ResolutionStrategy",
    "SyncChange",
    "SyncMode",
    "SyncTopology",
]
