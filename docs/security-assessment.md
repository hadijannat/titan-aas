# Security Assessment

This document provides security evidence to support potential production deployments.
It covers authentication, authorization, security controls, and known limitations.

---

## Authentication

### OIDC/OAuth2 Integration

| Component | Implementation | Evidence |
|-----------|----------------|----------|
| Token validation | JWT with JWKS | `src/titan/security/oidc.py` |
| JWKS caching | Configurable TTL | `TokenValidator` class |
| Issuer validation | Required | `OIDC_ISSUER` environment variable |
| Audience validation | Optional | `OIDC_AUDIENCE` environment variable |
| Role extraction | JWT claims | `OIDC_ROLE_CLAIM` (default: `roles`) |

**Configuration:**
```env
OIDC_ISSUER=https://auth.example.com/realms/titan
OIDC_AUDIENCE=titan-aas
OIDC_ROLE_CLAIM=realm_access.roles
OIDC_JWKS_CACHE_TTL=3600
```

**Test Coverage:**
- `tests/integration/test_security_flows.py` - End-to-end OIDC tests
- `tests/unit/security/test_oidc.py` - Token validation unit tests

---

## Authorization

### RBAC (Role-Based Access Control)

Three predefined roles with hierarchical permissions:

| Role | Read | Write | Delete | Admin |
|------|------|-------|--------|-------|
| `reader` | Yes | No | No | No |
| `writer` | Yes | Yes | Yes | No |
| `admin` | Yes | Yes | Yes | Yes |

**Implementation:** `src/titan/security/rbac.py`

**Test Coverage:**
- `tests/unit/security/test_deps_abac.py` - Role enforcement tests

### ABAC (Attribute-Based Access Control)

Optional tenant isolation for multi-tenant deployments:

| Feature | Description |
|---------|-------------|
| Tenant claim | Extracted from JWT (`tenant_id` claim) |
| Resource filtering | Automatic query filtering by tenant |
| Cross-tenant protection | Requests cannot access other tenants' data |

**Configuration:**
```env
ENABLE_ABAC=true
ABAC_TENANT_CLAIM=tenant_id
```

**Implementation:** `src/titan/security/abac.py`

**Test Coverage:**
- `tests/unit/security/test_abac.py` - Tenant isolation tests

---

## Security Controls

### Rate Limiting

Redis-backed rate limiting to prevent abuse:

| Setting | Default | Description |
|---------|---------|-------------|
| `RATE_LIMIT_REQUESTS` | 100 | Requests per window |
| `RATE_LIMIT_WINDOW` | 60 | Window in seconds |
| `RATE_LIMIT_KEY` | IP address | Rate limit key strategy |

**Implementation:** `src/titan/api/middleware/rate_limit.py`

**Test Coverage:**
- `tests/integration/test_rate_limit.py` - Rate limiting integration tests

### Security Headers

All responses include security headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `X-XSS-Protection` | `1; mode=block` | XSS protection |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Force HTTPS |
| `Content-Security-Policy` | `default-src 'self'` | Content restrictions |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer control |

**Implementation:** `src/titan/api/middleware/security_headers.py`

**Test Coverage:**
- `tests/unit/api/test_security_headers.py` - Header verification tests

### Input Validation

All API inputs validated with Pydantic v2 strict mode:

| Feature | Description |
|---------|-------------|
| Type coercion | Disabled (strict mode) |
| Extra fields | Rejected |
| Max string length | Enforced per field |
| URL validation | Format and scheme validation |

**Implementation:** `src/titan/core/model/` - Pydantic models

---

## Dependency Security

### Software Bill of Materials (SBOM)

CycloneDX format SBOM generated on each release:

```bash
# Generate SBOM locally
uv run -- cyclonedx-py requirements -o sbom.json
```

**CI Integration:** `.github/workflows/ci.yml` - `anchore/sbom-action`

### Vulnerability Scanning

#### Container Scanning

Trivy scans container images for vulnerabilities:

```bash
# Scan local image
trivy image titan-aas:latest --severity CRITICAL,HIGH
```

**CI Integration:** `.github/workflows/ci.yml` - `aquasecurity/trivy-action`

#### Dependency Auditing

pip-audit checks Python dependencies:

```bash
# Audit dependencies
uv run -- pip-audit --local --skip-editable
```

**CI Integration:** `.github/workflows/ci.yml` - Security job

#### Static Analysis

Bandit scans for common security issues:

```bash
# Run bandit
uv run -- bandit -r src/titan -ll
```

**CI Integration:** `.github/workflows/ci.yml` - Security job

### Known Vulnerabilities

Mitigated CVEs documented in `docs/security-advisories.md`:

| CVE | Package | Status | Justification |
|-----|---------|--------|---------------|
| PYSEC-2024-230 | (example) | Ignored | Not exploitable in our context |
| PYSEC-2024-225 | (example) | Ignored | Fixed in runtime configuration |
| CVE-2024-23342 | (example) | Ignored | Mitigated by input validation |

---

## Audit Logging

All security-relevant events logged with structured JSON:

| Event Type | Fields Logged |
|------------|---------------|
| Authentication | user_id, issuer, success/failure, timestamp |
| Authorization | user_id, resource, action, permitted, timestamp |
| Rate limiting | client_ip, endpoint, requests, window, timestamp |
| Resource access | user_id, resource_type, resource_id, action, timestamp |

**Configuration:**
```env
LOG_LEVEL=INFO
LOG_FORMAT=json
ENABLE_AUDIT_LOGGING=true
```

**Implementation:** `src/titan/observability/logging.py`

---

## Secure Defaults

### Development Mode (TITAN_ENV=development)

| Setting | Default | Warning |
|---------|---------|---------|
| Authentication | Disabled | Anonymous = admin access |
| HTTPS | Not enforced | Plain HTTP allowed |
| Debug endpoints | Enabled | `/debug/*` exposed |
| Profiling | Enabled | Performance data exposed |

### Production Mode (TITAN_ENV=production)

| Setting | Default | Notes |
|---------|---------|-------|
| Authentication | Required | OIDC_ISSUER must be set |
| HTTPS | Enforced | HSTS enabled |
| Debug endpoints | Disabled | 404 response |
| Profiling | Disabled | Not accessible |

---

## Network Security

### TLS Configuration

For production deployments, TLS should be terminated at:
- Load balancer (recommended)
- Ingress controller (Kubernetes)
- Reverse proxy (nginx, Traefik)

Titan-AAS expects TLS termination upstream and trusts `X-Forwarded-*` headers.

**Configuration:**
```env
TRUSTED_HOSTS=titan.example.com,api.example.com
FORWARDED_ALLOW_IPS=10.0.0.0/8,172.16.0.0/12
```

### Database Security

| Control | Implementation |
|---------|----------------|
| Connection encryption | `sslmode=require` in DATABASE_URL |
| Credential management | Environment variables or secrets manager |
| Connection pooling | SQLAlchemy async pool with limits |

### Redis Security

| Control | Implementation |
|---------|----------------|
| Authentication | Password in REDIS_URL |
| TLS | `rediss://` scheme for TLS |
| Access control | Redis ACL (Redis 6+) |

---

## Known Limitations

### 1. Anonymous Mode Grants Admin

**Risk:** Critical
**Context:** Development mode only
**Mitigation:** Always set `TITAN_ENV=production` and configure OIDC

In development mode without OIDC configuration, all requests are treated as
authenticated with admin privileges. This is convenient for development but
must never be used in production.

### 2. JWKS Cache Fallback

**Risk:** Medium
**Context:** OIDC provider unavailability
**Mitigation:** Monitor OIDC connectivity, configure alerts

If the OIDC provider is unavailable, cached JWKS keys are used. During
extended outages, cached keys may become stale, causing authentication
failures for new tokens.

### 3. Admin Bypasses ABAC

**Risk:** Low
**Context:** Multi-tenant deployments
**Mitigation:** Limit admin role assignment

Users with the `admin` role bypass ABAC tenant isolation checks. This is
by design for administrative operations but requires careful role assignment.

### 4. Rate Limit Bypass with Distributed Clients

**Risk:** Low
**Context:** DDoS scenarios
**Mitigation:** Use external WAF/DDoS protection

Rate limiting is per-IP. Distributed attacks from many IPs may bypass
client-side rate limits. Use external protection (Cloudflare, AWS WAF)
for production deployments.

---

## Security Contacts

For security vulnerabilities, see [SECURITY.md](../SECURITY.md).

**Response SLA:**
- Critical: 24 hours acknowledgment, 7 days resolution
- High: 48 hours acknowledgment, 14 days resolution
- Medium/Low: 7 days acknowledgment, 30 days resolution
