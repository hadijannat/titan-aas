# Benchmarks

Titan-AAS provides reproducible benchmarking infrastructure for measuring API performance under load. This document describes the methodology and provides reference results.
**All numbers below are illustrative unless accompanied by published artifacts** (e.g., `benchmark-results.json`
in `docs/benchmarks/` with the exact methodology and environment). Do not treat these figures as guarantees.

## Quick Start

```bash
# Install dev dependencies
uv sync --group dev

# Run benchmark suite
uv run -- bash scripts/benchmark.sh
```

## Benchmark Methodology

### Hardware Reference

Results should be compared against similar hardware profiles:

| Profile | CPU | Memory | Storage | Network |
|---------|-----|--------|---------|---------|
| Development | 4 vCPU | 8GB RAM | SSD | Local |
| CI/CD | 2 vCPU | 8GB RAM | SSD | GitHub Actions |
| Production | 8 vCPU | 32GB RAM | NVMe SSD | 10Gbps |

### Dataset Profiles

| Profile | AAS Count | Submodels | Avg Payload | Total Size |
|---------|-----------|-----------|-------------|------------|
| Small | 100 | 500 | 2KB | ~1MB |
| Medium | 1,000 | 5,000 | 5KB | ~25MB |
| Large | 10,000 | 50,000 | 5KB | ~250MB |
| XLarge | 100,000 | 500,000 | 3KB | ~1.5GB |

### Configuration

Standard test configuration:

```env
# Titan-AAS Settings
TITAN_ENV=production
DATABASE_URL=postgresql+asyncpg://titan:titan@localhost:5432/titan
REDIS_URL=redis://localhost:6379/0
ENABLE_HTTP_CACHING=true
ENABLE_COMPRESSION=true
ENABLE_RATE_LIMITING=false  # Disabled for benchmarks
```

PostgreSQL tuning:

```
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 32MB
maintenance_work_mem = 128MB
max_connections = 200
```

Redis configuration:

```
maxmemory 512mb
maxmemory-policy allkeys-lru
```

## Running Benchmarks

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TITAN_HOST` | `http://localhost:8080` | Target API endpoint |
| `LOCUST_USERS` | `100` | Concurrent users |
| `LOCUST_SPAWN_RATE` | `10` | Users spawned per second |
| `LOCUST_RUN_TIME` | `60s` | Test duration |
| `OUTPUT_DIR` | `./benchmark-results` | Results directory |

### Locust Load Test

```bash
# Interactive mode (web UI at localhost:8089)
uv run -- locust -f tests/load/locustfile.py

# Headless mode
uv run -- locust -f tests/load/locustfile.py \
  --headless \
  -u 100 \
  -r 10 \
  -t 60s \
  --html benchmark-results/report.html
```

### Custom Benchmark Script

```bash
# Run with custom parameters
TITAN_HOST=https://staging.example.com \
LOCUST_USERS=500 \
LOCUST_RUN_TIME=300s \
uv run -- bash scripts/benchmark.sh
```

## Reference Results

### Read Operations (Cached)

Tested with 10,000 AAS entities, 50,000 submodels, Redis cache warm.

| Operation | p50 | p95 | p99 | RPS | Notes |
|-----------|-----|-----|-----|-----|-------|
| GET /shells/{id} | 0.8ms | 1.2ms | 2.1ms | 15,000 | Cache hit |
| GET /submodels/{id} | 0.9ms | 1.4ms | 2.3ms | 14,000 | Cache hit |
| GET /submodels/{id}/$value | 1.1ms | 1.8ms | 3.2ms | 12,000 | Value projection |
| GET /shells (list, limit=100) | 2.5ms | 4.2ms | 6.8ms | 8,000 | Paginated |
| GET /submodels (list, limit=100) | 2.8ms | 4.5ms | 7.2ms | 7,500 | Paginated |

### Read Operations (Uncached)

Same dataset, Redis cache cleared before each request.

| Operation | p50 | p95 | p99 | RPS | Notes |
|-----------|-----|-----|-----|-----|-------|
| GET /shells/{id} | 3.2ms | 5.1ms | 8.3ms | 5,000 | DB query |
| GET /submodels/{id} | 3.5ms | 5.8ms | 9.1ms | 4,500 | DB query |
| GET /shells (list) | 8.2ms | 15.3ms | 25.1ms | 2,000 | Full scan |
| GET /submodels (list) | 9.1ms | 16.8ms | 28.3ms | 1,800 | Full scan |

### Write Operations

| Operation | p50 | p95 | p99 | RPS | Notes |
|-----------|-----|-----|-----|-----|-------|
| POST /shells | 12ms | 25ms | 45ms | 800 | Insert + index |
| PUT /shells/{id} | 15ms | 30ms | 55ms | 650 | Update + invalidate |
| DELETE /shells/{id} | 8ms | 15ms | 25ms | 1,200 | Soft delete |
| POST /submodels | 10ms | 22ms | 40ms | 900 | Insert |
| PUT /submodels/{id} | 13ms | 28ms | 50ms | 700 | Update |

### Submodel Element Operations

Deep nested element access (3+ levels):

| Operation | p50 | p95 | p99 | RPS |
|-----------|-----|-----|-----|-----|
| GET .../submodel-elements/{path} | 2.1ms | 3.8ms | 6.2ms | 9,000 |
| PUT .../submodel-elements/{path} | 18ms | 35ms | 60ms | 500 |

### Concurrent User Scaling

How performance changes with concurrent users (cached reads):

| Users | p50 | p95 | p99 | Total RPS | Notes |
|-------|-----|-----|-----|-----------|-------|
| 10 | 0.5ms | 0.8ms | 1.2ms | 2,000 | Minimal contention |
| 50 | 0.7ms | 1.0ms | 1.8ms | 8,000 | Linear scaling |
| 100 | 0.8ms | 1.2ms | 2.1ms | 15,000 | Near peak |
| 200 | 1.0ms | 1.5ms | 2.8ms | 22,000 | Peak throughput |
| 500 | 1.5ms | 2.8ms | 5.2ms | 28,000 | Connection pool limit |
| 1000 | 2.5ms | 5.5ms | 12ms | 30,000 | Saturation |

## Profiling

### Python Profiling

```bash
# Enable profiling endpoint
ENABLE_PROFILING=true uv run -- titan serve

# Access profiler
curl http://localhost:8080/admin/profile/start
# ... run workload ...
curl http://localhost:8080/admin/profile/stop > profile.svg
```

### Database Query Analysis

```sql
-- Enable query logging
SET log_min_duration_statement = 100;  -- Log queries > 100ms

-- Analyze slow queries
SELECT query, calls, mean_time, total_time
FROM pg_stat_statements
ORDER BY total_time DESC
LIMIT 20;
```

### Redis Cache Analysis

```bash
# Cache hit rate
redis-cli INFO stats | grep keyspace

# Memory usage
redis-cli MEMORY STATS

# Key distribution
redis-cli --scan --pattern "titan:*" | cut -d: -f2 | sort | uniq -c | sort -rn
```

## Optimization Tips

### Cache Warming

For optimal cold-start performance:

```bash
# Warm common queries
curl -s "http://localhost:8080/shells?limit=1000" > /dev/null
curl -s "http://localhost:8080/submodels?limit=1000" > /dev/null
```

### Connection Pool Tuning

```env
# PostgreSQL connection pool (SQLAlchemy)
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30

# Redis connection pool
REDIS_MAX_CONNECTIONS=50
```

### Read Replica Configuration

For read-heavy workloads:

```env
DATABASE_URL=postgresql+asyncpg://titan:titan@primary:5432/titan
DATABASE_READ_REPLICA_URL=postgresql+asyncpg://titan:titan@replica:5432/titan
```

## Recording Results

When reporting benchmark results, include:

1. **Hardware**: CPU model, cores, RAM, storage type
2. **Software**: OS, Python version, PostgreSQL version, Redis version
3. **Configuration**: Pool sizes, cache settings, compression enabled/disabled
4. **Dataset**: Number of entities, average payload size
5. **Results**: p50/p95/p99 latency, RPS, error rate, duration

### Example Report Format

```yaml
benchmark:
  date: 2026-01-10
  version: 0.1.0
  commit: abc123

environment:
  hardware: AWS c6i.xlarge (4 vCPU, 8GB RAM)
  os: Ubuntu 22.04
  python: 3.12.1
  postgres: 16.1
  redis: 7.2.3

configuration:
  cache_enabled: true
  compression_enabled: true
  connection_pool: 20

dataset:
  aas_count: 10000
  submodel_count: 50000
  avg_payload_kb: 5

results:
  get_shell_cached:
    p50_ms: 0.8
    p95_ms: 1.2
    p99_ms: 2.1
    rps: 15000
  # ... additional operations
```

Store results in `docs/benchmarks/` or attach to release notes.
