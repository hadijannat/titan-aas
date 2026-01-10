# titan-aas

Titan-AAS is a production-oriented Asset Administration Shell (AAS) runtime optimized for read-heavy industrial workloads. It follows a contract-first, write-validate / read-stream architecture and targets the IDTA Release 25-01 baseline.

## Spec baseline (pinned)
- IDTA-01001 Part 1 Metamodel v3.1.2
- IDTA-01002 Part 2 API v3.1.1
- IDTA-01003-a Data Specification IEC 61360 v3.1.1
- IDTA-01004 Security v3.0.1

## Architecture summary
- Write path: validate with Pydantic v2, canonicalize JSON, store JSONB + canonical bytes
- Read path: stream canonical bytes directly from Redis/Postgres (no model hydration)
- Fast path / slow path routing to protect latency under modifier-heavy queries
- Single writer: all writes become events; one worker serializes persistence and cache updates

## Repository layout
```
./specs/                 Vendored OpenAPI + schemas (IDTA-01002)
./src/titan/             Runtime code
./deployment/            Docker and deploy artifacts
./tests/                 Unit, integration, contract, load tests
```

## Quick start (developer)
```
uv sync
uv run -- uvicorn titan.api.app:app --host 0.0.0.0 --port 8080
```

## Vendoring the AAS OpenAPI specs
Pin a tag or commit from admin-shell-io/aas-specs-api and record checksums:
```
mkdir -p specs
# Option A: submodule
# git submodule add https://github.com/admin-shell-io/aas-specs-api specs/aas-specs-api
# git -C specs/aas-specs-api checkout <tag-or-commit>
# sha256sum -b specs/aas-specs-api/**/*.yaml > specs/checksums.txt
```

## Tests
```
uv run -- pytest -q
```

## Notes
- BaSyx Python SDK is used for ingestion and compatibility tooling only.
- Runtime paths never depend on BaSyx object hydration.

