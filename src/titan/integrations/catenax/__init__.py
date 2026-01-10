"""Catena-X Integration for Titan-AAS.

Enables:
- Eclipse Dataspace Connector (EDC) integration
- Digital Twin Registry (DTR) synchronization
- Usage policy enforcement
- Data sovereignty
"""

from titan.integrations.catenax.connector import (
    CatenaXConfig,
    CatenaXConnector,
    ContractOffer,
    PolicyType,
    TransferProcess,
    UsagePolicy,
)
from titan.integrations.catenax.registry import (
    DtrClient,
    DtrConfig,
    DtrSyncService,
    LookupResult,
    ShellDescriptorDtr,
    SpecificAssetId,
    SubmodelDescriptorDtr,
)

__all__ = [
    # Connector
    "CatenaXConnector",
    "CatenaXConfig",
    "ContractOffer",
    "PolicyType",
    "TransferProcess",
    "UsagePolicy",
    # Registry
    "DtrClient",
    "DtrConfig",
    "DtrSyncService",
    "LookupResult",
    "ShellDescriptorDtr",
    "SpecificAssetId",
    "SubmodelDescriptorDtr",
]
