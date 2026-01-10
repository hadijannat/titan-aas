"""Catena-X Integration for Titan-AAS.

Enables:
- Eclipse Dataspace Connector (EDC) integration
- Digital Twin Registry (DTR) synchronization
- Usage policy enforcement
- Data sovereignty
"""

from titan.integrations.catenax.connector import CatenaXConnector, CatenaXConfig
from titan.integrations.catenax.registry import DtrClient

__all__ = [
    "CatenaXConnector",
    "CatenaXConfig",
    "DtrClient",
]
