"""IDTA-01001 Part 1 v3.1.2: Asset Administration Shell.

This module defines the AssetAdministrationShell and related types
that form the top-level container for digital twins.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from titan.core.model import StrictModel
from titan.core.model.administrative import (
    AdministrativeInformation,
    HasDataSpecificationMixin,
)
from titan.core.model.descriptions import LangStringTextType
from titan.core.model.identifiers import AssetKind, Identifier, IdShort, Reference
from titan.core.model.qualifiers import HasExtensionsMixin
from titan.core.model.submodel_elements import SpecificAssetId


class Resource(StrictModel):
    """A resource referenced by path and optional content type.

    Used for referencing external resources like thumbnails or
    documentation files.
    """

    path: Annotated[str, Field(min_length=1, max_length=2000)] = Field(
        ..., description="Path or URL to the resource"
    )
    content_type: Annotated[str, Field(max_length=100)] | None = Field(
        default=None,
        alias="contentType",
        description="MIME type of the resource",
    )


class AssetInformation(StrictModel):
    """Information about the asset represented by an AAS.

    Contains identification information and metadata about the
    physical or virtual asset that the AAS represents.
    """

    asset_kind: AssetKind = Field(
        ..., alias="assetKind", description="Kind of the asset (Type, Instance, NotApplicable)"
    )
    global_asset_id: Annotated[str, Field(min_length=1, max_length=2000)] | None = Field(
        default=None,
        alias="globalAssetId",
        description="Globally unique identifier of the asset",
    )
    specific_asset_ids: list[SpecificAssetId] | None = Field(
        default=None,
        alias="specificAssetIds",
        description="Domain-specific identifiers of the asset",
    )
    asset_type: Annotated[str, Field(max_length=2000)] | None = Field(
        default=None,
        alias="assetType",
        description="Type of the asset (e.g., product type identifier)",
    )
    default_thumbnail: Resource | None = Field(
        default=None,
        alias="defaultThumbnail",
        description="Default thumbnail image for the asset",
    )


class AssetAdministrationShell(HasExtensionsMixin, HasDataSpecificationMixin):
    """The Asset Administration Shell - the top-level container.

    An AAS is the standardized digital representation of an asset.
    It contains metadata about the asset and references to Submodels
    that describe different aspects of the asset.

    Key features:
    - Globally unique identifier
    - Asset information (the asset being represented)
    - References to Submodels
    - Optional derivation from another AAS
    - Administrative information
    """

    model_type: str | None = Field(
        default=None, alias="modelType", description="Model type identifier"
    )
    id: Identifier = Field(..., description="Globally unique identifier of the AAS")
    id_short: IdShort | None = Field(
        default=None,
        alias="idShort",
        description="Short identifier (unique within context)",
    )
    description: list[LangStringTextType] | None = Field(
        default=None, description="Description in multiple languages"
    )
    display_name: list[LangStringTextType] | None = Field(
        default=None,
        alias="displayName",
        description="Display name in multiple languages",
    )
    category: str | None = Field(default=None, description="Category of the AAS")
    administration: AdministrativeInformation | None = Field(
        default=None, description="Administrative information"
    )
    asset_information: AssetInformation = Field(
        ..., alias="assetInformation", description="Information about the asset"
    )
    derived_from: Reference | None = Field(
        default=None,
        alias="derivedFrom",
        description="Reference to the AAS this one is derived from",
    )
    submodels: list[Reference] | None = Field(
        default=None, description="References to the Submodels"
    )
