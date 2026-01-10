"""GraphQL schema definitions using Strawberry.

Defines GraphQL types for AAS entities:
- Shell (AssetAdministrationShell)
- Submodel
- SubmodelElement (with subtypes)
- Reference, Key, etc.

Example:
    from titan.graphql.schema import schema

    app.include_router(GraphQLRouter(schema), prefix="/graphql")
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

import strawberry
from strawberry.types import Info


@strawberry.enum
class ModellingKind(Enum):
    """AAS modelling kind."""

    TEMPLATE = "Template"
    INSTANCE = "Instance"


@strawberry.enum
class AssetKind(Enum):
    """AAS asset kind."""

    TYPE = "Type"
    INSTANCE = "Instance"
    NOT_APPLICABLE = "NotApplicable"


@strawberry.enum
class KeyType(Enum):
    """Reference key type."""

    ASSET_ADMINISTRATION_SHELL = "AssetAdministrationShell"
    SUBMODEL = "Submodel"
    CONCEPT_DESCRIPTION = "ConceptDescription"
    GLOBAL_REFERENCE = "GlobalReference"
    SUBMODEL_ELEMENT = "SubmodelElement"


@strawberry.type
class Key:
    """Reference key."""

    type: KeyType
    value: str


@strawberry.type
class Reference:
    """AAS reference."""

    type: str
    keys: list[Key]


@strawberry.type
class LangString:
    """Multilingual string."""

    language: str
    text: str


@strawberry.type
class AdministrativeInfo:
    """Administrative information."""

    version: str | None = None
    revision: str | None = None


@strawberry.type
class AssetInformation:
    """Asset information for a shell."""

    asset_kind: AssetKind
    global_asset_id: str | None = None
    specific_asset_ids: list[str] | None = None
    asset_type: str | None = None


@strawberry.type
class Qualifier:
    """Qualifier for submodel elements."""

    type: str
    value_type: str
    value: str | None = None


@strawberry.interface
class SubmodelElementBase:
    """Base interface for all submodel elements."""

    id_short: str
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    qualifiers: list[Qualifier] | None = None


@strawberry.type
class Property(SubmodelElementBase):
    """Property submodel element."""

    model_type: str = "Property"
    value_type: str
    value: str | None = None


@strawberry.type
class MultiLanguageProperty(SubmodelElementBase):
    """Multi-language property."""

    model_type: str = "MultiLanguageProperty"
    value: list[LangString] | None = None


@strawberry.type
class Range(SubmodelElementBase):
    """Range submodel element."""

    model_type: str = "Range"
    value_type: str
    min: str | None = None
    max: str | None = None


@strawberry.type
class Blob(SubmodelElementBase):
    """Blob submodel element."""

    model_type: str = "Blob"
    content_type: str
    value: str | None = None  # Base64 encoded


@strawberry.type
class File(SubmodelElementBase):
    """File submodel element."""

    model_type: str = "File"
    content_type: str
    value: str | None = None  # URL or path


@strawberry.type
class SubmodelElementCollection(SubmodelElementBase):
    """Collection of submodel elements."""

    model_type: str = "SubmodelElementCollection"
    value: list["SubmodelElement"] | None = None


# Union type for all submodel elements
SubmodelElement = strawberry.union(
    "SubmodelElement",
    types=(
        Property,
        MultiLanguageProperty,
        Range,
        Blob,
        File,
        SubmodelElementCollection,
    ),
)


@strawberry.type
class Submodel:
    """Submodel entity."""

    id: str
    id_short: str | None = None
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    kind: ModellingKind | None = None
    administration: AdministrativeInfo | None = None
    submodel_elements: list[SubmodelElement] | None = None


@strawberry.type
class Shell:
    """Asset Administration Shell entity."""

    id: str
    id_short: str | None = None
    description: list[LangString] | None = None
    asset_information: AssetInformation
    administration: AdministrativeInfo | None = None
    derived_from: Reference | None = None

    @strawberry.field
    async def submodels(self, info: Info) -> list[Submodel]:
        """Get submodels referenced by this shell."""
        # In a real implementation, this would fetch from database
        return []


@strawberry.type
class PageInfo:
    """Pagination information."""

    has_next_page: bool
    has_previous_page: bool
    start_cursor: str | None = None
    end_cursor: str | None = None


@strawberry.type
class ShellConnection:
    """Paginated shell results."""

    edges: list[Shell]
    page_info: PageInfo
    total_count: int


@strawberry.type
class SubmodelConnection:
    """Paginated submodel results."""

    edges: list[Submodel]
    page_info: PageInfo
    total_count: int


@strawberry.input
class ShellInput:
    """Input for creating/updating a shell."""

    id: str
    id_short: str | None = None
    asset_kind: AssetKind = AssetKind.INSTANCE
    global_asset_id: str | None = None


@strawberry.input
class SubmodelInput:
    """Input for creating/updating a submodel."""

    id: str
    id_short: str | None = None
    semantic_id: str | None = None


@strawberry.type
class Query:
    """GraphQL query root."""

    @strawberry.field
    async def shells(
        self,
        info: Info,
        id_short: str | None = None,
        asset_kind: AssetKind | None = None,
        first: int = 100,
        after: str | None = None,
    ) -> ShellConnection:
        """Query shells with optional filtering."""
        # Placeholder - would fetch from repository
        return ShellConnection(
            edges=[],
            page_info=PageInfo(
                has_next_page=False,
                has_previous_page=False,
            ),
            total_count=0,
        )

    @strawberry.field
    async def shell(
        self,
        info: Info,
        id: str,
    ) -> Shell | None:
        """Get a shell by identifier."""
        # Placeholder - would fetch from repository
        return None

    @strawberry.field
    async def submodels(
        self,
        info: Info,
        semantic_id: str | None = None,
        id_short: str | None = None,
        first: int = 100,
        after: str | None = None,
    ) -> SubmodelConnection:
        """Query submodels with optional filtering."""
        # Placeholder - would fetch from repository
        return SubmodelConnection(
            edges=[],
            page_info=PageInfo(
                has_next_page=False,
                has_previous_page=False,
            ),
            total_count=0,
        )

    @strawberry.field
    async def submodel(
        self,
        info: Info,
        id: str,
    ) -> Submodel | None:
        """Get a submodel by identifier."""
        # Placeholder - would fetch from repository
        return None


@strawberry.type
class Mutation:
    """GraphQL mutation root."""

    @strawberry.mutation
    async def create_shell(
        self,
        info: Info,
        input: ShellInput,
    ) -> Shell:
        """Create a new shell."""
        # Placeholder - would call repository
        return Shell(
            id=input.id,
            id_short=input.id_short,
            asset_information=AssetInformation(
                asset_kind=input.asset_kind,
                global_asset_id=input.global_asset_id,
            ),
        )

    @strawberry.mutation
    async def delete_shell(
        self,
        info: Info,
        id: str,
    ) -> bool:
        """Delete a shell by identifier."""
        # Placeholder - would call repository
        return True

    @strawberry.mutation
    async def create_submodel(
        self,
        info: Info,
        input: SubmodelInput,
    ) -> Submodel:
        """Create a new submodel."""
        # Placeholder - would call repository
        return Submodel(
            id=input.id,
            id_short=input.id_short,
        )

    @strawberry.mutation
    async def delete_submodel(
        self,
        info: Info,
        id: str,
    ) -> bool:
        """Delete a submodel by identifier."""
        # Placeholder - would call repository
        return True


# Create the schema
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
)
