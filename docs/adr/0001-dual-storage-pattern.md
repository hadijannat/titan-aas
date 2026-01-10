# ADR-0001: Dual Storage Pattern (JSONB + Bytes)

## Status

Accepted

## Context

Titan-AAS needs to store Asset Administration Shells and Submodels in PostgreSQL. The IDTA-01002 specification requires:

1. **Query capability**: Find shells/submodels by semantic ID, idShort, asset type, etc.
2. **Fast streaming**: Return exact JSON bytes to clients without re-serialization.
3. **Consistency**: Ensure clients receive exactly what was stored.

Traditional approaches have trade-offs:
- **JSONB only**: Enables queries but requires re-serialization on every read, which may alter formatting.
- **BYTEA only**: Preserves bytes exactly but prevents database-level queries.
- **TEXT/VARCHAR**: Same issues as BYTEA plus encoding concerns.

## Decision

Store each AAS/Submodel record with dual columns:

```sql
CREATE TABLE shells (
    id SERIAL PRIMARY KEY,
    identifier TEXT UNIQUE NOT NULL,
    identifier_b64 TEXT UNIQUE NOT NULL,
    doc JSONB NOT NULL,         -- For queries and writes
    doc_bytes BYTEA NOT NULL,   -- For streaming reads
    etag TEXT NOT NULL,         -- SHA256 of doc_bytes for caching
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_shells_doc ON shells USING GIN (doc);
```

**Write path**:
1. Parse incoming JSON into Pydantic model (validation)
2. Serialize to canonical JSON bytes (preserves formatting)
3. Store in both `doc` (parsed) and `doc_bytes` (raw)
4. Compute and store `etag`

**Read path** (fast):
1. Read `doc_bytes` directly from database
2. Stream bytes to client with `etag` header
3. No parsing, no re-serialization

**Query path** (slow):
1. Query against `doc` JSONB with PostgreSQL operators
2. Parse results through Pydantic for response building

## Consequences

### Positive

- **Zero re-serialization overhead**: Clients receive exact bytes that were stored.
- **Full query capability**: JSONB operators enable complex filtering.
- **ETag support**: Content-based cache validation without parsing.
- **Fast path performance**: 10ms p50 latency achievable on reads.

### Negative

- **2x storage footprint**: Each record stored twice (JSONB + BYTEA).
- **Write complexity**: Must keep both columns synchronized.
- **Migration complexity**: Schema changes require updating both representations.

### Neutral

- **No change to client compatibility**: Wire format remains standard JSON.
- **PostgreSQL-specific**: Other databases would need different approaches.
