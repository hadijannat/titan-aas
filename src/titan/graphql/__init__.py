"""GraphQL API module for Titan-AAS.

Provides GraphQL interface using Strawberry:
- Type definitions for AAS entities
- Query resolvers for fetching data
- Mutation resolvers for modifications
- DataLoaders for N+1 prevention

Example:
    from titan.graphql import schema
    from strawberry.fastapi import GraphQLRouter

    router = GraphQLRouter(schema)
    app.include_router(router, prefix="/graphql")
"""

from titan.graphql.schema import (
    AdministrativeInfo,
    AssetInformation,
    AssetKind,
    Blob,
    File,
    Key,
    KeyType,
    LangString,
    ModellingKind,
    MultiLanguageProperty,
    Mutation,
    PageInfo,
    Property,
    Qualifier,
    Query,
    Range,
    Reference,
    Shell,
    ShellConnection,
    ShellInput,
    Submodel,
    SubmodelConnection,
    SubmodelElement,
    SubmodelElementCollection,
    SubmodelInput,
    schema,
)

__all__ = [
    # Schema
    "schema",
    # Types
    "Shell",
    "Submodel",
    "SubmodelElement",
    "SubmodelElementCollection",
    "Property",
    "MultiLanguageProperty",
    "Range",
    "Blob",
    "File",
    "Reference",
    "Key",
    "LangString",
    "Qualifier",
    "AdministrativeInfo",
    "AssetInformation",
    "PageInfo",
    # Connections
    "ShellConnection",
    "SubmodelConnection",
    # Inputs
    "ShellInput",
    "SubmodelInput",
    # Enums
    "ModellingKind",
    "AssetKind",
    "KeyType",
    # Root types
    "Query",
    "Mutation",
]
