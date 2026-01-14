# Production Gates Checklist (Draft)

This document provides measurable acceptance criteria for future Titan-AAS releases.
**Titan-AAS is currently a prototype/research platform and is not production-ready.**
This is a planning checklist, not proof of production readiness. Each gate should be
verified before a version can be considered production-ready.

---

## Gate 1: CI Health (BLOCKING)

All CI checks must pass consistently before release.

| Criterion | Threshold | Evidence |
|-----------|-----------|----------|
| Main branch CI | Green for 7+ consecutive days | GitHub Actions history |
| Unit tests | All passing | `tests/unit/` - JUnit XML artifact |
| Integration tests | All passing | `tests/integration/` - JUnit XML artifact |
| Contract tests | All passing | `tests/contract/` - JUnit XML artifact |
| Code coverage | >= 40% | Codecov report |
| Type checking | Zero errors | mypy output |
| Linting | Zero errors | ruff check output |

**Verification:**
```bash
# Run all CI checks locally
uv run -- ruff check src/ tests/
uv run -- ruff format --check src/ tests/
uv run -- mypy src/titan
uv run -- pytest tests/unit tests/integration tests/contract -v
```

---

## Gate 2: Specification Conformance (BLOCKING)

Part 2 API endpoints must be validated against IDTA specifications.

| Criterion | Threshold | Evidence |
|-----------|-----------|----------|
| AAS Repository (SSP-001) | 100% of CRUD endpoints | `conformance-report.json` |
| Submodel Repository (SSP-001) | 100% of CRUD endpoints | `conformance-report.json` |
| Registry (SSP-001) | 100% of descriptor endpoints | `conformance-report.json` |
| Discovery (SSP-002) | Lookup endpoints functional | `conformance-report.json` |
| Conformance report | Attached to release | GitHub Release artifacts |
| Interop testing | Tested with AASX Package Explorer | Manual verification |

**Verification:**
```bash
# Generate conformance report
python scripts/generate_conformance_report.py \
  --input test-results/contract.xml \
  --output conformance-report.json \
  --version $(git describe --tags)
```

---

## Gate 3: Security (BLOCKING)

Security controls must be implemented and verified.

| Criterion | Threshold | Evidence |
|-----------|-----------|----------|
| OIDC integration | Tested end-to-end | `tests/integration/test_security_flows.py` |
| RBAC enforcement | reader/writer/admin roles verified | `tests/unit/security/test_deps_abac.py` |
| Rate limiting | Functional with Redis | `tests/integration/test_rate_limit.py` |
| Security scan | Zero CRITICAL/HIGH vulnerabilities | Trivy SARIF report |
| Dependency audit | No unmitigated CVEs | pip-audit output |
| SBOM | CycloneDX attached to release | GitHub Release artifacts |
| Security headers | All headers present | `tests/unit/api/test_security_headers.py` |

**Verification:**
```bash
# Run security scans
uv run -- bandit -r src/titan -ll
uv run -- pip-audit --local --skip-editable

# Run security-focused tests
uv run -- pytest tests/unit/security tests/integration/test_security_flows.py -v
```

---

## Gate 4: Performance (INFORMATIONAL)

Performance benchmarks with documented methodology.

| Metric | Target | Measured |
|--------|--------|----------|
| p50 latency (GET /shells/{id}) | < 50ms | See benchmark-results.json |
| p95 latency (GET /shells/{id}) | < 100ms | See benchmark-results.json |
| p99 latency (GET /shells/{id}) | < 250ms | See benchmark-results.json |
| Error rate | < 1% | See benchmark-results.json |
| Requests/second | > 300 RPS | See benchmark-results.json |

**Test Environment:**
- Hardware: GitHub Actions runner (2 vCPU, 8GB RAM)
- Database: PostgreSQL 16-alpine
- Cache: Redis 7-alpine
- Dataset: 100 AAS, 100 Submodels
- Load: 100 concurrent users, 60 second duration

**Verification:**
```bash
# Run load test
uv run -- locust -f tests/load/locustfile.py \
  --host http://localhost:8080 \
  --headless -u 100 -r 20 -t 60s \
  --csv load-test-results
```

---

## Gate 5: Operations (RECOMMENDED)

Operational readiness for production deployment.

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Health endpoints | `/health/live`, `/health/ready` functional | API response |
| Prometheus metrics | `/metrics` endpoint exposed | Scrape config tested |
| Structured logging | JSON logs with correlation IDs | Log output |
| Deployment runbook | Documented | `docs/deployment-runbook.md` |
| HA guidance | Documented | `docs/ha-guidance.md` |
| Capacity planning | Documented | `docs/capacity-planning.md` |
| Alert rules | Prometheus rules defined | `deployment/prometheus/alerts/` |
| Backup procedure | Documented | `docs/runbook-quickref.md` |

**Verification:**
```bash
# Test health endpoints
curl -f http://localhost:8080/health/live
curl -f http://localhost:8080/health/ready
curl http://localhost:8080/metrics | head -20
```

---

## Feature Implementation Status

Features are classified as:
- **Implemented**: Fully functional with test coverage
- **Scaffolded**: Code structure exists, not fully functional
- **Planned**: Roadmap item, not yet started

| Feature | Status | Evidence |
|---------|--------|----------|
| OIDC Authentication | Implemented | `src/titan/security/oidc.py`, `tests/integration/test_security_flows.py` |
| RBAC (reader/writer/admin) | Implemented | `src/titan/security/rbac.py`, `tests/unit/security/test_deps_abac.py` |
| ABAC (tenant isolation) | Implemented | `src/titan/security/abac.py`, `tests/unit/security/test_abac.py` |
| Rate Limiting | Implemented | `src/titan/api/middleware/rate_limit.py`, `tests/integration/test_rate_limit.py` |
| Redis Cache Fast Path | Implemented | `src/titan/cache/redis.py`, `docs/benchmarks.md` |
| AAS Repository CRUD | Implemented | `src/titan/api/routers/aas_repository.py` |
| Submodel Repository CRUD | Implemented | `src/titan/api/routers/submodel_repository.py` |
| Registry CRUD | Implemented | `src/titan/api/routers/registry.py` |
| Discovery Lookup | Implemented | `src/titan/api/routers/discovery.py` |
| ConceptDescription CRUD | Implemented | `src/titan/api/routers/concept_description_repository.py` |
| WebSocket Events | Implemented | `src/titan/events/` |
| AASX Import/Export | Scaffolded | `src/titan/aasx/` - basic structure only |
| Federation | Scaffolded | `src/titan/federation/` - interface only |
| Catena-X EDC Connector | Scaffolded | `src/titan/connectors/edc/` - interface only |
| Edge Offline-First | Planned | Roadmap for v0.3 |
| OPC-UA Connector | Scaffolded | `src/titan/connectors/opcua/` - interface only |
| Plugin System | Planned | Roadmap for v0.4 |

---

## Release Checklist

Before tagging a release:

- [ ] All Gate 1 (CI Health) criteria pass
- [ ] All Gate 2 (Conformance) criteria pass
- [ ] All Gate 3 (Security) criteria pass
- [ ] Gate 4 (Performance) benchmark attached
- [ ] Gate 5 (Operations) documentation reviewed
- [ ] CHANGELOG.md updated
- [ ] Version bumped in pyproject.toml
- [ ] Release notes drafted
- [ ] Artifacts attached: conformance-report.json, benchmark-results.json, SBOM

---

## Known Limitations

1. **Anonymous mode grants admin**: Only when `ALLOW_ANONYMOUS_ADMIN=true` and OIDC is unset.
   Never use in production.

2. **JWKS cache fallback**: If OIDC provider is unavailable, cached keys are used. Stale keys may cause auth failures.

3. **Admin bypasses ABAC**: Users with admin role bypass tenant isolation checks.

4. **Coverage threshold**: Currently set to 40% to allow incremental improvement. Target is 80%.

5. **Load test environment**: GitHub Actions runners have variable performance. Results are indicative, not absolute.
