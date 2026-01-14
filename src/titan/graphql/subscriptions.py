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

import logging
from collections.abc import AsyncGenerator
from typing import Any

import orjson
import strawberry
from strawberry.types import Info

from titan.core.model import AssetAdministrationShell
from titan.core.model import ConceptDescription as PydanticConceptDescription
from titan.core.model import Submodel as PydanticSubmodel
from titan.graphql.converters import (
    concept_description_to_graphql,
    shell_to_graphql,
    submodel_to_graphql,
)
from titan.graphql.subscription_manager import get_subscription_manager

# Use Strawberry's LazyType to avoid circular import
# Type annotation as Any to satisfy mypy while preserving runtime behavior
Shell: Any = strawberry.LazyType("Shell", "titan.graphql.schema")
Submodel: Any = strawberry.LazyType("Submodel", "titan.graphql.schema")
ConceptDescription: Any = strawberry.LazyType("ConceptDescription", "titan.graphql.schema")

logger = logging.getLogger(__name__)


def _deserialize_shell(doc_bytes: bytes | None) -> AssetAdministrationShell | None:
    """Deserialize shell from JSON bytes."""
    if doc_bytes is None:
        return None
    try:
        data = orjson.loads(doc_bytes)
        return AssetAdministrationShell.model_validate(data)
    except Exception as e:
        logger.warning("Failed to deserialize shell: %s", e)
        return None


def _deserialize_submodel(doc_bytes: bytes | None) -> PydanticSubmodel | None:
    """Deserialize submodel from JSON bytes."""
    if doc_bytes is None:
        return None
    try:
        data = orjson.loads(doc_bytes)
        return PydanticSubmodel.model_validate(data)
    except Exception as e:
        logger.warning("Failed to deserialize submodel: %s", e)
        return None


def _deserialize_concept_description(
    doc_bytes: bytes | None,
) -> PydanticConceptDescription | None:
    """Deserialize concept description from JSON bytes."""
    if doc_bytes is None:
        return None
    try:
        data = orjson.loads(doc_bytes)
        return PydanticConceptDescription.model_validate(data)
    except Exception as e:
        logger.warning("Failed to deserialize concept description: %s", e)
        return None


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
        manager = get_subscription_manager()

        async for event in manager.subscribe_shell_created():
            shell = _deserialize_shell(event.doc_bytes)
            graphql_shell = shell_to_graphql(shell)
            if graphql_shell is not None:
                yield graphql_shell

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_shell_updated(entity_id=id):
            shell = _deserialize_shell(event.doc_bytes)
            graphql_shell = shell_to_graphql(shell)
            if graphql_shell is not None:
                yield graphql_shell

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_shell_deleted():
            yield event.identifier

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_submodel_created():
            submodel = _deserialize_submodel(event.doc_bytes)
            graphql_submodel = submodel_to_graphql(submodel)
            if graphql_submodel is not None:
                yield graphql_submodel

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_submodel_updated(entity_id=id):
            submodel = _deserialize_submodel(event.doc_bytes)
            graphql_submodel = submodel_to_graphql(submodel)
            if graphql_submodel is not None:
                yield graphql_submodel

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_submodel_deleted():
            yield event.identifier

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_concept_description_created():
            cd = _deserialize_concept_description(event.doc_bytes)
            graphql_cd = concept_description_to_graphql(cd)
            if graphql_cd is not None:
                yield graphql_cd

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_concept_description_updated(entity_id=id):
            cd = _deserialize_concept_description(event.doc_bytes)
            graphql_cd = concept_description_to_graphql(cd)
            if graphql_cd is not None:
                yield graphql_cd

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
        manager = get_subscription_manager()

        async for event in manager.subscribe_concept_description_deleted():
            yield event.identifier
