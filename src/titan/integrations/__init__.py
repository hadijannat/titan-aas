"""External ecosystem integrations for Titan-AAS.

Provides connectors for:
- Catena-X (EDC, Digital Twin Registry)
- Digital Product Passports (Battery, Carbon Footprint)
"""

from titan.integrations.catenax import (
    CatenaXConfig,
    CatenaXConnector,
    DtrClient,
    DtrConfig,
    PolicyType,
    UsagePolicy,
)
from titan.integrations.dpp import (
    DppGenerator,
    DppType,
    PassportData,
    QrCodeGenerator,
)

__all__ = [
    # Catena-X
    "CatenaXConfig",
    "CatenaXConnector",
    "DtrClient",
    "DtrConfig",
    "UsagePolicy",
    "PolicyType",
    # Digital Product Passport
    "DppGenerator",
    "DppType",
    "PassportData",
    "QrCodeGenerator",
]
