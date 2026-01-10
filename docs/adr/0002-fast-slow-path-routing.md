# ADR-0002: Fast/Slow Path Request Routing

## Status

Accepted

## Context

IDTA-01002 Part 2 defines query modifiers that transform API responses:

| Modifier | Effect |
|----------|--------|
| `level=deep` | Expand nested references |
| `extent=withBlobValue` | Include blob content inline |
| `$value` | Return only the value |
| `$metadata` | Return only metadata |

The presence of these modifiers requires server-side processing:
- Parsing stored JSON
- Applying projections
- Re-serializing response

However, the majority of API calls (estimated 80%+) are simple `GET` requests without modifiers. These should bypass expensive processing.

## Decision

Implement **two distinct request paths**:

### Fast Path (No Modifiers)

```
Client Request → Cache Check → DB doc_bytes → Stream Response
```

- No JSON parsing
- No Pydantic model instantiation
- Direct byte streaming from PostgreSQL or Redis cache
- Target: <10ms p50 latency

### Slow Path (With Modifiers)

```
Client Request → DB doc → Parse → Apply Modifiers → Serialize → Response
```

- Full Pydantic model parsing
- Projection/transformation logic
- Re-serialization to JSON
- Target: <100ms p50 latency

### Implementation

```python
class PathRouter:
    def is_fast_path(self, request: Request) -> bool:
        """Determine if request can use fast path."""
        # Fast path requires:
        # 1. GET method
        # 2. No query modifiers (level, extent, etc.)
        # 3. No $value, $metadata projections
        if request.method != "GET":
            return False

        params = request.query_params
        slow_params = {"level", "extent", "content"}
        if any(p in params for p in slow_params):
            return False

        # Check for $value/$metadata in path
        if "$" in request.url.path:
            return False

        return True
```

## Consequences

### Positive

- **Optimal performance for common case**: Simple reads hit target latency.
- **Full IDTA compliance**: All modifiers supported via slow path.
- **Resource efficiency**: Avoids unnecessary parsing/serialization.
- **Caching synergy**: Fast path leverages Redis byte cache directly.

### Negative

- **Code duplication**: Two code paths for similar operations.
- **Testing complexity**: Must test both paths for each endpoint.
- **Potential inconsistency**: Must ensure both paths return equivalent results.

### Neutral

- **Transparent to clients**: Routing decision is internal.
- **Measurable**: Easy to track fast vs slow path usage in metrics.
