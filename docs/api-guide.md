# Titan-AAS API Guide

This guide covers the Titan-AAS REST API, which implements the IDTA-01002 Asset Administration Shell API specification.

## Base URL

```
http://localhost:8080
```

## Authentication

When OIDC is enabled, all endpoints require a valid Bearer token:

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/shells
```

## Endpoints Overview

| Category | Base Path | Description |
|----------|-----------|-------------|
| AAS Repository | `/shells` | Manage Asset Administration Shells |
| Submodel Repository | `/submodels` | Manage Submodels |
| Registry | `/shell-descriptors` | AAS Descriptors for discovery |
| Discovery | `/lookup/shells` | Find AAS by asset IDs |
| Health | `/health` | Service health checks |

---

## AAS Repository API

### List All Shells

```bash
GET /shells
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max results (default: 100) |
| `cursor` | string | Pagination cursor |
| `assetIds` | string | Filter by asset ID (Base64URL encoded) |

**Example:**
```bash
curl http://localhost:8080/shells?limit=10
```

**Response:**
```json
{
  "result": [
    {
      "modelType": "AssetAdministrationShell",
      "id": "urn:example:aas:1",
      "idShort": "ExampleAAS",
      "assetInformation": {
        "assetKind": "Instance",
        "globalAssetId": "urn:example:asset:1"
      }
    }
  ],
  "paging_metadata": {
    "cursor": "eyJpZCI6MTB9"
  }
}
```

### Get Shell by ID

```bash
GET /shells/{aasIdentifier}
```

**Path Parameters:**
- `aasIdentifier`: Base64URL-encoded AAS ID (no padding)

**Example:**
```bash
# Encode: urn:example:aas:1 -> dXJuOmV4YW1wbGU6YWFzOjE
curl http://localhost:8080/shells/dXJuOmV4YW1wbGU6YWFzOjE
```

### Create Shell

```bash
POST /shells
Content-Type: application/json
```

**Request Body:**
```json
{
  "modelType": "AssetAdministrationShell",
  "id": "urn:example:aas:new",
  "idShort": "NewAAS",
  "assetInformation": {
    "assetKind": "Instance",
    "globalAssetId": "urn:example:asset:new"
  }
}
```

### Update Shell

```bash
PUT /shells/{aasIdentifier}
Content-Type: application/json
```

### Delete Shell

```bash
DELETE /shells/{aasIdentifier}
```

---

## Submodel Repository API

### List All Submodels

```bash
GET /submodels
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max results (default: 100) |
| `cursor` | string | Pagination cursor |
| `semanticId` | string | Filter by semantic ID |
| `idShort` | string | Filter by idShort |

### Get Submodel by ID

```bash
GET /submodels/{submodelIdentifier}
```

**Modifiers (Query Parameters):**
| Modifier | Description |
|----------|-------------|
| `level=deep` | Include nested elements |
| `level=core` | Only top-level properties |
| `content=value` | Values only (no metadata) |
| `content=metadata` | Metadata only (no values) |
| `extent=withBlobValue` | Include blob content |

**Example with modifiers:**
```bash
curl "http://localhost:8080/submodels/{id}?level=deep&content=value"
```

### Get Submodel Element

```bash
GET /submodels/{submodelIdentifier}/submodel-elements/{idShortPath}
```

**idShortPath Examples:**
- Simple: `Temperature`
- Nested: `Sensors.Temperature`
- Collection index: `Readings[0]`
- Deep path: `Device.Sensors.Temperature.Value`

### Update Submodel Element

```bash
PUT /submodels/{submodelIdentifier}/submodel-elements/{idShortPath}
```

### Invoke Operation

```bash
POST /submodels/{submodelIdentifier}/submodel-elements/{idShortPath}/invoke
```

**Request Body:**
```json
{
  "inputArguments": [
    {
      "value": {
        "modelType": "Property",
        "idShort": "input1",
        "valueType": "xs:string",
        "value": "test"
      }
    }
  ]
}
```

---

## Blob/File Handling

### Get Attachment

```bash
GET /submodels/{id}/submodel-elements/{path}/attachment
```

Returns the raw file content with appropriate Content-Type.

### Upload Attachment

```bash
PUT /submodels/{id}/submodel-elements/{path}/attachment
Content-Type: application/octet-stream

<binary data>
```

---

## Registry API

### List Shell Descriptors

```bash
GET /shell-descriptors
```

### Get Shell Descriptor

```bash
GET /shell-descriptors/{aasIdentifier}
```

### Register Shell Descriptor

```bash
POST /shell-descriptors
```

**Request Body:**
```json
{
  "id": "urn:example:aas:1",
  "idShort": "ExampleAAS",
  "endpoints": [
    {
      "interface": "AAS-3.0",
      "protocolInformation": {
        "href": "http://localhost:8080/shells/dXJuOmV4YW1wbGU6YWFzOjE"
      }
    }
  ]
}
```

---

## Discovery API

### Lookup Shells by Asset ID

```bash
GET /lookup/shells?assetIds={base64url-encoded-asset-id}
```

**Example:**
```bash
# Find AAS for asset urn:example:asset:1
curl "http://localhost:8080/lookup/shells?assetIds=dXJuOmV4YW1wbGU6YXNzZXQ6MQ"
```

---

## Real-time Events

### WebSocket Subscription

```javascript
const ws = new WebSocket('ws://localhost:8080/events');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.type, data.payload);
};

// Subscribe to specific events
ws.send(JSON.stringify({
  action: 'subscribe',
  topics: ['aas.*', 'submodel.updated']
}));
```

### MQTT Events

Events are published to the MQTT broker on topic `titan/events/{type}`:

```bash
mosquitto_sub -h localhost -t 'titan/events/#'
```

**Event Types:**
- `aas.created`, `aas.updated`, `aas.deleted`
- `submodel.created`, `submodel.updated`, `submodel.deleted`
- `submodel-element.updated`

---

## Error Responses

All errors follow the IDTA-01002 format:

```json
{
  "messages": [
    {
      "code": "404",
      "messageType": "Error",
      "text": "Asset Administration Shell not found",
      "timestamp": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**Common Status Codes:**
| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 204 | No Content (successful delete) |
| 400 | Bad Request (validation error) |
| 401 | Unauthorized (missing/invalid token) |
| 403 | Forbidden (insufficient permissions) |
| 404 | Not Found |
| 409 | Conflict (duplicate ID) |
| 422 | Unprocessable Entity |
| 500 | Internal Server Error |

---

## Base64URL Encoding

All identifiers in URL paths must be Base64URL encoded **without padding**.

**Python:**
```python
import base64

def encode_id(identifier: str) -> str:
    return base64.urlsafe_b64encode(identifier.encode()).rstrip(b'=').decode()

def decode_id(encoded: str) -> str:
    padded = encoded + '=' * (4 - len(encoded) % 4)
    return base64.urlsafe_b64decode(padded).decode()
```

**JavaScript:**
```javascript
function encodeId(id) {
  return btoa(id).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function decodeId(encoded) {
  const padded = encoded + '='.repeat((4 - encoded.length % 4) % 4);
  return atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
}
```

---

## Rate Limiting

Default limits (configurable):
- 1000 requests/minute per IP
- 10000 requests/minute with valid token

Headers in response:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 950
X-RateLimit-Reset: 1705312800
```

---

## Health Endpoints

### Liveness Probe

```bash
GET /health/live
```

Returns `200 OK` if the service is running.

### Readiness Probe

```bash
GET /health/ready
```

Returns `200 OK` if the service can handle requests (DB, Redis, MQTT connected).

### Full Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "up", "latency_ms": 2},
    "redis": {"status": "up", "latency_ms": 1},
    "mqtt": {"status": "up"}
  }
}
```

---

## Metrics

Prometheus metrics are exposed at:

```bash
GET /metrics
```

Key metrics:
- `http_requests_total{method, path, status}`
- `http_request_duration_seconds{method, path}`
- `cache_hits_total`, `cache_misses_total`
- `db_query_duration_seconds{query_type}`
- `event_queue_size`
