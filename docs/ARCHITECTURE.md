# Titan-AAS Architecture

Industrial-grade Asset Administration Shell runtime implementing IDTA-01001/01002 standards.

---

## Quick Reference

```
src/titan/
├── core/           # Domain models (AAS, Submodel, SubmodelElements)
├── api/            # REST API endpoints (/shells, /submodels)
├── persistence/    # PostgreSQL (JSONB + canonical bytes)
├── cache/          # Redis (cache-aside + distributed invalidation)
├── events/         # Event bus (single-writer pattern)
├── connectors/     # MQTT, WebSocket integrations
├── security/       # OIDC auth + RBAC
├── storage/        # Blob storage (S3/local)
├── tenancy/        # Multi-tenant isolation
├── observability/  # Metrics, tracing, profiling
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
| `routers/registry.py` | `/shell-descriptors/*`, `/submodel-descriptors/*` |
| `routers/websocket.py` | Real-time event subscriptions |
| `routing.py` | Fast/slow path detection |
| `errors.py` | IDTA-compliant error responses |
| `pagination.py` | Cursor-based pagination |

**Fast vs Slow Path:**
- **Fast:** No modifiers → stream pre-serialized bytes directly (sub-ms)
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
**What:** Distributed cache with invalidation across instances.

| File | Purpose |
|------|---------|
| `redis.py` | RedisCache with get/set/delete operations |
| `keys.py` | Cache key generation patterns |
| `invalidation.py` | Pub/Sub broadcaster for cache sync |

### events/ - Event System
**What:** Single-writer pattern for consistency and event broadcasting.

| File | Purpose |
|------|---------|
| `schemas.py` | AasEvent, SubmodelEvent, EventType enum |
| `publisher.py` | publish_aas_event, publish_submodel_event helpers |
| `bus.py` | InMemoryEventBus interface |
| `redis_bus.py` | RedisStreamEventBus for distributed mode |
| `worker.py` | SingleWriter (sequential processing) |

### security/ - Auth
**What:** OIDC token validation, RBAC enforcement, audit logging.

| File | Purpose |
|------|---------|
| `oidc.py` | TokenValidator, JWKS caching |
| `rbac.py` | Role→Permission mapping (READER, WRITER, ADMIN) |
| `deps.py` | FastAPI dependencies (require_read, require_write) |
| `audit.py` | AuditLog for security events |

### connectors/ - Integrations
**What:** External event broadcasting (MQTT for IoT, WebSocket for browsers).

| File | Purpose |
|------|---------|
| `mqtt.py` | MqttPublisher, topics: `titan/{entity}/{id}/{action}` |

### storage/ - Blob Storage
**What:** Externalized storage for large File/Blob elements.

| File | Purpose |
|------|---------|
| `base.py` | BlobStorage interface |
| `local.py` | LocalBlobStorage (filesystem) |
| `s3.py` | S3BlobStorage (AWS/MinIO) |

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
5. **IDTA Compliance:** Full IDTA-01001/01002 spec implementation

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
| `REDIS_URL` | `redis://localhost` | Redis connection |
| `MQTT_BROKER` | none | MQTT broker hostname (optional) |
| `OIDC_ISSUER` | none | OIDC provider URL (optional) |
| `STORAGE_BACKEND` | `local` | Blob storage: `local` or `s3` |
| `ENABLE_METRICS` | `true` | Prometheus metrics |
| `ENABLE_TRACING` | `false` | OpenTelemetry tracing |
