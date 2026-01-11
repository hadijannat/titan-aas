# GraphQL API Documentation

## Overview

Titan-AAS provides a comprehensive GraphQL API for querying and mutating Asset Administration Shell (AAS) data. The GraphQL API offers several advantages over the REST API:

- **Single Endpoint**: All operations go through `/graphql`
- **Flexible Queries**: Request exactly the fields you need
- **Type Safety**: Strongly-typed schema with automatic validation
- **Real-Time Updates**: WebSocket subscriptions for live data
- **Efficient Batching**: DataLoaders automatically batch and cache database queries
- **Reduced Over-Fetching**: No need to make multiple REST calls

### Why GraphQL for AAS?

Asset Administration Shells have deeply nested structures (shells → submodels → elements). With REST, fetching a complete shell with all its submodels requires multiple API calls. With GraphQL, you can request everything in a single query.

**REST Approach** (3 API calls):
```
GET /api/v3/shells/{shellId}
GET /api/v3/shells/{shellId}/submodels
GET /api/v3/submodels/{submodelId}  (repeated for each submodel)
```

**GraphQL Approach** (1 query):
```graphql
query {
  shell(id: "...") {
    id
    idShort
    submodels {
      id
      idShort
      submodelElements {
        idShort
        ... on Property { value }
      }
    }
  }
}
```

## Getting Started

### GraphiQL Playground

The easiest way to explore the API is through the built-in GraphiQL playground:

```bash
# Start the development server
uv run -- uvicorn titan.api.app:create_app --factory --reload

# Open GraphiQL in your browser
open http://localhost:8080/graphql
```

GraphiQL provides:
- Auto-completion as you type
- Inline documentation for all types and fields
- Query validation and error highlighting
- Query history

### Authentication

GraphQL mutations require authentication. Include your Bearer token in the HTTP `Authorization` header:

```bash
curl -X POST http://localhost:8080/graphql \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"query": "mutation { ... }"}'
```

Queries (read operations) work without authentication by default.

### Basic Query Example

```graphql
query GetShell {
  shell(id: "https://example.com/shells/motor-123") {
    id
    idShort
    assetInformation {
      assetKind
      globalAssetId
    }
  }
}
```

## Queries

### Shell Queries

#### Get Single Shell

```graphql
query GetShell($id: String!) {
  shell(id: $id) {
    id
    idShort
    description {
      language
      text
    }
    assetInformation {
      assetKind
      globalAssetId
      assetType
    }
    submodels {
      id
      idShort
    }
  }
}
```

**Variables:**
```json
{
  "id": "https://example.com/shells/motor-123"
}
```

#### List Shells with Pagination

```graphql
query ListShells($limit: Int, $cursor: String) {
  shells(limit: $limit, cursor: $cursor) {
    id
    idShort
    assetInformation {
      globalAssetId
    }
  }
}
```

**Variables:**
```json
{
  "limit": 50,
  "cursor": null
}
```

### Submodel Queries

#### Get Single Submodel

```graphql
query GetSubmodel($id: String!) {
  submodel(id: $id) {
    id
    idShort
    kind
    semanticId {
      keys {
        type
        value
      }
    }
    submodelElements {
      idShort
      ... on Property {
        valueType
        value
      }
      ... on Range {
        valueType
        min
        max
      }
      ... on File {
        contentType
        value
      }
    }
  }
}
```

#### List Submodels

```graphql
query ListSubmodels($limit: Int) {
  submodels(limit: $limit) {
    id
    idShort
    semanticId {
      keys {
        value
      }
    }
  }
}
```

### Nested Queries with DataLoaders

GraphQL automatically batches and caches queries using DataLoaders. This prevents N+1 query problems:

```graphql
query GetMultipleShellsWithSubmodels {
  shell1: shell(id: "https://example.com/shells/1") {
    id
    submodels {  # DataLoader batches these
      id
      idShort
    }
  }
  shell2: shell(id: "https://example.com/shells/2") {
    id
    submodels {  # Batched with shell1's submodels
      id
      idShort
    }
  }
}
```

Behind the scenes, this executes only 2 database queries instead of 4:
1. Batch load both shells
2. Batch load all submodels for both shells

## Mutations

All mutations require authentication and proper permissions.

### Shell Mutations

#### Create Shell

```graphql
mutation CreateShell($input: ShellInput!) {
  createShell(input: $input) {
    success
    shell {
      id
      idShort
      assetInformation {
        assetKind
        globalAssetId
      }
    }
    error {
      code
      message
    }
  }
}
```

**Variables:**
```json
{
  "input": {
    "id": "https://example.com/shells/new-motor",
    "idShort": "NewMotor",
    "assetKind": "INSTANCE",
    "globalAssetId": "https://example.com/assets/motor-456"
  }
}
```

**Required Permission:** `CREATE_AAS`

#### Update Shell

```graphql
mutation UpdateShell($id: String!, $input: ShellUpdateInput!) {
  updateShell(id: $id, input: $input) {
    success
    shell {
      id
      idShort
      assetInformation {
        globalAssetId
      }
    }
    error {
      code
      message
    }
  }
}
```

**Variables:**
```json
{
  "id": "https://example.com/shells/motor-123",
  "input": {
    "idShort": "UpdatedMotor",
    "globalAssetId": "https://example.com/assets/motor-updated"
  }
}
```

**Required Permission:** `UPDATE_AAS`

#### Delete Shell

```graphql
mutation DeleteShell($id: String!) {
  deleteShell(id: $id) {
    success
    id
    error {
      code
      message
    }
  }
}
```

**Required Permission:** `DELETE_AAS`

### Batch Mutations

#### Create Multiple Shells

```graphql
mutation CreateShells($inputs: [ShellInput!]!) {
  createShells(inputs: $inputs) {
    success
    shell {
      id
      idShort
    }
    error {
      code
      message
    }
  }
}
```

**Variables:**
```json
{
  "inputs": [
    {
      "id": "https://example.com/shells/motor-1",
      "idShort": "Motor1",
      "assetKind": "INSTANCE"
    },
    {
      "id": "https://example.com/shells/motor-2",
      "idShort": "Motor2",
      "assetKind": "INSTANCE"
    }
  ]
}
```

Returns an array of results, one per input. All shells are created in a single database transaction.

**Required Permission:** `CREATE_AAS`

### Submodel Mutations

#### Create Submodel

```graphql
mutation CreateSubmodel($input: SubmodelInput!) {
  createSubmodel(input: $input) {
    success
    submodel {
      id
      idShort
    }
    error {
      code
      message
    }
  }
}
```

**Variables:**
```json
{
  "input": {
    "id": "https://example.com/submodels/nameplate",
    "idShort": "Nameplate"
  }
}
```

**Required Permission:** `CREATE_SUBMODEL`

#### Update Submodel

```graphql
mutation UpdateSubmodel($id: String!, $input: SubmodelUpdateInput!) {
  updateSubmodel(id: $id, input: $input) {
    success
    submodel {
      id
      idShort
    }
    error {
      code
      message
    }
  }
}
```

**Required Permission:** `UPDATE_SUBMODEL`

#### Delete Submodel

```graphql
mutation DeleteSubmodel($id: String!) {
  deleteSubmodel(id: $id) {
    success
    id
    error {
      code
      message
    }
  }
}
```

**Required Permission:** `DELETE_SUBMODEL`

### ConceptDescription Mutations

#### Create ConceptDescription

```graphql
mutation CreateConceptDescription($input: ConceptDescriptionInput!) {
  createConceptDescription(input: $input) {
    success
    conceptDescription {
      id
      idShort
    }
    error {
      code
      message
    }
  }
}
```

**Variables:**
```json
{
  "input": {
    "id": "https://example.com/concepts/rotation-speed",
    "idShort": "RotationSpeed"
  }
}
```

**Required Permission:** `CREATE_CONCEPT_DESCRIPTION`

#### Update ConceptDescription

```graphql
mutation UpdateConceptDescription($id: String!, $input: ConceptDescriptionUpdateInput!) {
  updateConceptDescription(id: $id, input: $input) {
    success
    conceptDescription {
      id
      idShort
    }
    error {
      code
      message
    }
  }
}
```

**Required Permission:** `UPDATE_CONCEPT_DESCRIPTION`

#### Delete ConceptDescription

```graphql
mutation DeleteConceptDescription($id: String!) {
  deleteConceptDescription(id: $id) {
    success
    id
    error {
      code
      message
    }
  }
}
```

**Required Permission:** `DELETE_CONCEPT_DESCRIPTION`

## Subscriptions

Subscriptions provide real-time updates via WebSocket connections. Currently implemented as placeholders for future event bus integration.

### Shell Subscriptions

#### Subscribe to Shell Creation

```graphql
subscription {
  shellCreated {
    id
    idShort
    assetInformation {
      globalAssetId
    }
  }
}
```

Receives a notification whenever a shell is created.

#### Subscribe to Shell Updates

```graphql
subscription WatchShell($id: String) {
  shellUpdated(id: $id) {
    id
    idShort
    assetInformation {
      globalAssetId
    }
  }
}
```

**Variables:**
```json
{
  "id": "https://example.com/shells/motor-123"
}
```

If `id` is provided, only updates to that specific shell are received. Otherwise, all shell updates are streamed.

#### Subscribe to Shell Deletion

```graphql
subscription {
  shellDeleted
}
```

Returns the ID of deleted shells as a string.

### Submodel Subscriptions

Similar patterns exist for submodels:
- `submodelCreated`
- `submodelUpdated(id: String)`
- `submodelDeleted`

### ConceptDescription Subscriptions

And for concept descriptions:
- `conceptDescriptionCreated`
- `conceptDescriptionUpdated(id: String)`
- `conceptDescriptionDeleted`

## Error Handling

All mutations return a result type with `success`, data, and `error` fields:

```graphql
type ShellMutationResult {
  success: Boolean!
  shell: Shell
  error: MutationError
}

type MutationError {
  code: String!
  message: String!
  field: String
}
```

### Error Codes

| Code | Description |
|------|-------------|
| `UNAUTHORIZED` | Authentication required |
| `FORBIDDEN` | User lacks required permission |
| `VALIDATION_ERROR` | Input validation failed |
| `DUPLICATE_ID` | Entity with this ID already exists |
| `NOT_FOUND` | Entity not found |
| `INTERNAL_ERROR` | Server error |

### Example Error Handling

```graphql
mutation {
  createShell(input: { ... }) {
    success
    shell { id }
    error {
      code
      message
      field
    }
  }
}
```

**Success Response:**
```json
{
  "data": {
    "createShell": {
      "success": true,
      "shell": {
        "id": "https://example.com/shells/new"
      },
      "error": null
    }
  }
}
```

**Error Response:**
```json
{
  "data": {
    "createShell": {
      "success": false,
      "shell": null,
      "error": {
        "code": "DUPLICATE_ID",
        "message": "Shell with ID 'https://example.com/shells/new' already exists",
        "field": null
      }
    }
  }
}
```

### GraphQL Validation Errors

Invalid queries return GraphQL errors:

```json
{
  "errors": [
    {
      "message": "Field 'invalidField' doesn't exist on type 'Shell'",
      "locations": [{"line": 3, "column": 5}]
    }
  ]
}
```

## Performance Best Practices

### 1. Request Only What You Need

GraphQL lets you select specific fields. Avoid requesting unnecessary data:

**Bad:**
```graphql
query {
  shells(limit: 100) {
    id
    idShort
    description { language text }
    assetInformation { assetKind globalAssetId assetType }
    administration { version revision }
    derivedFrom { keys { type value } }
    submodels {
      id
      idShort
      kind
      semanticId { keys { type value } }
      submodelElements { ... }  # Large nested data
    }
  }
}
```

**Good:**
```graphql
query {
  shells(limit: 100) {
    id
    idShort
    assetInformation {
      globalAssetId
    }
  }
}
```

### 2. Use Pagination

Always use `limit` to paginate large result sets:

```graphql
query {
  shells(limit: 50) {
    id
    idShort
  }
}
```

### 3. Leverage DataLoaders

DataLoaders automatically batch queries. This is most effective when:
- Requesting the same entity multiple times
- Loading related entities (shells → submodels)

```graphql
query {
  shell1: shell(id: "...") {
    submodels { id }  # Batched
  }
  shell2: shell(id: "...") {
    submodels { id }  # Batched with shell1
  }
}
```

### 4. Batch Mutations

Use batch mutations instead of multiple individual mutations:

**Bad:**
```graphql
mutation { createShell(input: {...}) { success } }
mutation { createShell(input: {...}) { success } }
mutation { createShell(input: {...}) { success } }
```

**Good:**
```graphql
mutation {
  createShells(inputs: [{...}, {...}, {...}]) {
    success
    shell { id }
  }
}
```

### 5. Avoid Deep Nesting

Deeply nested queries can cause performance issues:

```graphql
# Avoid this if possible
query {
  shell(id: "...") {
    submodels {
      submodelElements {
        ... on SubmodelElementCollection {
          value {
            ... on Property {
              # Very deep nesting
            }
          }
        }
      }
    }
  }
}
```

## Frontend Integration

### Apollo Client (React/TypeScript)

```typescript
import { ApolloClient, InMemoryCache, HttpLink } from '@apollo/client';

const client = new ApolloClient({
  link: new HttpLink({
    uri: 'http://localhost:8080/graphql',
    headers: {
      authorization: `Bearer ${token}`,
    },
  }),
  cache: new InMemoryCache(),
});

// Query example
import { gql, useQuery } from '@apollo/client';

const GET_SHELL = gql`
  query GetShell($id: String!) {
    shell(id: $id) {
      id
      idShort
      assetInformation {
        globalAssetId
      }
    }
  }
`;

function ShellDetail({ shellId }: { shellId: string }) {
  const { loading, error, data } = useQuery(GET_SHELL, {
    variables: { id: shellId },
  });

  if (loading) return <p>Loading...</p>;
  if (error) return <p>Error: {error.message}</p>;

  return (
    <div>
      <h1>{data.shell.idShort}</h1>
      <p>Global Asset ID: {data.shell.assetInformation.globalAssetId}</p>
    </div>
  );
}

// Mutation example
import { gql, useMutation } from '@apollo/client';

const CREATE_SHELL = gql`
  mutation CreateShell($input: ShellInput!) {
    createShell(input: $input) {
      success
      shell {
        id
        idShort
      }
      error {
        code
        message
      }
    }
  }
`;

function CreateShellForm() {
  const [createShell, { loading, error }] = useMutation(CREATE_SHELL);

  const handleSubmit = async (formData: any) => {
    const result = await createShell({
      variables: {
        input: {
          id: formData.id,
          idShort: formData.idShort,
          assetKind: 'INSTANCE',
        },
      },
    });

    if (result.data.createShell.success) {
      console.log('Shell created:', result.data.createShell.shell);
    } else {
      console.error('Error:', result.data.createShell.error);
    }
  };

  return <form onSubmit={handleSubmit}>...</form>;
}
```

### Code Generation

Use `graphql-codegen` to generate TypeScript types from your schema:

```bash
npm install -D @graphql-codegen/cli @graphql-codegen/typescript

# Generate types
npx graphql-codegen --schema http://localhost:8080/graphql --documents './src/**/*.graphql' --target typescript
```

This generates type-safe hooks and types for your queries and mutations.

### Subscription Example

```typescript
import { useSubscription, gql } from '@apollo/client';

const SHELL_UPDATED = gql`
  subscription OnShellUpdated($id: String!) {
    shellUpdated(id: $id) {
      id
      idShort
      assetInformation {
        globalAssetId
      }
    }
  }
`;

function ShellLiveView({ shellId }: { shellId: string }) {
  const { data, loading } = useSubscription(SHELL_UPDATED, {
    variables: { id: shellId },
  });

  if (loading) return <p>Connecting...</p>;

  return (
    <div>
      <h1>Live: {data?.shellUpdated.idShort}</h1>
      <p>Updated: {data?.shellUpdated.assetInformation.globalAssetId}</p>
    </div>
  );
}
```

## Comparison: GraphQL vs REST

| Feature | GraphQL | REST |
|---------|---------|------|
| **Fetching a shell with submodels** | 1 query | 3+ requests |
| **Over-fetching** | Request only needed fields | Returns all fields |
| **Under-fetching** | Single query for nested data | Multiple round trips |
| **Type safety** | Strongly-typed schema | OpenAPI spec optional |
| **Versioning** | Schema evolution | URL versioning (v1, v2, v3) |
| **Real-time** | WebSocket subscriptions | Polling or separate WebSocket |
| **Caching** | Field-level caching | Response-level caching |
| **Learning curve** | Higher (new paradigm) | Lower (familiar pattern) |

## When to Use GraphQL vs REST

**Use GraphQL when:**
- Building interactive UIs that need flexible data fetching
- You need deeply nested data (shells with submodels and elements)
- You want type-safe frontend/backend integration
- Real-time updates are important

**Use REST when:**
- Simple CRUD operations on single resources
- Caching is critical (REST responses are easier to cache)
- You're integrating with tools that expect REST (like BaSyx clients)
- Binary file uploads/downloads (use REST `/blobs` endpoints)

Both APIs are available in Titan-AAS. Choose the one that fits your use case.
