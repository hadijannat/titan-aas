# Titan-AAS Architecture

Asset Administration Shell runtime targeting IDTA-01001/01002 standards.

---

## Quick Reference

```
src/titan/
├── core/           # Domain models (AAS, Submodel, SubmodelElements)
├── api/            # REST API endpoints (/shells, /submodels, /concept-descriptions)
├── persistence/    # PostgreSQL (JSONB + canonical bytes)
├── cache/          # Redis (cache-aside)
├── events/         # Event bus (single-writer + micro-batching)
├── connectors/     # MQTT integrations
├── security/       # OIDC auth + RBAC/ABAC + request signing
├── storage/        # Blob storage (local/S3/GCS/Azure)
├── tenancy/        # Multi-tenant isolation
├── observability/  # Metrics, tracing, profiling
├── compat/         # AASX import/export compatibility
├── distributed/    # Leader election / coordination
├── jobs/           # Background jobs
├── plugins/        # Extension hooks (planned)
├── graphql/        # GraphQL API (optional)
└── cli/            # Command-line interface
```

---

## Module Breakdown

### core/ - Domain Models
**What:** IDTA-01001 AAS models using Pydantic v2 with strict validation.

| File | Purpose |
|------|---------|
| `model/aas.py` | AssetAdministrationShell, AssetInformation |
| `model/submodel.py` | Submodel container |
| `model/submodel_elements.py` | 11 element types (Property, Blob, File, Entity, etc.) |
| `model/registry.py` | Descriptors for Registry API |
| `ids.py` | Base64URL encoding/decoding for path segments |
| `canonicalize.py` | Canonical JSON via orjson (fastest path) |
| `projection.py` | IDTA modifiers ($value, $metadata, level, extent) |

### api/ - REST Layer
**What:** IDTA-01002 Part 2 REST endpoints with fast/slow path routing.

| File | Purpose |
|------|---------|
| `routers/aas_repository.py` | `/shells/*` CRUD |
| `routers/submodel_repository.py` | `/submodels/*` CRUD |
| `routers/concept_description_repository.py` | `/concept-descriptions/*` CRUD |
| `routers/registry.py` | `/shell-descriptors/*`, `/submodel-descriptors/*` |
| `routers/websocket.py` | Real-time event subscriptions |
| `routing.py` | Fast/slow path detection |
| `errors.py` | IDTA-compliant error responses |
| `pagination.py` | Cursor-based pagination |

**Fast vs Slow Path:**
- **Fast:** No modifiers → stream pre-serialized bytes directly (latency depends on cache/network)
- **Slow:** Has modifiers → deserialize, apply projection, re-serialize

### persistence/ - Database
**What:** PostgreSQL async storage with dual-column pattern.

| File | Purpose |
|------|---------|
| `tables.py` | ORM models (JSONB for queries + BYTEA for streaming) |
| `repositories.py` | Repository pattern with fast/slow query methods |
| `registry.py` | Descriptor storage for AAS/Submodel Registry |
| `migrations/` | Alembic version-controlled migrations |

**Key Pattern:** Store both `doc` (JSONB, GIN-indexed) and `doc_bytes` (canonical JSON). Queries use JSONB, reads stream bytes.

### cache/ - Redis
**What:** Cache-aside storage for serialized bytes with TTL-based expiry.

| File | Purpose |
|------|---------|
| `redis.py` | RedisCache with get/set/delete operations |
| `keys.py` | Cache key generation patterns |

### events/ - Event System
**What:** Single-writer pattern for consistency and event broadcasting.

| File | Purpose |
|------|---------|
| `schemas.py` | AasEvent, SubmodelEvent, EventType enum |
| `publisher.py` | publish_aas_event, publish_submodel_event helpers |
| `bus.py` | InMemoryEventBus interface |
| `redis_bus.py` | RedisStreamEventBus for distributed mode |
| `worker.py` | SingleWriter (sequential processing) |
| `batch_writer.py` | MicroBatchWriter (windowed flush to downstream sinks) |

### security/ - Auth
**What:** OIDC token validation, RBAC enforcement, audit logging.

| File | Purpose |
|------|---------|
| `oidc.py` | TokenValidator, JWKS caching |
| `rbac.py` | Role→Permission mapping (READER, WRITER, ADMIN) |
| `abac.py` | ABAC policy engine (tenant isolation, time/IP policies) |
| `deps.py` | FastAPI dependencies (require_read, require_write) |
| `audit.py` | AuditLog for security events |
| `signing.py` | Request signing helpers |

### connectors/ - Integrations
**What:** External event broadcasting (MQTT for IoT, WebSocket for browsers).

| File | Purpose |
|------|---------|
| `mqtt.py` | MqttPublisher, topics: `titan/{entity}/{id}/{action}` |

---

## Rationale (Prototype Track)

This section documents why Titan-AAS includes certain components instead of delegating
everything to external SDKs. These choices are *deliberate and scoped* for a prototype.

### AASX Import/Export
- **Why it exists:** Titan needs deterministic, canonical payloads for fast-path streaming
  and reproducible tests. A minimal in-tree AASX compatibility layer keeps the export/import
  surface small and testable.
- **What it is not:** A drop-in replacement for mature SDKs (e.g., BaSyx). For full-featured
  authoring, transformation, or advanced validation, use external tooling.

### Semantic Validation
- **Default mode:** Lenient. Missing ConceptDescriptions or semantic definitions produce
  warnings, not errors.
- **Why:** Semantic IDs are optional and can reference arbitrary vocabularies; rejecting
  valid AAS content would be incorrect for general use.

### Middleware Wrappers
- **Why it exists:** Centralizes configuration and defaults for standard Starlette middleware
  (CORS, gzip, security headers) and keeps settings in one place.
- **Scope:** No custom protocol logic; it is configuration glue, not a bespoke middleware stack.

### Dual Observability & Event Transports
- **Prometheus + OpenTelemetry:** Prometheus is for scrape-based operational metrics; OTel is
  for distributed tracing. Both are optional and can be enabled independently.
- **WebSocket + MQTT:** WebSocket targets browser/UI consumers; MQTT targets edge/IoT brokers.
  If you only need one, disable the other.

### storage/ - Blob Storage
**What:** Externalized storage for large File/Blob elements.

| File | Purpose |
|------|---------|
| `base.py` | BlobStorage interface |
| `local.py` | LocalBlobStorage (filesystem) |
| `s3.py` | S3BlobStorage (AWS/MinIO) |
| `gcs.py` | GCSBlobStorage (Google Cloud Storage) |
| `azure.py` | AzureBlobStorage (Azure Blob Storage) |

### Other Modules

| Module | Purpose |
|--------|---------|
| `tenancy/` | Multi-tenant context, RLS policies |
| `observability/` | OpenTelemetry tracing, Prometheus metrics |
| `plugins/` | Plugin hooks for extensibility |
| `jobs/` | Background job queue |
| `graphql/` | GraphQL API (alternative to REST) |
| `cli/` | Command-line: serve, import, export, validate |
| `compat/` | AASX import/export, XML serialization |
| `distributed/` | Leader election and coordination |

---

## Data Flows

### Write Operation (POST /shells)
```
Request → Validate (Pydantic) → Publish Event → SingleWriter
                                                    ↓
                                    ┌───────────────┴───────────────┐
                                    ↓                               ↓
                              PostgreSQL                        Redis Cache
                           (JSONB + bytes)                     (set + invalidate)
                                    ↓                               ↓
                              Event Broadcast ──────────────────────┘
                                    ↓
                           MQTT / WebSocket
```

### Read Operation (GET /shells/{id})
```
Request → Check Redis Cache ──hit──→ Stream bytes → Response
              │
             miss
              ↓
        Query PostgreSQL doc_bytes
              ↓
        Update Redis Cache
              ↓
        Stream bytes → Response
```

---

## Key Design Decisions

1. **Dual Storage:** JSONB for queries + doc_bytes for streaming (no deserialize on reads)
2. **Single Writer:** All writes go through event bus → sequential processing (no races)
3. **Cache-Aside:** Redis caches serialized bytes; Pub/Sub invalidates across instances
4. **Fast Path:** Default reads bypass deserialization entirely
5. **IDTA Alignment:** Targets IDTA-01001/01002; coverage is tracked in the conformance matrix

---

## Running

```bash
# Development server
uv run -- uvicorn titan.api.app:app --reload --port 8080

# Run unit tests
uv run -- pytest tests/unit -v

# Run integration tests (needs Docker)
uv run -- pytest tests/integration -v

# CLI commands
uv run -- titan serve              # Start server
uv run -- titan import-aasx file.aasx  # Import AASX package
uv run -- titan export-aasx --id "urn:..." out.aasx
uv run -- titan validate file.json # Validate AAS JSON

# API docs
open http://localhost:8080/docs    # Swagger UI
open http://localhost:8080/redoc   # ReDoc
```

---

## Test Structure

```
tests/
├── unit/              # Fast, no external deps
│   ├── core/          # Model validation
│   ├── api/           # Router tests (mocked DB)
│   ├── events/        # Event bus tests
│   ├── cache/         # Cache tests (mocked Redis)
│   └── security/      # Auth tests
├── integration/       # Real PostgreSQL/Redis via testcontainers
│   ├── test_api.py    # Full API tests
│   ├── test_registry.py
│   └── test_websocket_events.py
└── contract/          # Schemathesis spec compliance
```

---

## Configuration

Key environment variables (see `src/titan/config.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | required | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `EVENT_BUS_BACKEND` | `redis` | Event bus backend: `redis` or `memory` |
| `MQTT_BROKER` | none | MQTT broker hostname (optional) |
| `OIDC_ISSUER` | none | OIDC provider URL (optional) |
| `BLOB_STORAGE_TYPE` | `local` | Blob storage: `local`, `s3`, `gcs`, `azure` |
| `BLOB_STORAGE_PATH` | `/var/lib/titan/blobs` | Local blob storage root |
| `BLOB_INLINE_THRESHOLD` | `65536` | Inline blob bytes threshold (bytes) |
| `S3_BUCKET` | none | S3 bucket name |
| `GCS_BUCKET` | none | GCS bucket name |
| `AZURE_CONTAINER` | none | Azure blob container name |
| `ENABLE_SECURITY_HEADERS` | `true` | Add OWASP security headers |
| `ENABLE_HSTS` | `false` | Enable HSTS (HTTPS only) |
| `ENABLE_ABAC` | `false` | Enable ABAC policy evaluation |
| `ABAC_DEFAULT_DENY` | `true` | Deny when no ABAC policy applies |
| `ENABLE_METRICS` | `true` | Prometheus metrics |
| `ENABLE_TRACING` | `true` | OpenTelemetry tracing |
