"""Catena-X Eclipse Dataspace Connector (EDC) integration.

Provides connectivity to Catena-X dataspace for secure data exchange
with usage policy enforcement and data sovereignty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PolicyType(str, Enum):
    """Standard Catena-X usage policy types."""

    UNRESTRICTED = "idsc:BASE_CONNECTOR_POLICY"
    MEMBERSHIP = "Membership"
    FRAMEWORK_AGREEMENT = "FrameworkAgreement"
    DISMANTLER = "Dismantler"
    PURPOSE = "Purpose"
    DURATION = "Duration"


@dataclass
class UsagePolicy:
    """Usage policy for data exchange."""

    policy_type: PolicyType
    constraints: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    prohibitions: list[str] = field(default_factory=list)

    def to_odrl(self) -> dict[str, Any]:
        """Convert to ODRL policy format.

        Returns:
            ODRL-compliant policy dictionary
        """
        return {
            "@type": "odrl:Set",
            "odrl:permission": [
                {
                    "odrl:action": {"odrl:type": "USE"},
                    "odrl:constraint": [
                        {
                            "odrl:leftOperand": k,
                            "odrl:operator": {"@id": "odrl:eq"},
                            "odrl:rightOperand": v,
                        }
                        for k, v in self.constraints.items()
                    ],
                }
            ],
            "odrl:prohibition": [{"odrl:action": {"odrl:type": p}} for p in self.prohibitions],
        }


@dataclass
class CatenaXConfig:
    """Configuration for Catena-X integration."""

    edc_management_url: str | None = None
    edc_protocol_url: str | None = None
    edc_api_key: str | None = None
    dtr_url: str | None = None
    bpn: str | None = None  # Business Partner Number
    connector_id: str | None = None
    timeout: float = 30.0


@dataclass
class ContractOffer:
    """EDC contract offer for data exchange."""

    offer_id: str
    asset_id: str
    policy: UsagePolicy
    provider_bpn: str
    valid_until: str | None = None


@dataclass
class TransferProcess:
    """Status of a data transfer."""

    transfer_id: str
    state: str
    asset_id: str
    connector_address: str
    error_message: str | None = None


class CatenaXConnector:
    """Connector for Catena-X dataspace integration.

    Provides:
    - Asset registration and discovery
    - Contract negotiation
    - Data transfer with policy enforcement
    - Digital Twin Registry synchronization
    """

    def __init__(self, config: CatenaXConfig) -> None:
        """Initialize Catena-X connector.

        Args:
            config: Connection configuration
        """
        self.config = config
        self._connected = False
        self._contracts: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        """Check if connected to EDC."""
        return self._connected

    async def connect(self) -> bool:
        """Connect to the EDC management API.

        Returns:
            True if connected successfully
        """
        if not self.config.edc_management_url:
            logger.warning("No EDC management URL configured")
            return False

        try:
            # Placeholder - would make HTTP request to EDC health endpoint
            logger.info(f"Connecting to EDC: {self.config.edc_management_url}")
            self._connected = True
            return True

        except Exception as e:
            logger.error(f"Failed to connect to EDC: {e}")
            self._connected = False
            return False

    async def health(self) -> dict[str, Any]:
        """Check connector health status.

        Returns:
            Health status dictionary
        """
        return {
            "status": "healthy" if self._connected else "disconnected",
            "edc_configured": bool(self.config.edc_management_url),
            "dtr_configured": bool(self.config.dtr_url),
            "bpn": self.config.bpn,
        }

    async def register_asset(
        self,
        asset_id: str,
        name: str,
        description: str,
        content_type: str = "application/json",
        policy: UsagePolicy | None = None,
    ) -> str | None:
        """Register an asset in the EDC catalog.

        Args:
            asset_id: Unique asset identifier
            name: Human-readable name
            description: Asset description
            content_type: MIME type of the asset
            policy: Usage policy (default: unrestricted)

        Returns:
            Asset ID if successful, None otherwise
        """
        if not self._connected:
            logger.warning("Not connected to EDC")
            return None

        try:
            policy = policy or UsagePolicy(policy_type=PolicyType.UNRESTRICTED)

            # EDC asset creation payload
            asset_payload = {
                "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
                "@type": "Asset",
                "@id": asset_id,
                "properties": {
                    "name": name,
                    "description": description,
                    "contenttype": content_type,
                },
                "dataAddress": {
                    "@type": "DataAddress",
                    "type": "HttpData",
                    "baseUrl": f"{self.config.edc_protocol_url}/data/{asset_id}",
                },
            }

            logger.debug("EDC asset payload: %s", asset_payload)

            # Placeholder - would POST to EDC /v3/assets
            logger.info(f"Registered asset: {asset_id}")
            return asset_id

        except Exception as e:
            logger.error(f"Failed to register asset: {e}")
            return None

    async def create_contract_definition(
        self,
        asset_id: str,
        policy: UsagePolicy,
        validity_seconds: int = 86400,
    ) -> str | None:
        """Create a contract definition for an asset.

        Args:
            asset_id: The asset to create contract for
            policy: Usage policy to apply
            validity_seconds: How long the contract is valid

        Returns:
            Contract definition ID if successful
        """
        if not self._connected:
            return None

        try:
            contract_id = f"contract-{asset_id}"

            contract_payload = {
                "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
                "@type": "ContractDefinition",
                "@id": contract_id,
                "accessPolicyId": f"policy-{asset_id}",
                "contractPolicyId": f"policy-{asset_id}",
                "assetsSelector": {"operandLeft": "id", "operator": "=", "operandRight": asset_id},
            }

            logger.debug("EDC contract payload: %s", contract_payload)

            # Placeholder - would POST to EDC /v3/contractdefinitions
            logger.info(f"Created contract definition: {contract_id}")
            return contract_id

        except Exception as e:
            logger.error(f"Failed to create contract definition: {e}")
            return None

    async def query_catalog(
        self,
        provider_url: str,
        filter_expression: dict[str, Any] | None = None,
    ) -> list[ContractOffer]:
        """Query another EDC's catalog.

        Args:
            provider_url: Provider's protocol endpoint
            filter_expression: Optional filter criteria

        Returns:
            List of available contract offers
        """
        if not self._connected:
            return []

        try:
            catalog_request = {
                "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
                "@type": "CatalogRequest",
                "counterPartyAddress": provider_url,
                "protocol": "dataspace-protocol-http",
            }

            if filter_expression:
                catalog_request["querySpec"] = {"filterExpression": [filter_expression]}

            # Placeholder - would POST to EDC /v3/catalog/request
            logger.info(f"Queried catalog at: {provider_url}")
            return []

        except Exception as e:
            logger.error(f"Failed to query catalog: {e}")
            return []

    async def negotiate_contract(
        self,
        offer: ContractOffer,
        provider_url: str,
    ) -> str | None:
        """Initiate contract negotiation.

        Args:
            offer: The contract offer to negotiate
            provider_url: Provider's protocol endpoint

        Returns:
            Contract agreement ID if successful
        """
        if not self._connected:
            return None

        try:
            negotiation_request = {
                "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
                "@type": "ContractRequest",
                "counterPartyAddress": provider_url,
                "protocol": "dataspace-protocol-http",
                "policy": offer.policy.to_odrl(),
            }

            logger.debug("EDC negotiation request: %s", negotiation_request)

            # Placeholder - would POST to EDC /v3/contractnegotiations
            agreement_id = f"agreement-{offer.offer_id}"
            self._contracts[agreement_id] = offer

            logger.info(f"Negotiated contract: {agreement_id}")
            return agreement_id

        except Exception as e:
            logger.error(f"Contract negotiation failed: {e}")
            return None

    async def initiate_transfer(
        self,
        agreement_id: str,
        destination: str,
    ) -> TransferProcess | None:
        """Start data transfer after contract agreement.

        Args:
            agreement_id: The contract agreement ID
            destination: Where to send the data

        Returns:
            Transfer process status
        """
        if not self._connected:
            return None

        if agreement_id not in self._contracts:
            logger.error(f"Unknown contract agreement: {agreement_id}")
            return None

        try:
            transfer_request = {
                "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
                "@type": "TransferRequest",
                "contractId": agreement_id,
                "dataDestination": {
                    "@type": "DataAddress",
                    "type": "HttpData",
                    "baseUrl": destination,
                },
                "protocol": "dataspace-protocol-http",
            }

            logger.debug("EDC transfer request: %s", transfer_request)

            # Placeholder - would POST to EDC /v3/transferprocesses
            transfer_id = f"transfer-{agreement_id}"

            logger.info(f"Initiated transfer: {transfer_id}")
            return TransferProcess(
                transfer_id=transfer_id,
                state="STARTED",
                asset_id=self._contracts[agreement_id].asset_id,
                connector_address=destination,
            )

        except Exception as e:
            logger.error(f"Failed to initiate transfer: {e}")
            return None

    async def get_transfer_status(self, transfer_id: str) -> TransferProcess | None:
        """Get the status of a transfer process.

        Args:
            transfer_id: The transfer process ID

        Returns:
            Current transfer status
        """
        if not self._connected:
            return None

        try:
            # Placeholder - would GET from EDC /v3/transferprocesses/{id}
            return TransferProcess(
                transfer_id=transfer_id,
                state="COMPLETED",
                asset_id="unknown",
                connector_address="",
            )

        except Exception as e:
            logger.error(f"Failed to get transfer status: {e}")
            return None
