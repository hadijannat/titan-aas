# Security Modes Configuration

This document describes the security configuration matrix for Titan-AAS, covering all authentication, authorization, and access control modes.

---

## Security Stack Overview

Titan-AAS implements a layered security stack:

```
┌─────────────────────────────────────────────┐
│              Rate Limiting                   │
│          (Redis sliding window)              │
├─────────────────────────────────────────────┤
│           Authentication (OIDC)              │
│         (JWT validation, JWKS)               │
├─────────────────────────────────────────────┤
│              RBAC (Roles)                    │
│      (reader, writer, admin roles)           │
├─────────────────────────────────────────────┤
│              ABAC (Policies)                 │
│    (tenant isolation, IP allowlist, etc.)    │
├─────────────────────────────────────────────┤
│             Audit Logging                    │
│    (security events, mutations, access)      │
└─────────────────────────────────────────────┘
```

---

## Configuration Matrix

| Mode | OIDC_ISSUER | ENABLE_ABAC | ENABLE_RATE_LIMITING | Risk Level |
|------|-------------|-------------|----------------------|------------|
| Development | unset + `ALLOW_ANONYMOUS_ADMIN=true` | `false` | `false` | **HIGH** |
| OIDC Only | set | `false` | `true` | MEDIUM |
| OIDC + RBAC | set | `false` | `true` | LOW |
| OIDC + ABAC | set | `true` | `true` | **LOWEST** |

---

## Mode Details

### Development Mode (Anonymous - Explicit Opt-In)

**Configuration:**
```bash
# No authentication configured
# OIDC_ISSUER is unset
ALLOW_ANONYMOUS_ADMIN=true
ENABLE_RATE_LIMITING=false
ENABLE_ABAC=false
```

**Behavior:**
- All requests are processed without authentication
- An anonymous user with `admin` role is created for every request
- All permissions are granted by default
- Rate limiting is disabled

**Security Warning:**
```
┌────────────────────────────────────────────────────────────────┐
│ ⚠️  NEVER USE DEVELOPMENT MODE IN PRODUCTION                   │
│                                                                 │
│ When OIDC_ISSUER is not set and ALLOW_ANONYMOUS_ADMIN is true, │
│ unauthenticated requests receive full admin privileges. This   │
│ grants anonymous users:                                        │
│                                                                 │
│ - Full CRUD on all AAS                                         │
│ - Full CRUD on all Submodels                                   │
│ - Full CRUD on all Concept Descriptions                        │
│ - Registry modification access                                 │
│ - Admin API access                                             │
└────────────────────────────────────────────────────────────────┘
```

**Code Reference:** `src/titan/security/deps.py`
```python
# If OIDC not configured, allow anonymous admin only when explicitly enabled
if validator is None and settings.allow_anonymous_admin:
    anon = User(sub="anonymous", name="Anonymous", roles=["admin"])
    return anon
```

---

### Public Endpoint Overrides (Explicit Opt-In)

By default, sensitive endpoints require authentication. You can explicitly expose
them for internal networks or local development:

```bash
PUBLIC_HEALTH_ENDPOINTS=true
PUBLIC_METRICS_ENDPOINT=true
PUBLIC_DESCRIPTION_ENDPOINTS=true
PUBLIC_JOBS_ENDPOINTS=true
PUBLIC_DEBUG_ENDPOINTS=true
```

---

### OIDC Only Mode

**Configuration:**
```bash
OIDC_ISSUER=https://your-idp.com
OIDC_AUDIENCE=titan-aas
OIDC_CLIENT_ID=titan-client
OIDC_ROLES_CLAIM=roles
OIDC_JWKS_CACHE_SECONDS=3600

ENABLE_RATE_LIMITING=true
ENABLE_ABAC=false
```

**Behavior:**
- JWT tokens are validated against OIDC provider
- JWKS (JSON Web Key Set) is cached for performance
- User roles are extracted from the `roles` claim
- RBAC is implicitly enabled (always on)
- Fine-grained ABAC policies are not evaluated

**JWKS Cache Fallback Warning:**
```
┌────────────────────────────────────────────────────────────────┐
│ ⚠️  JWKS Cache Fallback Behavior                               │
│                                                                 │
│ During OIDC provider outages, Titan-AAS uses stale cached keys.│
│ This allows service continuity but may accept tokens that were │
│ revoked or signed with rotated keys.                           │
│                                                                 │
│ Mitigations:                                                   │
│ - Set appropriate OIDC_JWKS_CACHE_SECONDS (default: 1 hour)    │
│ - Monitor OIDC connectivity via /health/ready                  │
│ - Use short-lived tokens (< 15 minutes recommended)            │
└────────────────────────────────────────────────────────────────┘
```

---

### OIDC + RBAC Mode

**Configuration:**
```bash
OIDC_ISSUER=https://your-idp.com
OIDC_AUDIENCE=titan-aas
OIDC_CLIENT_ID=titan-client
OIDC_ROLES_CLAIM=roles

ENABLE_RATE_LIMITING=true
ENABLE_ABAC=false
```

**RBAC Roles:**

| Role | OIDC Claim | Permissions |
|------|------------|-------------|
| `reader` | `reader` or `titan:read` | Read all resources |
| `writer` | `writer` or `titan:write` | Read + Create + Update |
| `admin` | `admin` or `titan:admin` | Full access |

**Permissions Matrix:**

| Permission | Reader | Writer | Admin |
|------------|--------|--------|-------|
| `read:aas` | ✅ | ✅ | ✅ |
| `read:submodel` | ✅ | ✅ | ✅ |
| `read:descriptor` | ✅ | ✅ | ✅ |
| `read:concept_description` | ✅ | ✅ | ✅ |
| `create:aas` | ❌ | ✅ | ✅ |
| `update:aas` | ❌ | ✅ | ✅ |
| `delete:aas` | ❌ | ❌ | ✅ |
| `create:submodel` | ❌ | ✅ | ✅ |
| `update:submodel` | ❌ | ✅ | ✅ |
| `delete:submodel` | ❌ | ❌ | ✅ |
| `create:descriptor` | ❌ | ✅ | ✅ |
| `update:descriptor` | ❌ | ✅ | ✅ |
| `delete:descriptor` | ❌ | ❌ | ✅ |
| `create:concept_description` | ❌ | ✅ | ✅ |
| `update:concept_description` | ❌ | ✅ | ✅ |
| `delete:concept_description` | ❌ | ❌ | ✅ |
| `admin:*` | ❌ | ❌ | ✅ |

---

### OIDC + ABAC Mode (Multi-tenant)

**Configuration:**
```bash
OIDC_ISSUER=https://your-idp.com
OIDC_AUDIENCE=titan-aas
OIDC_CLIENT_ID=titan-client
OIDC_ROLES_CLAIM=roles

ENABLE_RATE_LIMITING=true
ENABLE_ABAC=true
ABAC_DEFAULT_DENY=true
```

**Behavior:**
- RBAC is evaluated first (role-based permissions)
- ABAC policies are evaluated second (attribute-based)
- Policies are evaluated in priority order (lower = higher priority)
- First ALLOW or DENY result is returned
- If no policy matches, default deny applies

**Admin Bypass Warning:**
```
┌────────────────────────────────────────────────────────────────┐
│ ⚠️  Admin Users Bypass ABAC Evaluation                         │
│                                                                 │
│ Users with the "admin" role skip all ABAC policy evaluation.  │
│ This is intentional for administrative override scenarios but  │
│ means admin users are not subject to:                          │
│                                                                 │
│ - Tenant isolation policies                                    │
│ - IP allowlist restrictions                                    │
│ - Time-based access controls                                   │
│ - Any custom ABAC policies                                     │
│                                                                 │
│ Grant admin roles sparingly.                                   │
└────────────────────────────────────────────────────────────────┘
```

**Code Reference:** `src/titan/security/deps.py:259-260`
```python
if engine is not None and not user.is_admin:
    # ABAC evaluation only happens for non-admin users
```

**Built-in ABAC Policies:**

| Policy | Priority | Description |
|--------|----------|-------------|
| `tenant_isolation` | 5 | Enforces multi-tenant data isolation |
| `allow_owner` | 10 | Allows resource owners full access |
| `ip_allowlist` | 20 | Restricts access by IP/CIDR |
| `resource_type` | 30 | Restricts actions per resource type |
| `time_based` | 50 | Restricts access by time/day |

---

## Rate Limiting

**Configuration:**
```bash
ENABLE_RATE_LIMITING=true
RATE_LIMIT_REQUESTS=100      # Requests per window
RATE_LIMIT_WINDOW=60         # Window in seconds
```

**Bypass Paths:**
- `/health/*` - Health check endpoints
- `/metrics` - Prometheus metrics endpoint

**Rate Limit Key:**
- Authenticated requests: SHA-256 hash of Bearer token (first 16 chars)
- Unauthenticated requests: Client IP address

**Headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704886800
Retry-After: 60  # Only when rate limited (429)
```

**Redis Unavailable Behavior:**
When Redis is unavailable, rate limiting fails open (requests are allowed) to maintain service availability. Monitor Redis connectivity.

---

## Security Headers

**Configuration:**
```bash
ENABLE_SECURITY_HEADERS=true
ENABLE_HSTS=true
HSTS_MAX_AGE=31536000        # 1 year (default)
HSTS_INCLUDE_SUBDOMAINS=true
HSTS_PRELOAD=false           # Enable only after HSTS is stable
CSP_POLICY=default-src 'self'
PERMISSIONS_POLICY=geolocation=()
```

**Default Headers:**
| Header | Default Value |
|--------|---------------|
| X-Content-Type-Options | `nosniff` |
| X-Frame-Options | `DENY` |
| Strict-Transport-Security | `max-age=31536000; includeSubDomains` |

---

## Audit Logging

All security events are logged to the audit log:

**Event Categories:**
- Authentication events (login, logout, token validation failure)
- Authorization decisions (RBAC grant, RBAC deny, ABAC grant, ABAC deny)
- Resource mutations (create, update, delete)

**Log Fields:**
```json
{
  "timestamp": "2026-01-10T12:34:56.789Z",
  "level": "INFO",
  "logger": "titan.security.audit",
  "event_type": "authorization",
  "user_sub": "user-123",
  "action": "delete:aas",
  "resource_id": "aas-456",
  "decision": "denied",
  "reason": "Insufficient permissions",
  "client_ip": "192.168.1.100",
  "correlation_id": "req-abc123"
}
```

---

## Production Deployment Checklist

Before deploying to production, verify:

- [ ] `OIDC_ISSUER` is set to your identity provider
- [ ] `OIDC_AUDIENCE` matches your registered application
- [ ] `ENABLE_RATE_LIMITING=true`
- [ ] `ENABLE_HSTS=true`
- [ ] `ENABLE_SECURITY_HEADERS=true`
- [ ] Redis is available and monitored
- [ ] Audit logs are shipped to central logging
- [ ] Admin roles are granted only to necessary users
- [ ] ABAC is enabled for multi-tenant deployments

---

## Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `OIDC_ISSUER` | unset | OIDC provider URL (e.g., `https://auth.example.com`) |
| `OIDC_AUDIENCE` | unset | Expected audience claim |
| `OIDC_CLIENT_ID` | unset | Client ID for token validation |
| `OIDC_ROLES_CLAIM` | `roles` | JWT claim containing user roles |
| `OIDC_JWKS_CACHE_SECONDS` | `3600` | JWKS cache TTL in seconds |
| `ALLOW_ANONYMOUS_ADMIN` | `false` | Allow anonymous admin when OIDC is unset (dev only) |
| `PUBLIC_HEALTH_ENDPOINTS` | `false` | Expose `/health*` without auth |
| `PUBLIC_METRICS_ENDPOINT` | `false` | Expose `/metrics` without auth |
| `PUBLIC_DESCRIPTION_ENDPOINTS` | `false` | Expose `/description*` without auth |
| `PUBLIC_JOBS_ENDPOINTS` | `false` | Expose `/jobs*` without auth |
| `PUBLIC_DEBUG_ENDPOINTS` | `false` | Expose `/debug/profile*` without auth |
| `ENABLE_RATE_LIMITING` | `true` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Window duration in seconds |
| `ENABLE_ABAC` | `false` | Enable ABAC policies |
| `ABAC_DEFAULT_DENY` | `true` | Deny if no policy matches |
| `ENABLE_SECURITY_HEADERS` | `true` | Add security response headers |
| `ENABLE_HSTS` | `true` | Enable HSTS header |
| `HSTS_MAX_AGE` | `31536000` | HSTS max-age in seconds |
| `HSTS_INCLUDE_SUBDOMAINS` | `true` | Include subdomains in HSTS |
| `HSTS_PRELOAD` | `false` | Add HSTS preload directive |
| `CSP_POLICY` | unset | Content-Security-Policy header value |
| `PERMISSIONS_POLICY` | unset | Permissions-Policy header value |
