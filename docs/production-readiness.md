# Production Readiness Checklist

This document defines the production readiness gates for Titan-AAS. Each section includes acceptance criteria that should be verified before production deployment.

## Overview

Titan-AAS is designed for industrial AAS v3.1 workloads. Production readiness requires validation across five categories:

| Category | Status | CI Job |
|----------|--------|--------|
| Standards Compliance | Required | `test-contract` |
| Security | Required | `test-integration`, `security` |
| Operations | Required | Manual review |
| Performance | Required | `load-test` |
| Release | Required | `release` |

---

## A. Standards and Interoperability Gates

### A.1 Specification Conformance

| Requirement | Status | Evidence |
|-------------|--------|----------|
| IDTA-01002 Part 2 API v3.1.1 | Partial | `conformance-report.json` |
| IDTA-01003-a IEC 61360 | Partial | See `docs/conformance-matrix.md` |
| IDTA-01004 Security | Implemented | See `docs/security.md` |

**CI Gate:** Contract tests must pass with SSP test case IDs linked.

```bash
# Verify conformance
uv run -- pytest tests/contract -v --junitxml=test-results/contract.xml
```

### A.2 SSP Profile Coverage

| Profile | Endpoints | Status | Test Coverage |
|---------|-----------|--------|---------------|
| AAS Repository SSP-001 | Full CRUD | Implemented | `tests/contract/test_openapi.py` |
| AAS Repository SSP-002 | Read-only | Implemented | `tests/contract/test_openapi.py` |
| Submodel Repository SSP-001 | Full CRUD | Implemented | `tests/contract/test_openapi.py` |
| Submodel Repository SSP-002 | Read-only | Implemented | `tests/contract/test_openapi.py` |
| Registry SSP-001/002 | Full CRUD | Implemented | `tests/integration/test_registry.py` |
| Discovery SSP-001 | Asset lookup | Partial | Planned |

### A.3 Error Response Conformance

All error responses follow IDTA-compliant format:

```json
{
  "messages": [
    {
      "code": "NotFound",
      "messageType": "Error",
      "text": "AAS with identifier 'xyz' not found",
      "timestamp": "2026-01-10T12:34:56Z"
    }
  ]
}
```

**Verified HTTP Status Codes:**
- 200 OK, 201 Created, 204 No Content
- 400 Bad Request, 404 Not Found, 409 Conflict
- 412 Precondition Failed (ETag validation)
- 429 Too Many Requests (Rate limiting)

### A.4 Interoperability

| System | Version | Status | Evidence |
|--------|---------|--------|----------|
| AASX Package Explorer | 2024.x | Compatible | Manual testing |
| BaSyx AAS Server | v2 | Compatible | `tests/compatibility/` |
| Eclipse BaSyx | 2.0.x | Compatible | DTR sync tested |
| Catena-X EDC | 0.7.x | Compatible | Asset registration |

---

## B. Security Gates

### B.1 Authentication

| Mode | Configuration | Status |
|------|---------------|--------|
| Anonymous (dev) | `OIDC_ISSUER` unset | Implemented |
| OIDC | `OIDC_ISSUER` set | Implemented |

**Security Warning:** Anonymous mode grants admin privileges. Never use in production.

See `docs/security-modes.md` for full security configuration matrix.

### B.2 Authorization

| Feature | Configuration | Status |
|---------|---------------|--------|
| RBAC | Always enabled | Implemented |
| ABAC | `ENABLE_ABAC=true` | Implemented |
| Default deny | `ABAC_DEFAULT_DENY=true` | Implemented |

**Roles:** READER, WRITER, ADMIN

**Permissions:** Fine-grained per resource type (AAS, SUBMODEL, DESCRIPTOR, CONCEPT_DESCRIPTION)

### B.3 Rate Limiting

| Setting | Default | Configuration |
|---------|---------|---------------|
| Enabled | Yes | `ENABLE_RATE_LIMITING` |
| Requests/window | 100 | `RATE_LIMIT_REQUESTS` |
| Window (seconds) | 60 | `RATE_LIMIT_WINDOW` |

**Bypass paths:** `/health/*`, `/metrics`

### B.4 Security Headers

| Header | Default | Configuration |
|--------|---------|---------------|
| X-Content-Type-Options | nosniff | Always |
| X-Frame-Options | DENY | Always |
| Strict-Transport-Security | Enabled | `ENABLE_HSTS=true` |
| Content-Security-Policy | Optional | `CSP_POLICY` |

### B.5 Audit Logging

All security events are logged to a dedicated audit log:
- Authentication events (login, logout, failure)
- Authorization decisions (granted, denied)
- Resource mutations (create, update, delete)

See `src/titan/security/audit.py` for implementation.

---

## C. Operations Gates

### C.1 Health Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health/live` | Liveness probe | `{"status": "ok"}` |
| `/health/ready` | Readiness probe | Checks DB + Redis |

### C.2 Observability

| Feature | Endpoint | Status |
|---------|----------|--------|
| Prometheus metrics | `/metrics` | Implemented |
| OpenTelemetry tracing | OTLP export | Implemented |
| Structured JSON logging | stderr | Implemented |
| Correlation IDs | X-Request-ID, X-Correlation-ID | Implemented |

### C.3 High Availability

See `docs/ha-guidance.md` for:
- Active-Active architecture
- Redis leader election (ADR-0004)
- PostgreSQL read replicas
- Kubernetes HPA configuration

### C.4 Backup and Recovery

See `docs/deployment-runbook.md` for:
- PostgreSQL backup procedures
- Redis persistence configuration
- Disaster recovery playbook

---

## D. Performance Gates

### D.1 Performance Targets

| Metric | Target | Evidence |
|--------|--------|----------|
| p50 latency (cached) | < 10ms | `load-test-report.html` |
| p99 latency (cached) | < 100ms | `load-test-report.html` |
| Error rate | < 0.1% | `load-test-report.html` |
| Throughput | 15,000+ RPS | With optimized infrastructure |

### D.2 CI Performance Gate

```yaml
# .github/workflows/ci.yml
load-test:
  env:
    LOAD_TEST_P99_MS: "200"
    LOAD_TEST_MAX_ERROR_RATE: "0.01"
```

### D.3 Benchmark Artifacts

Each release includes:
- `benchmark-results.json` - Structured performance data
- `load-test-report.html` - Detailed Locust report

See `docs/benchmarks.md` for methodology and reference results.

---

## E. Release Gates

### E.1 Version Policy

- Semantic versioning (SemVer)
- Pre-1.0 releases may have breaking changes
- Post-1.0 follows strict compatibility

### E.2 Release Artifacts

| Artifact | Location | CI Job |
|----------|----------|--------|
| Docker image | `ghcr.io/hadijannat/titan-aas` | `release` |
| SBOM (CycloneDX) | GitHub release | `build` |
| Benchmark results | GitHub release | `load-test` |
| Conformance report | GitHub release | `test-contract` |

### E.3 Release Notes Requirements

Each release must include:
- Summary of changes
- SSP profile status (what's supported)
- Known limitations
- Breaking changes (if any)
- Security advisories (if any)

See `docs/release-process.md` for procedures.

---

## Pre-Deployment Checklist

Before deploying to production:

- [ ] All CI jobs pass (lint, test, security, build)
- [ ] Contract tests pass for claimed SSP profiles
- [ ] Security mode configured (OIDC enabled, rate limiting enabled)
- [ ] HSTS enabled (`ENABLE_HSTS=true`)
- [ ] Audit logging destination configured
- [ ] Alerting rules deployed (Prometheus/Grafana)
- [ ] Backup procedures tested
- [ ] Load test passes performance thresholds
- [ ] Release notes document known limitations

---

## Known Limitations

### Current Version (v0.1.x)

| Limitation | Impact | Workaround |
|------------|--------|------------|
| SSP-003 Bulk operations | Not implemented | Use individual CRUD |
| SSP-004 Advanced queries | Not implemented | Use basic filters |
| Template-only profiles | Not implemented | Full submodels only |
| External vocab validation | Not implemented | No code list enforcement |

### Security Considerations

1. **Anonymous mode** grants admin access - never use in production
2. **Admin users bypass ABAC** evaluation entirely
3. **JWKS cache fallback** uses potentially stale keys during network failures

---

## Compliance Summary

Titan-AAS v0.1.x is suitable for:
- POCs and pilot deployments
- Non-regulated industrial workloads
- Development and testing environments

For regulated or safety-critical deployments:
- Wait for v1.0 with full SSP coverage
- Conduct independent security assessment
- Implement additional hardening per your requirements
