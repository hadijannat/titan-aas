"""GraphQL subscriptions for real-time updates.

Provides subscription endpoints for:
- Shell creation and update events
- Submodel creation and update events
- ConceptDescription creation and update events

Subscriptions use Redis Streams for event delivery and maintain
WebSocket connections to clients.

Example:
    subscription {
        shellUpdated(id: "https://example.com/shell/1") {
            id
            idShort
            assetInformation {
                globalAssetId
            }
        }
    }
"""

# ruff: noqa: UP037
# Note: Lazy types are required to avoid circular imports with schema.py
from __future__ import annotations

from collections.abc import AsyncGenerator

import strawberry
from strawberry.types import Info

# Use Strawberry's LazyType to avoid circular import
Shell = strawberry.LazyType["Shell", "titan.graphql.schema"]
Submodel = strawberry.LazyType["Submodel", "titan.graphql.schema"]
ConceptDescription = strawberry.LazyType["ConceptDescription", "titan.graphql.schema"]


@strawberry.type
class Subscription:
    """GraphQL subscription root for real-time updates.

    All subscriptions require an active WebSocket connection and
    will stream updates as events occur in the system.
    """

    @strawberry.subscription
    async def shell_created(
        self,
        info: Info,
    ) -> AsyncGenerator[Shell, None]:
        """Subscribe to shell creation events.

        Yields a Shell object whenever a new shell is created in the system.

        Args:
            info: GraphQL context information

        Yields:
            Newly created Shell objects
        """
        # TODO: Implement event bus subscription
        # This is a placeholder implementation
        # In production, this would:
        # 1. Subscribe to Redis Stream for "shell.created" events
        # 2. Load shell data via DataLoader when event received
        # 3. Convert to GraphQL type and yield
        # 4. Handle disconnection and cleanup

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def shell_updated(
        self,
        info: Info,
        id: str | None = None,
    ) -> AsyncGenerator[Shell, None]:
        """Subscribe to shell update events.

        Yields a Shell object whenever a shell is updated.
        Optionally filter for a specific shell ID.

        Args:
            info: GraphQL context information
            id: Optional shell ID to filter events (if None, all shells)

        Yields:
            Updated Shell objects
        """
        # TODO: Implement event bus subscription with filtering
        # If id is provided, only yield updates for that shell
        # Otherwise yield all shell updates

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def shell_deleted(
        self,
        info: Info,
    ) -> AsyncGenerator[str, None]:
        """Subscribe to shell deletion events.

        Yields the shell ID whenever a shell is deleted.

        Args:
            info: GraphQL context information

        Yields:
            Deleted shell IDs
        """
        # TODO: Implement event bus subscription
        # Yields shell IDs as strings when shells are deleted

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def submodel_created(
        self,
        info: Info,
    ) -> AsyncGenerator[Submodel, None]:
        """Subscribe to submodel creation events.

        Yields a Submodel object whenever a new submodel is created.

        Args:
            info: GraphQL context information

        Yields:
            Newly created Submodel objects
        """
        # TODO: Implement event bus subscription for submodel.created

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def submodel_updated(
        self,
        info: Info,
        id: str | None = None,
    ) -> AsyncGenerator[Submodel, None]:
        """Subscribe to submodel update events.

        Yields a Submodel object whenever a submodel is updated.
        Optionally filter for a specific submodel ID.

        Args:
            info: GraphQL context information
            id: Optional submodel ID to filter events (if None, all submodels)

        Yields:
            Updated Submodel objects
        """
        # TODO: Implement event bus subscription with filtering
        # If id is provided, only yield updates for that submodel
        # Otherwise yield all submodel updates

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def submodel_deleted(
        self,
        info: Info,
    ) -> AsyncGenerator[str, None]:
        """Subscribe to submodel deletion events.

        Yields the submodel ID whenever a submodel is deleted.

        Args:
            info: GraphQL context information

        Yields:
            Deleted submodel IDs
        """
        # TODO: Implement event bus subscription for submodel.deleted

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def concept_description_created(
        self,
        info: Info,
    ) -> AsyncGenerator[ConceptDescription, None]:
        """Subscribe to concept description creation events.

        Yields a ConceptDescription object whenever a new concept description is created.

        Args:
            info: GraphQL context information

        Yields:
            Newly created ConceptDescription objects
        """
        # TODO: Implement event bus subscription for concept_description.created

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def concept_description_updated(
        self,
        info: Info,
        id: str | None = None,
    ) -> AsyncGenerator[ConceptDescription, None]:
        """Subscribe to concept description update events.

        Yields a ConceptDescription object whenever a concept description is updated.
        Optionally filter for a specific concept description ID.

        Args:
            info: GraphQL context information
            id: Optional concept description ID to filter events

        Yields:
            Updated ConceptDescription objects
        """
        # TODO: Implement event bus subscription with filtering

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore

    @strawberry.subscription
    async def concept_description_deleted(
        self,
        info: Info,
    ) -> AsyncGenerator[str, None]:
        """Subscribe to concept description deletion events.

        Yields the concept description ID whenever one is deleted.

        Args:
            info: GraphQL context information

        Yields:
            Deleted concept description IDs
        """
        # TODO: Implement event bus subscription for concept_description.deleted

        # Placeholder - always empty for now
        if False:  # pragma: no cover
            yield  # type: ignore
