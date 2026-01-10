"""OPC UA Connector for Titan-AAS.

Enables:
- Reading AAS from OPC UA servers
- Exposing AAS as OPC UA information model
- Real-time subscriptions
- NodeId <-> idShortPath mapping
"""

from titan.connectors.opcua.client import OpcUaClient, OpcUaConfig
from titan.connectors.opcua.mapping import AasOpcUaMapper

__all__ = [
    "OpcUaClient",
    "OpcUaConfig",
    "AasOpcUaMapper",
]
