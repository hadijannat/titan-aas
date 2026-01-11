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

from enum import Enum
from typing import TYPE_CHECKING, Annotated

import strawberry
from strawberry.types import Info

from titan.security.rbac import Permission, rbac_policy

if TYPE_CHECKING:
    from titan.graphql.dataloaders import DataLoaderContext


def check_permission(context: DataLoaderContext, permission: Permission) -> MutationError | None:
    """Check if user has required permission.

    Args:
        context: GraphQL context with user
        permission: Required permission

    Returns:
        MutationError if permission denied, None if allowed
    """
    # If no user (unauthenticated), deny write operations
    if context.user is None:
        return MutationError(
            code="UNAUTHORIZED",
            message="Authentication required for this operation",
        )

    # Check if user has permission
    if not rbac_policy.has_permission(context.user, permission):
        return MutationError(
            code="FORBIDDEN",
            message=f"Permission denied: {permission.value} required",
        )

    return None


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


@strawberry.type
class Property:
    """Property submodel element."""

    id_short: str
    model_type: str = "Property"
    value_type: str = "xs:string"
    value: str | None = None
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    qualifiers: list[Qualifier] | None = None


@strawberry.type
class MultiLanguageProperty:
    """Multi-language property."""

    id_short: str
    model_type: str = "MultiLanguageProperty"
    value: list[LangString] | None = None
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    qualifiers: list[Qualifier] | None = None


@strawberry.type
class Range:
    """Range submodel element."""

    id_short: str
    model_type: str = "Range"
    value_type: str = "xs:double"
    min: str | None = None
    max: str | None = None
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    qualifiers: list[Qualifier] | None = None


@strawberry.type
class Blob:
    """Blob submodel element."""

    id_short: str
    model_type: str = "Blob"
    content_type: str = "application/octet-stream"
    value: str | None = None  # Base64 encoded
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    qualifiers: list[Qualifier] | None = None


@strawberry.type
class File:
    """File submodel element."""

    id_short: str
    model_type: str = "File"
    content_type: str = "application/octet-stream"
    value: str | None = None  # URL or path
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    qualifiers: list[Qualifier] | None = None


# Define SubmodelElement union using the new Annotated syntax
# Note: Must be defined after all element types but before use
SubmodelElement = Annotated[
    Property | MultiLanguageProperty | Range | Blob | File,
    strawberry.union("SubmodelElement"),
]


@strawberry.type
class SubmodelElementCollection:
    """Collection of submodel elements."""

    id_short: str
    model_type: str = "SubmodelElementCollection"
    elements: list[SubmodelElement] | None = None
    description: list[LangString] | None = None
    semantic_id: Reference | None = None
    qualifiers: list[Qualifier] | None = None


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
class ConceptDescription:
    """Concept Description entity."""

    id: str
    id_short: str | None = None
    description: list[LangString] | None = None


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
        ctx: DataLoaderContext = info.context
        return await ctx.submodels_by_shell_loader.load(self.id)


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
    """Input for creating a submodel."""

    id: str
    id_short: str | None = None
    semantic_id: str | None = None


@strawberry.input
class ShellUpdateInput:
    """Input for updating a shell (all fields optional)."""

    id_short: str | None = None
    asset_kind: AssetKind | None = None
    global_asset_id: str | None = None


@strawberry.input
class SubmodelUpdateInput:
    """Input for updating a submodel (all fields optional)."""

    id_short: str | None = None
    semantic_id: str | None = None


@strawberry.input
class ConceptDescriptionInput:
    """Input for creating a concept description."""

    id: str
    id_short: str | None = None


@strawberry.input
class ConceptDescriptionUpdateInput:
    """Input for updating a concept description (all fields optional)."""

    id_short: str | None = None


# -----------------------------------------------------------------------------
# Mutation Result Types
# -----------------------------------------------------------------------------


@strawberry.type
class MutationError:
    """Error information from a mutation."""

    code: str
    message: str
    field: str | None = None


@strawberry.type
class ShellMutationResult:
    """Result of a shell mutation."""

    success: bool
    shell: Shell | None = None
    error: MutationError | None = None


@strawberry.type
class SubmodelMutationResult:
    """Result of a submodel mutation."""

    success: bool
    submodel: Submodel | None = None
    error: MutationError | None = None


@strawberry.type
class DeleteMutationResult:
    """Result of a delete mutation."""

    success: bool
    id: str | None = None
    error: MutationError | None = None


@strawberry.type
class ConceptDescriptionMutationResult:
    """Result of a concept description mutation."""

    success: bool
    concept_description: ConceptDescription | None = None
    error: MutationError | None = None


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
        from titan.graphql.converters import shell_to_graphql
        from titan.persistence.repositories import AasRepository

        ctx: DataLoaderContext = info.context
        repo = AasRepository(ctx.session)

        # Query shells with pagination
        shells_list, cursor = await repo.list_models(limit=first, cursor=after)

        # Convert to GraphQL types
        edges = [
            gql_shell for shell in shells_list if (gql_shell := shell_to_graphql(shell)) is not None
        ]

        return ShellConnection(
            edges=edges,
            page_info=PageInfo(
                has_next_page=cursor is not None,
                has_previous_page=after is not None,
                end_cursor=cursor,
            ),
            total_count=len(edges),
        )

    @strawberry.field
    async def shell(
        self,
        info: Info,
        id: str,
    ) -> Shell | None:
        """Get a shell by identifier."""
        ctx: DataLoaderContext = info.context
        return await ctx.shell_loader.load(id)

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
        from titan.graphql.converters import submodel_to_graphql
        from titan.persistence.repositories import SubmodelRepository

        ctx: DataLoaderContext = info.context
        repo = SubmodelRepository(ctx.session)

        # Query submodels with pagination
        submodels_list, cursor = await repo.list_models(limit=first, cursor=after)

        # Convert to GraphQL types
        edges = [gql_sm for sm in submodels_list if (gql_sm := submodel_to_graphql(sm)) is not None]

        return SubmodelConnection(
            edges=edges,
            page_info=PageInfo(
                has_next_page=cursor is not None,
                has_previous_page=after is not None,
                end_cursor=cursor,
            ),
            total_count=len(edges),
        )

    @strawberry.field
    async def submodel(
        self,
        info: Info,
        id: str,
    ) -> Submodel | None:
        """Get a submodel by identifier."""
        ctx: DataLoaderContext = info.context
        return await ctx.submodel_loader.load(id)


@strawberry.type
class Mutation:
    """GraphQL mutation root."""

    @strawberry.mutation
    async def create_shell(
        self,
        info: Info,
        input: ShellInput,
    ) -> ShellMutationResult:
        """Create a new Asset Administration Shell.

        Args:
            info: GraphQL context information
            input: Shell creation input

        Returns:
            ShellMutationResult with created shell or error
        """
        from titan.graphql.converters import shell_from_input, shell_to_graphql
        from titan.persistence.repositories import AasRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.CREATE_AAS)
        if perm_error:
            return ShellMutationResult(success=False, error=perm_error)

        try:
            # Convert GraphQL input to domain model
            shell_model = shell_from_input(input)

            # Persist via repository
            repo = AasRepository(session)
            await repo.create(shell_model)
            await session.commit()

            # Convert to GraphQL type (use the model we created)
            gql_shell = shell_to_graphql(shell_model)

            return ShellMutationResult(success=True, shell=gql_shell)  # nosec B604

        except ValueError as e:
            await session.rollback()
            return ShellMutationResult(
                success=False,
                error=MutationError(
                    code="VALIDATION_ERROR",
                    message=str(e),
                ),
            )
        except Exception as e:
            await session.rollback()
            # Check for duplicate ID (IntegrityError)
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                return ShellMutationResult(
                    success=False,
                    error=MutationError(
                        code="DUPLICATE_ID",
                        message=f"Shell with ID '{input.id}' already exists",
                    ),
                )
            return ShellMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to create shell: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def delete_shell(
        self,
        info: Info,
        id: str,
    ) -> DeleteMutationResult:
        """Delete a shell by identifier.

        Args:
            info: GraphQL context information
            id: Shell identifier to delete

        Returns:
            DeleteMutationResult with success status
        """
        from titan.persistence.repositories import AasRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.DELETE_AAS)
        if perm_error:
            return DeleteMutationResult(success=False, error=perm_error)

        try:
            repo = AasRepository(session)
            deleted = await repo.delete(id)
            await session.commit()

            if deleted:
                return DeleteMutationResult(success=True, id=id)
            else:
                return DeleteMutationResult(
                    success=False,
                    error=MutationError(
                        code="NOT_FOUND",
                        message=f"Shell with ID '{id}' not found",
                    ),
                )

        except Exception as e:
            await session.rollback()
            return DeleteMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to delete shell: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def create_submodel(
        self,
        info: Info,
        input: SubmodelInput,
    ) -> SubmodelMutationResult:
        """Create a new submodel.

        Args:
            info: GraphQL context information
            input: Submodel creation input

        Returns:
            SubmodelMutationResult with created submodel or error
        """
        from titan.graphql.converters import submodel_from_input, submodel_to_graphql
        from titan.persistence.repositories import SubmodelRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.CREATE_SUBMODEL)
        if perm_error:
            return SubmodelMutationResult(success=False, error=perm_error)

        try:
            # Convert GraphQL input to domain model
            submodel_model = submodel_from_input(input)

            # Persist via repository
            repo = SubmodelRepository(session)
            await repo.create(submodel_model)
            await session.commit()

            # Convert to GraphQL type (use the model we created)
            gql_submodel = submodel_to_graphql(submodel_model)

            return SubmodelMutationResult(success=True, submodel=gql_submodel)

        except ValueError as e:
            await session.rollback()
            return SubmodelMutationResult(
                success=False,
                error=MutationError(
                    code="VALIDATION_ERROR",
                    message=str(e),
                ),
            )
        except Exception as e:
            await session.rollback()
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                return SubmodelMutationResult(
                    success=False,
                    error=MutationError(
                        code="DUPLICATE_ID",
                        message=f"Submodel with ID '{input.id}' already exists",
                    ),
                )
            return SubmodelMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to create submodel: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def delete_submodel(
        self,
        info: Info,
        id: str,
    ) -> DeleteMutationResult:
        """Delete a submodel by identifier.

        Args:
            info: GraphQL context information
            id: Submodel identifier to delete

        Returns:
            DeleteMutationResult with success status
        """
        from titan.persistence.repositories import SubmodelRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.DELETE_SUBMODEL)
        if perm_error:
            return DeleteMutationResult(success=False, error=perm_error)

        try:
            repo = SubmodelRepository(session)
            deleted = await repo.delete(id)
            await session.commit()

            if deleted:
                return DeleteMutationResult(success=True, id=id)
            else:
                return DeleteMutationResult(
                    success=False,
                    error=MutationError(
                        code="NOT_FOUND",
                        message=f"Submodel with ID '{id}' not found",
                    ),
                )

        except Exception as e:
            await session.rollback()
            return DeleteMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to delete submodel: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def update_shell(
        self,
        info: Info,
        id: str,
        input: ShellUpdateInput,
    ) -> ShellMutationResult:
        """Update an existing shell.

        Args:
            info: GraphQL context information
            id: Shell identifier to update
            input: Shell update input with optional fields

        Returns:
            ShellMutationResult with updated shell or error
        """
        from titan.core.model import AssetInformation
        from titan.core.model import AssetKind as PydanticAssetKind
        from titan.graphql.converters import shell_to_graphql
        from titan.persistence.repositories import AasRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.UPDATE_AAS)
        if perm_error:
            return ShellMutationResult(success=False, error=perm_error)

        try:
            repo = AasRepository(session)

            # Get existing shell
            existing = await repo.get_model_by_id(id)
            if existing is None:
                return ShellMutationResult(
                    success=False,
                    error=MutationError(
                        code="NOT_FOUND",
                        message=f"Shell with ID '{id}' not found",
                    ),
                )

            # Apply updates to existing shell
            if input.id_short is not None:
                existing.id_short = input.id_short

            if input.asset_kind is not None or input.global_asset_id is not None:
                # Update asset information
                asset_kind_map = {
                    AssetKind.TYPE: PydanticAssetKind.TYPE,
                    AssetKind.INSTANCE: PydanticAssetKind.INSTANCE,
                    AssetKind.NOT_APPLICABLE: PydanticAssetKind.NOT_APPLICABLE,
                }

                # Get current values or use input
                current_asset_kind = existing.asset_information.asset_kind
                current_global_asset_id = existing.asset_information.global_asset_id

                new_asset_kind = (
                    asset_kind_map[input.asset_kind]
                    if input.asset_kind is not None
                    else current_asset_kind
                )

                new_global_asset_id = (
                    input.global_asset_id
                    if input.global_asset_id is not None
                    else current_global_asset_id
                )

                existing.asset_information = AssetInformation(
                    assetKind=new_asset_kind,
                    globalAssetId=new_global_asset_id,
                )

            # Update in repository
            await repo.update(id, existing)
            await session.commit()

            # Convert to GraphQL type
            gql_shell = shell_to_graphql(existing)

            return ShellMutationResult(success=True, shell=gql_shell)  # nosec B604

        except ValueError as e:
            await session.rollback()
            return ShellMutationResult(
                success=False,
                error=MutationError(
                    code="VALIDATION_ERROR",
                    message=str(e),
                ),
            )
        except Exception as e:
            await session.rollback()
            return ShellMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to update shell: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def update_submodel(
        self,
        info: Info,
        id: str,
        input: SubmodelUpdateInput,
    ) -> SubmodelMutationResult:
        """Update an existing submodel.

        Args:
            info: GraphQL context information
            id: Submodel identifier to update
            input: Submodel update input with optional fields

        Returns:
            SubmodelMutationResult with updated submodel or error
        """
        from titan.graphql.converters import submodel_to_graphql
        from titan.persistence.repositories import SubmodelRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.UPDATE_SUBMODEL)
        if perm_error:
            return SubmodelMutationResult(success=False, error=perm_error)

        try:
            repo = SubmodelRepository(session)

            # Get existing submodel
            existing = await repo.get_model_by_id(id)
            if existing is None:
                return SubmodelMutationResult(
                    success=False,
                    error=MutationError(
                        code="NOT_FOUND",
                        message=f"Submodel with ID '{id}' not found",
                    ),
                )

            # Apply updates to existing submodel
            if input.id_short is not None:
                existing.id_short = input.id_short

            # TODO: Handle semantic_id update when needed

            # Update in repository
            await repo.update(id, existing)
            await session.commit()

            # Convert to GraphQL type
            gql_submodel = submodel_to_graphql(existing)

            return SubmodelMutationResult(success=True, submodel=gql_submodel)

        except ValueError as e:
            await session.rollback()
            return SubmodelMutationResult(
                success=False,
                error=MutationError(
                    code="VALIDATION_ERROR",
                    message=str(e),
                ),
            )
        except Exception as e:
            await session.rollback()
            return SubmodelMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to update submodel: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def create_concept_description(
        self,
        info: Info,
        input: ConceptDescriptionInput,
    ) -> ConceptDescriptionMutationResult:
        """Create a new concept description.

        Args:
            info: GraphQL context information
            input: ConceptDescription creation input

        Returns:
            ConceptDescriptionMutationResult with created concept description or error
        """
        from titan.graphql.converters import (
            concept_description_from_input,
            concept_description_to_graphql,
        )
        from titan.persistence.repositories import ConceptDescriptionRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.CREATE_CONCEPT_DESCRIPTION)
        if perm_error:
            return ConceptDescriptionMutationResult(success=False, error=perm_error)

        try:
            # Convert GraphQL input to domain model
            cd_model = concept_description_from_input(input)

            # Persist via repository
            repo = ConceptDescriptionRepository(session)
            await repo.create(cd_model)
            await session.commit()

            # Convert to GraphQL type
            gql_cd = concept_description_to_graphql(cd_model)

            return ConceptDescriptionMutationResult(success=True, concept_description=gql_cd)

        except ValueError as e:
            await session.rollback()
            return ConceptDescriptionMutationResult(
                success=False,
                error=MutationError(
                    code="VALIDATION_ERROR",
                    message=str(e),
                ),
            )
        except Exception as e:
            await session.rollback()
            error_msg = str(e).lower()
            if "duplicate" in error_msg or "unique" in error_msg:
                return ConceptDescriptionMutationResult(
                    success=False,
                    error=MutationError(
                        code="DUPLICATE_ID",
                        message=f"ConceptDescription with ID '{input.id}' already exists",
                    ),
                )
            return ConceptDescriptionMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to create concept description: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def update_concept_description(
        self,
        info: Info,
        id: str,
        input: ConceptDescriptionUpdateInput,
    ) -> ConceptDescriptionMutationResult:
        """Update an existing concept description.

        Args:
            info: GraphQL context information
            id: ConceptDescription identifier to update
            input: ConceptDescription update input with optional fields

        Returns:
            ConceptDescriptionMutationResult with updated concept description or error
        """
        from titan.graphql.converters import concept_description_to_graphql
        from titan.persistence.repositories import ConceptDescriptionRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.UPDATE_CONCEPT_DESCRIPTION)
        if perm_error:
            return ConceptDescriptionMutationResult(success=False, error=perm_error)

        try:
            repo = ConceptDescriptionRepository(session)

            # Get existing concept description
            existing = await repo.get(id)
            if existing is None:
                return ConceptDescriptionMutationResult(
                    success=False,
                    error=MutationError(
                        code="NOT_FOUND",
                        message=f"ConceptDescription with ID '{id}' not found",
                    ),
                )

            # Apply updates to existing concept description
            if input.id_short is not None:
                existing.id_short = input.id_short

            # Update in repository
            await repo.update(id, existing)
            await session.commit()

            # Convert to GraphQL type
            gql_cd = concept_description_to_graphql(existing)

            return ConceptDescriptionMutationResult(success=True, concept_description=gql_cd)

        except ValueError as e:
            await session.rollback()
            return ConceptDescriptionMutationResult(
                success=False,
                error=MutationError(
                    code="VALIDATION_ERROR",
                    message=str(e),
                ),
            )
        except Exception as e:
            await session.rollback()
            return ConceptDescriptionMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to update concept description: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def delete_concept_description(
        self,
        info: Info,
        id: str,
    ) -> DeleteMutationResult:
        """Delete a concept description by identifier.

        Args:
            info: GraphQL context information
            id: ConceptDescription identifier to delete

        Returns:
            DeleteMutationResult with success status
        """
        from titan.persistence.repositories import ConceptDescriptionRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.DELETE_CONCEPT_DESCRIPTION)
        if perm_error:
            return DeleteMutationResult(success=False, error=perm_error)

        try:
            repo = ConceptDescriptionRepository(session)
            deleted = await repo.delete(id)
            await session.commit()

            if deleted:
                return DeleteMutationResult(success=True, id=id)
            else:
                return DeleteMutationResult(
                    success=False,
                    error=MutationError(
                        code="NOT_FOUND",
                        message=f"ConceptDescription with ID '{id}' not found",
                    ),
                )

        except Exception as e:
            await session.rollback()
            return DeleteMutationResult(
                success=False,
                error=MutationError(
                    code="INTERNAL_ERROR",
                    message=f"Failed to delete concept description: {str(e)}",
                ),
            )

    @strawberry.mutation
    async def create_shells(
        self,
        info: Info,
        inputs: list[ShellInput],
    ) -> list[ShellMutationResult]:
        """Create multiple shells in a single transaction.

        Args:
            info: GraphQL context information
            inputs: List of shell creation inputs

        Returns:
            List of ShellMutationResult (one per input)
        """
        from titan.graphql.converters import shell_from_input, shell_to_graphql
        from titan.persistence.repositories import AasRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.CREATE_AAS)
        if perm_error:
            # Return error for all inputs
            return [ShellMutationResult(success=False, error=perm_error) for _ in inputs]

        results: list[ShellMutationResult] = []

        for input_item in inputs:
            try:
                shell_model = shell_from_input(input_item)
                repo = AasRepository(session)
                await repo.create(shell_model)
                gql_shell = shell_to_graphql(shell_model)
                results.append(ShellMutationResult(success=True, shell=gql_shell))  # nosec B604
            except ValueError as e:
                results.append(
                    ShellMutationResult(
                        success=False,
                        error=MutationError(code="VALIDATION_ERROR", message=str(e)),
                    )
                )
            except Exception as e:
                error_msg = str(e).lower()
                if "duplicate" in error_msg or "unique" in error_msg:
                    results.append(
                        ShellMutationResult(
                            success=False,
                            error=MutationError(
                                code="DUPLICATE_ID",
                                message=f"Shell with ID '{input_item.id}' already exists",
                            ),
                        )
                    )
                else:
                    results.append(
                        ShellMutationResult(
                            success=False,
                            error=MutationError(
                                code="INTERNAL_ERROR",
                                message=f"Failed to create shell: {str(e)}",
                            ),
                        )
                    )

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            # If commit fails, mark all successful results as failed
            for i, result in enumerate(results):
                if result.success:
                    results[i] = ShellMutationResult(
                        success=False,
                        error=MutationError(
                            code="INTERNAL_ERROR",
                            message=f"Transaction failed: {str(e)}",
                        ),
                    )

        return results

    @strawberry.mutation
    async def delete_shells(
        self,
        info: Info,
        ids: list[str],
    ) -> list[DeleteMutationResult]:
        """Delete multiple shells.

        Args:
            info: GraphQL context information
            ids: List of shell identifiers to delete

        Returns:
            List of DeleteMutationResult (one per ID)
        """
        from titan.persistence.repositories import AasRepository

        ctx: DataLoaderContext = info.context
        session = ctx.session

        # Check permission
        perm_error = check_permission(ctx, Permission.DELETE_AAS)
        if perm_error:
            # Return error for all IDs
            return [DeleteMutationResult(success=False, error=perm_error) for _ in ids]

        results: list[DeleteMutationResult] = []

        for shell_id in ids:
            try:
                repo = AasRepository(session)
                deleted = await repo.delete(shell_id)

                if deleted:
                    results.append(DeleteMutationResult(success=True, id=shell_id))
                else:
                    results.append(
                        DeleteMutationResult(
                            success=False,
                            error=MutationError(
                                code="NOT_FOUND",
                                message=f"Shell with ID '{shell_id}' not found",
                            ),
                        )
                    )
            except Exception as e:
                results.append(
                    DeleteMutationResult(
                        success=False,
                        error=MutationError(
                            code="INTERNAL_ERROR",
                            message=f"Failed to delete shell: {str(e)}",
                        ),
                    )
                )

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            # If commit fails, mark all successful results as failed
            for i, result in enumerate(results):
                if result.success:
                    results[i] = DeleteMutationResult(
                        success=False,
                        error=MutationError(
                            code="INTERNAL_ERROR",
                            message=f"Transaction failed: {str(e)}",
                        ),
                    )

        return results


def _create_schema() -> strawberry.Schema:
    """Create the GraphQL schema with query, mutation, and subscription roots.

    Deferred import of Subscription to avoid circular dependency issues.
    """
    from titan.graphql.subscriptions import Subscription

    return strawberry.Schema(
        query=Query,
        mutation=Mutation,
        subscription=Subscription,
        types=[SubmodelElementCollection],  # Include collection type
    )


# Create the schema
schema = _create_schema()
