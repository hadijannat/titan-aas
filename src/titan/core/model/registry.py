"""IDTA-01002 Part 2 v3.1.1: Registry types.

This module defines the Descriptor types used by the AAS Registry
and Submodel Registry services for discovering AAS and Submodel
endpoints.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel
from titan.core.model.administrative import AdministrativeInformation
from titan.core.model.descriptions import LangStringTextType
from titan.core.model.identifiers import Identifier, IdShort
from titan.core.model.semantic import HasSemanticsMixin
from titan.core.model.submodel_elements import SpecificAssetId


class ProtocolInformationSecurityType(str, Enum):
    """Security attributes for protocol information."""

    NONE = "NONE"
    RFC_TLSA = "RFC_TLSA"
    W3C_DID = "W3C_DID"


class Endpoint(StrictModel):
    """An endpoint for accessing an AAS or Submodel.

    Contains the interface type and protocol information needed
    to connect to the service.
    """

    interface: Annotated[str, Field(min_length=1, max_length=128)] = Field(
        ..., alias="interface", description="Interface identifier (e.g., AAS-3.0)"
    )
    protocol_information: ProtocolInformation = Field(
        ...,
        alias="protocolInformation",
        description="Protocol-specific connection details",
    )


class ProtocolInformation(StrictModel):
    """Protocol-specific information for connecting to an endpoint."""

    href: Annotated[str, Field(min_length=1, max_length=2048)] = Field(
        ..., description="URL of the endpoint"
    )
    endpoint_protocol: Annotated[str, Field(max_length=128)] | None = Field(
        default=None,
        alias="endpointProtocol",
        description="Protocol (e.g., HTTPS, OPC-UA)",
    )
    endpoint_protocol_version: list[str] | None = Field(
        default=None,
        alias="endpointProtocolVersion",
        description="Supported protocol versions",
    )
    subprotocol: Annotated[str, Field(max_length=128)] | None = Field(
        default=None, description="Sub-protocol identifier"
    )
    subprotocol_body: Annotated[str, Field(max_length=128)] | None = Field(
        default=None, alias="subprotocolBody", description="Sub-protocol body"
    )
    subprotocol_body_encoding: Annotated[str, Field(max_length=128)] | None = Field(
        default=None,
        alias="subprotocolBodyEncoding",
        description="Encoding of the sub-protocol body",
    )
    security_attributes: list[ProtocolInformationSecurityType] | None = Field(
        default=None,
        alias="securityAttributes",
        description="Security attributes for the endpoint",
    )


class SubmodelDescriptor(HasSemanticsMixin):
    """Descriptor for a Submodel in the registry.

    Contains identification information and endpoints for
    accessing a Submodel.
    """

    id: Identifier = Field(..., description="Globally unique identifier of the Submodel")
    id_short: IdShort | None = Field(
        default=None,
        alias="idShort",
        description="Short identifier",
    )
    description: list[LangStringTextType] | None = Field(
        default=None, description="Description in multiple languages"
    )
    display_name: list[LangStringTextType] | None = Field(
        default=None,
        alias="displayName",
        description="Display name in multiple languages",
    )
    administration: AdministrativeInformation | None = Field(
        default=None, description="Administrative information"
    )
    endpoints: list[Endpoint] | None = Field(
        default=None, description="Endpoints for accessing the Submodel"
    )


class AssetAdministrationShellDescriptor(StrictModel):
    """Descriptor for an AAS in the registry.

    Contains identification information, asset information,
    and endpoints for accessing an AAS and its Submodels.
    """

    id: Identifier = Field(..., description="Globally unique identifier of the AAS")
    id_short: IdShort | None = Field(
        default=None,
        alias="idShort",
        description="Short identifier",
    )
    description: list[LangStringTextType] | None = Field(
        default=None, description="Description in multiple languages"
    )
    display_name: list[LangStringTextType] | None = Field(
        default=None,
        alias="displayName",
        description="Display name in multiple languages",
    )
    administration: AdministrativeInformation | None = Field(
        default=None, description="Administrative information"
    )
    asset_kind: Annotated[str, Field(max_length=50)] | None = Field(
        default=None,
        alias="assetKind",
        description="Kind of the asset (Type, Instance)",
    )
    asset_type: Annotated[str, Field(max_length=2000)] | None = Field(
        default=None,
        alias="assetType",
        description="Type of the asset",
    )
    global_asset_id: Annotated[str, Field(max_length=2000)] | None = Field(
        default=None,
        alias="globalAssetId",
        description="Global identifier of the asset",
    )
    specific_asset_ids: list[SpecificAssetId] | None = Field(
        default=None,
        alias="specificAssetIds",
        description="Domain-specific identifiers of the asset",
    )
    endpoints: list[Endpoint] | None = Field(
        default=None, description="Endpoints for accessing the AAS"
    )
    submodel_descriptors: list[SubmodelDescriptor] | None = Field(
        default=None,
        alias="submodelDescriptors",
        description="Descriptors of Submodels associated with this AAS",
    )
