"""Federation module for Titan-AAS.

Enables multi-instance deployment with:
- Peer-to-peer sync
- Cross-instance discovery
- Edge deployment support
- Conflict resolution
"""

from titan.federation.peer import Peer, PeerRegistry
from titan.federation.sync import FederationSync, SyncMode
from titan.federation.discovery import FederatedDiscovery

__all__ = [
    "Peer",
    "PeerRegistry",
    "FederationSync",
    "SyncMode",
    "FederatedDiscovery",
]
