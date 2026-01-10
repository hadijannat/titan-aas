# Benchmarks

Titan-AAS provides a reproducible benchmarking script and Locust load tests.

## Prerequisites

- Titan-AAS running locally or in a test environment
- Postgres + Redis configured
- Locust available via the dev dependency group

## Run the benchmark

```bash
uv sync --group dev
uv run -- bash scripts/benchmark.sh
```

Environment variables you can override:

- `TITAN_HOST` (default: `http://localhost:8080`)
- `LOCUST_USERS` (default: `100`)
- `LOCUST_SPAWN_RATE` (default: `10`)
- `LOCUST_RUN_TIME` (default: `60s`)
- `OUTPUT_DIR` (default: `./benchmark-results`)

## Recording baselines

When reporting results, include:

- Hardware and OS details
- Postgres and Redis versions + configuration
- Dataset size and seeded assets
- p50/p95/p99 latency, RPS, and error rate

Store baseline summaries in `docs/benchmarks/` or attach to release notes.
