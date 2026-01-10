"""GraphQL API router.

Mounts the Strawberry GraphQL schema to FastAPI.

Provides:
- /graphql endpoint with GraphiQL playground
- Query execution
- Mutation execution
- Subscription support (future)

Example:
    from titan.api.routers.graphql import router

    app.include_router(router)
"""

from __future__ import annotations

from strawberry.fastapi import GraphQLRouter

from titan.graphql import schema

# Create the GraphQL router with playground enabled
router = GraphQLRouter(
    schema,
    path="/graphql",
    graphql_ide="graphiql",
)

# Alternative configuration for production (no playground)
# router = GraphQLRouter(
#     schema,
#     path="/graphql",
#     graphql_ide=None,
# )
