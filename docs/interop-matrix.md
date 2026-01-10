# IDTA Service Profile Interoperability Matrix

This document provides detailed interoperability information for Titan-AAS against the IDTA Part 2 API v3.1.1 specification. It complements [conformance-matrix.md](conformance-matrix.md) with practical integration details.

## API Version Information

| Property | Value |
|----------|-------|
| IDTA Specification | Part 2 API v3.1.1 (Release 25-01) |
| OpenAPI Version | 3.0.3 |
| Base Path | `/api/v1` |
| Content-Type | `application/json` |

## Implemented Service Profiles

### AAS Repository (SSP-001/002)

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/shells` | GET | Full | Pagination, filtering |
| `/shells` | POST | Full | Returns 201 + Location |
| `/shells/{aasIdentifier}` | GET | Full | Base64URL encoded ID |
| `/shells/{aasIdentifier}` | PUT | Full | Full replacement |
| `/shells/{aasIdentifier}` | DELETE | Full | Returns 204 |
| `/shells/{aasIdentifier}/asset-information` | GET | Full | Asset info extraction |
| `/shells/{aasIdentifier}/asset-information` | PUT | Full | Asset info update |
| `/shells/{aasIdentifier}/submodel-references` | GET | Full | Paginated list |
| `/shells/{aasIdentifier}/submodel-references` | POST | Full | Add submodel ref |
| `/shells/{aasIdentifier}/submodel-references/{submodelIdentifier}` | DELETE | Full | Remove submodel ref |

### Submodel Repository (SSP-001/002)

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/submodels` | GET | Full | Pagination, filtering |
| `/submodels` | POST | Full | Returns 201 + Location |
| `/submodels/{submodelIdentifier}` | GET | Full | Base64URL encoded ID |
| `/submodels/{submodelIdentifier}` | PUT | Full | Full replacement |
| `/submodels/{submodelIdentifier}` | DELETE | Full | Returns 204 |
| `/submodels/{submodelIdentifier}/$value` | GET | Full | Value-only payload |
| `/submodels/{submodelIdentifier}/$metadata` | GET | Full | Metadata-only |
| `/submodels/{submodelIdentifier}/$path` | GET | Full | Path references |
| `/submodels/{submodelIdentifier}/submodel-elements` | GET | Full | Paginated elements |
| `/submodels/{submodelIdentifier}/submodel-elements/{idShortPath}` | GET/PUT/DELETE | Full | Nested element access |

### Registry (SSP-001/002)

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/shell-descriptors` | GET | Full | Pagination, filtering |
| `/shell-descriptors` | POST | Full | Returns 201 |
| `/shell-descriptors/{aasIdentifier}` | GET/PUT/DELETE | Full | CRUD operations |
| `/shell-descriptors/{aasIdentifier}/submodel-descriptors` | GET | Full | List submodel descriptors |
| `/shell-descriptors/{aasIdentifier}/submodel-descriptors` | POST | Full | Add submodel descriptor |
| `/submodel-descriptors` | GET | Full | Standalone submodel registry |
| `/submodel-descriptors` | POST | Full | Returns 201 |
| `/submodel-descriptors/{submodelIdentifier}` | GET/PUT/DELETE | Full | CRUD operations |

### Discovery (SSP-002)

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| `/lookup/shells` | GET | Full | Asset ID lookup |
| `/lookup/shells` | POST | Full | Bulk asset ID lookup |

## Query Parameters

### Pagination

| Parameter | Type | Default | Max | Endpoints |
|-----------|------|---------|-----|-----------|
| `cursor` | string | - | - | All list endpoints |
| `limit` | integer | 100 | 1000 | All list endpoints |

### Filtering (Shells)

| Parameter | Type | Format | Example |
|-----------|------|--------|---------|
| `idShort` | string | Exact match | `?idShort=MyAAS` |
| `assetIds` | string | Base64URL JSON array | `?assetIds=W3sibmFtZSI6...` |

### Filtering (Submodels)

| Parameter | Type | Format | Example |
|-----------|------|--------|---------|
| `idShort` | string | Exact match | `?idShort=Nameplate` |
| `semanticId` | string | Base64URL encoded | `?semanticId=aHR0cHM6Ly...` |
| `kind` | string | Enum: Instance, Template | `?kind=Instance` |

### Content Modifiers

| Parameter | Values | Endpoints | Description |
|-----------|--------|-----------|-------------|
| `level` | `deep`, `core` | `/shells`, `/submodels` | Element depth |
| `extent` | `withBlobValue`, `withoutBlobValue` | `/submodels` | Blob inclusion |
| `content` | `value`, `metadata`, `reference`, `path` | `/submodel-elements` | Response format |

## Content Negotiation

### Supported Media Types

| Media Type | Serialization | Notes |
|------------|---------------|-------|
| `application/json` | JSON | Default, ORJSON optimized |
| `application/xml` | XML | Limited support |
| `application/octet-stream` | Binary | Blob content |

### Accept Header Handling

```
Accept: application/json           -> JSON response
Accept: application/json;charset=utf-8 -> JSON response (UTF-8)
Accept: */*                        -> JSON response (default)
```

## Error Responses

All error responses follow IDTA-compliant format:

```json
{
  "messages": [
    {
      "code": "NotFound",
      "messageType": "Error",
      "text": "AAS with identifier 'xyz' not found",
      "timestamp": "2026-01-10T12:34:56Z"
    }
  ]
}
```

### HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | OK | Successful GET/PUT |
| 201 | Created | Successful POST |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid input |
| 401 | Unauthorized | Missing/invalid auth |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Duplicate ID |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |

## Headers

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Conditional | Bearer token (when OIDC enabled) |
| `Content-Type` | POST/PUT | `application/json` |
| `Accept` | No | Response format preference |
| `X-Request-ID` | No | Client request correlation |
| `X-Correlation-ID` | No | Cross-service correlation |

### Response Headers

| Header | Description |
|--------|-------------|
| `X-Request-ID` | Echo or generated request ID |
| `X-Correlation-ID` | Echo or generated correlation ID |
| `X-Trace-ID` | OpenTelemetry trace ID |
| `ETag` | Resource version for caching |
| `Cache-Control` | Caching directives |
| `Location` | Created resource URL (201 responses) |

## Identifier Encoding

All identifiers in URL paths must be Base64URL encoded (RFC 4648 Section 5):

```
Original: https://example.com/aas/12345
Encoded:  aHR0cHM6Ly9leGFtcGxlLmNvbS9hYXMvMTIzNDU

URL path: /shells/aHR0cHM6Ly9leGFtcGxlLmNvbS9hYXMvMTIzNDU
```

No padding (`=`) characters are included.

## Rate Limiting

| Limit | Default | Header |
|-------|---------|--------|
| Requests per window | 100 | `X-RateLimit-Limit` |
| Window duration | 60s | - |
| Remaining requests | - | `X-RateLimit-Remaining` |
| Reset timestamp | - | `X-RateLimit-Reset` |

When rate limited, response includes `Retry-After` header.

## Known Limitations

| Feature | Status | Notes |
|---------|--------|-------|
| SSP-003 Bulk operations | Not implemented | Use individual CRUD |
| SSP-004 Advanced queries | Not implemented | Basic filters only |
| AASX File Server SSP-001 | Partial | Via `/packages` endpoints |
| Template-only profiles | Not implemented | Full submodels only |
| External vocab validation | Not implemented | No code list enforcement |

## Tested Integrations

| System | Version | Status | Notes |
|--------|---------|--------|-------|
| AASX Package Explorer | 2024.x | Compatible | Import/export tested |
| BaSyx AAS Server | v2 | Compatible | Federation tested |
| Eclipse BaSyx | 2.0.x | Compatible | DTR sync tested |
| Catena-X EDC | 0.7.x | Compatible | Asset registration tested |

## Self-Description

The server provides self-description at:

```
GET /description
```

Response includes:
- Supported profiles
- API versions
- Service capabilities
