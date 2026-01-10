# Security Overview

This document describes Titan-AAS security behavior and configuration.

## OIDC Authentication

When `OIDC_ISSUER` is set, Titan-AAS validates JWT access tokens using the
issuer's JWKS endpoint. Requests must include:

```
Authorization: Bearer <access_token>
```

Configuration (env vars):

- `OIDC_ISSUER` (required to enable OIDC)
- `OIDC_AUDIENCE` (defaults to `TITAN_APP_NAME` if unset)
- `OIDC_CLIENT_ID` (optional, for client-role extraction)
- `OIDC_ROLES_CLAIM` (default: `roles`)
- `OIDC_JWKS_CACHE_SECONDS` (default: `3600`)

Role extraction supports:

- top-level `roles` claim (list or string)
- `realm_access.roles` (Keycloak)
- `resource_access.<client_id>.roles` (Keycloak client roles)

Authorization helpers treat `admin` or `titan:admin` as admin roles, and
`reader`/`writer`/`titan:read`/`titan:write` as read/write roles.

## Rate Limiting

Rate limiting is enabled by default via Redis-backed sliding windows.

Configuration (env vars):

- `ENABLE_RATE_LIMITING` (default: `true`)
- `RATE_LIMIT_REQUESTS` (default: `100`)
- `RATE_LIMIT_WINDOW` (default: `60` seconds)

Behavior:

- Unauthenticated requests are limited by client IP.
- Authenticated requests are limited by a hash of the bearer token.
- Standard rate limit headers are added to responses when enabled.

## Threat Model Notes

- TLS termination is expected at the ingress or gateway.
- Tokens are validated on each request; no token introspection is performed.
- JWKS keys are cached to reduce upstream dependency and latency.
