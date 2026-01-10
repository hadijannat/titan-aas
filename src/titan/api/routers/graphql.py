"""GraphQL API router.

Mounts the Strawberry GraphQL schema to FastAPI.

Provides:
- /graphql endpoint with GraphiQL playground
- Query execution with DataLoader context
- Mutation execution
- Subscription support (future)

Example:
    from titan.api.routers.graphql import router

    app.include_router(router)
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.fastapi import GraphQLRouter

from titan.graphql import schema
from titan.graphql.dataloaders import DataLoaderContext
from titan.persistence.db import get_session


async def get_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> DataLoaderContext:
    """Create GraphQL context with dataloaders for each request.

    Args:
        request: FastAPI request object
        session: Database session from dependency injection

    Returns:
        DataLoaderContext with dataloaders bound to the session
    """
    return DataLoaderContext(session)


# Create the GraphQL router with context injection
router = GraphQLRouter(
    schema,
    path="/graphql",
    graphql_ide="graphiql",
    context_getter=cast(Any, get_context),
)

# Alternative configuration for production (no playground)
# router = GraphQLRouter(
#     schema,
#     path="/graphql",
#     graphql_ide=None,
#     context_getter=get_context,
# )
