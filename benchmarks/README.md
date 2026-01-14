# Titan-AAS vs BaSyx Python SDK Benchmark

This benchmark suite validates that Titan-AAS works correctly and compares its performance against BaSyx Python SDK.

## What This Proves

1. **Functional correctness**: Titan-AAS APIs work (create, read, update, delete)
2. **IDTA compliance**: Same API endpoints as BaSyx work correctly
3. **Performance comparison**: Fair head-to-head comparison
4. **Data integrity**: Created data can be retrieved correctly

## Quick Start

```bash
# 1. Generate test data
python benchmarks/data/generate_test_data.py

# 2. Start both servers
docker compose -f benchmarks/docker-compose.benchmark.yml up -d

# 3. Wait for servers to be ready (about 60 seconds for BaSyx)
sleep 60

# 4. Run functional tests
python benchmarks/functional_tests.py

# 5. Run performance comparison
python benchmarks/compare_basyx.py

# 6. View results
cat benchmarks/results/comparison_report.md
```

## Test Scenarios

| Scenario | Titan-AAS | BaSyx Python SDK |
|----------|-----------|------------------|
| **Storage** | PostgreSQL + Redis | LocalFileBackend |
| **Server** | Uvicorn (async) | WSGI |
| **Auth** | Disabled | Disabled |
| **Base Path** | `/shells`, `/submodels` | `/shells`, `/submodels` |

## Operations Tested

**Core CRUD (both support):**
- `POST /shells` - Create AAS
- `GET /shells/{id}` - Retrieve AAS
- `GET /shells` - List AAS
- `PUT /shells/{id}` - Update AAS
- `DELETE /shells/{id}` - Delete AAS
- `POST /submodels` - Create Submodel
- `GET /submodels/{id}` - Retrieve Submodel
- `GET /submodels` - List Submodels

## Files

| File | Purpose |
|------|---------|
| `docker-compose.benchmark.yml` | Side-by-side deployment |
| `functional_tests.py` | CRUD validation tests |
| `compare_basyx.py` | Main benchmark runner |
| `locustfile_comparison.py` | Locust load tests |
| `data/generate_test_data.py` | Test data generator |
| `data/benchmark_aas.json` | Generated AAS test data |
| `data/benchmark_submodels.json` | Generated Submodel test data |
| `results/` | Benchmark results output |

## Functional Tests

Validate that both servers correctly implement CRUD operations:

```bash
# Test both servers
python benchmarks/functional_tests.py

# Test Titan only
python benchmarks/functional_tests.py --target titan

# Test BaSyx only
python benchmarks/functional_tests.py --target basyx

# Custom URLs
python benchmarks/functional_tests.py \
    --titan-url http://my-titan:8080 \
    --basyx-url http://my-basyx:8081
```

## Performance Benchmarks

### Using compare_basyx.py

```bash
# Full benchmark (load data + benchmark + report)
python benchmarks/compare_basyx.py

# Load test data only
python benchmarks/compare_basyx.py --load-data

# Run benchmarks only (assumes data is loaded)
python benchmarks/compare_basyx.py --benchmark

# Generate report from existing results
python benchmarks/compare_basyx.py --report

# Custom iterations
python benchmarks/compare_basyx.py --iterations 500
```

### Using Locust (Advanced)

For detailed load testing with real-time metrics:

```bash
# Test Titan-AAS with web UI
locust -f benchmarks/locustfile_comparison.py --host http://localhost:8080

# Test BaSyx Python SDK with web UI
locust -f benchmarks/locustfile_comparison.py --host http://localhost:8081

# Headless comparison
locust -f benchmarks/locustfile_comparison.py --host http://localhost:8080 \
    --headless --users 50 --spawn-rate 10 --run-time 60s \
    --html benchmarks/results/titan_report.html

locust -f benchmarks/locustfile_comparison.py --host http://localhost:8081 \
    --headless --users 50 --spawn-rate 10 --run-time 60s \
    --html benchmarks/results/basyx_report.html
```

## Success Criteria

| Metric | Target |
|--------|--------|
| Functional tests pass | 100% for both |
| CRUD operations work | All 8 core operations |
| Error rate under load | < 1% |
| Data integrity | Created = Retrieved |

## Troubleshooting

### Servers not starting

```bash
# Check container status
docker compose -f benchmarks/docker-compose.benchmark.yml ps

# View logs
docker compose -f benchmarks/docker-compose.benchmark.yml logs titan-aas
docker compose -f benchmarks/docker-compose.benchmark.yml logs basyx-aas-server
```

### BaSyx takes long to start

BaSyx Python SDK installs dependencies on first run. Wait 60+ seconds.

### Connection refused

Ensure servers are healthy before running tests:

```bash
# Check Titan
curl http://localhost:8080/shells

# Check BaSyx
curl http://localhost:8081/shells
```

### Clean up

```bash
# Stop and remove containers
docker compose -f benchmarks/docker-compose.benchmark.yml down -v
```
