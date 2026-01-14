# Titan-AAS Load Testing

This directory contains load testing scenarios using [Locust](https://locust.io/).

## Prerequisites

1. Start the full stack:
   ```bash
   cd deployment
   docker compose up -d
   ```

2. Wait for services to be healthy:
   ```bash
   docker compose ps
   ```

## Running Load Tests

### Authentication

Titan-AAS requires authentication by default. For load tests, use one of:

1. **Anonymous admin (local/dev only):**
   ```bash
   export ALLOW_ANONYMOUS_ADMIN=true
   ```
   Start Titan-AAS with this env var so Locust can access endpoints without a token.

2. **Bearer token (recommended for secured environments):**
   ```bash
   export LOAD_TEST_TOKEN="your-bearer-token"
   ```
   Locust will attach the token as `Authorization: Bearer ...` on every request.

### Web UI Mode (Interactive)

```bash
# Start Locust with web interface
uv run -- locust -f tests/load/locustfile.py --host=http://localhost:8080

# Open http://localhost:8089 in your browser
```

### Headless Mode (CI/CD)

```bash
# Run for 60 seconds with 100 concurrent users, ramping up 10 users/second
uv run -- locust -f tests/load/locustfile.py \
    --host=http://localhost:8080 \
    --headless \
    -u 100 \
    -r 10 \
    -t 60s \
    --csv=results/load-test
```

## Test Scenarios

### TitanAASUser (Mixed Workload)
- **Weight**: Default
- **Wait Time**: 100-500ms between requests
- Simulates typical API usage:
  - 70% reads (GET /shells, GET /submodels)
  - 20% updates (PUT endpoints)
  - 10% creates (POST endpoints)

### HighThroughputReader (Cache Benchmark)
- **Wait Time**: 10-50ms
- Tests cache performance with repeated reads on fixed IDs
- Use to measure cache hit ratio

### BurstWriter (Write Stress)
- **Wait Time**: 10-20ms
- High-frequency write operations
- Tests event bus and micro-batching performance

## Performance Targets

| Metric | Target | Critical |
|--------|--------|----------|
| p50 Latency (cached read) | <10ms | <50ms |
| p99 Latency (cached read) | <50ms | <200ms |
| p50 Latency (DB read) | <20ms | <100ms |
| p99 Latency (DB read) | <100ms | <500ms |
| Error Rate | <0.1% | <1% |
| Cache Hit Rate | >95% | >80% |
| Throughput (reads) | >1000 RPS | >500 RPS |

## Analyzing Results

### CSV Output Files
- `results/load-test_stats.csv` - Summary statistics
- `results/load-test_stats_history.csv` - Time-series data
- `results/load-test_failures.csv` - Failed requests
- `results/load-test_exceptions.csv` - Exceptions

### Key Metrics to Monitor

1. **Request Rate**: Should scale linearly with users
2. **Response Time Distribution**: Watch for tail latency (p95, p99)
3. **Error Rate**: Should stay near zero
4. **Cache Hit Rate**: Monitor via Prometheus/Grafana

## Integration with CI/CD

Add to GitHub Actions:

```yaml
- name: Run Load Tests
  run: |
    uv run -- locust -f tests/load/locustfile.py \
        --host=${{ secrets.STAGING_URL }} \
        --headless \
        -u 50 -r 5 -t 30s \
        --csv=load-results

- name: Check Results
  run: |
    # Fail if error rate > 1%
    python -c "
    import csv
    with open('load-results_stats.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Name'] == 'Aggregated':
                if float(row['Failure Count']) / float(row['Request Count']) > 0.01:
                    exit(1)
    "
```

## Troubleshooting

### High Latency
1. Check database connection pool utilization
2. Verify Redis is properly caching
3. Check for slow queries with `EXPLAIN ANALYZE`

### High Error Rate
1. Check application logs: `docker compose logs titan`
2. Verify database/Redis connectivity
3. Check for rate limiting or timeouts

### Memory Issues
1. Monitor container memory: `docker stats`
2. Check for memory leaks in long-running tests
3. Tune connection pool sizes
