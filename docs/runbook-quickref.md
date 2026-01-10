# Runbook Quick Reference

One-page operational reference for Titan-AAS incident response.

---

## Health Check Commands

```bash
# Application health
curl http://localhost:8080/health/live    # Liveness
curl http://localhost:8080/health/ready   # Readiness (checks DB + Redis)

# PostgreSQL
pg_isready -h $DB_HOST -p 5432

# Redis
redis-cli -h $REDIS_HOST ping
```

---

## Common Issues

### Service Down

**Symptom:** `/health/live` returns 503 or timeout

```bash
# Check pods
kubectl get pods -l app=titan-aas

# Check logs
kubectl logs -l app=titan-aas --tail=100

# Restart if needed
kubectl rollout restart deployment/titan-aas

# Check events
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

### Database Connection Issues

**Symptom:** `/health/ready` fails, logs show "connection refused"

```bash
# Check PostgreSQL status
kubectl exec -it postgres-0 -- pg_isready

# Check connection count
kubectl exec -it postgres-0 -- psql -c "SELECT count(*) FROM pg_stat_activity"

# Check for blocking queries
kubectl exec -it postgres-0 -- psql -c "
SELECT pid, query, state, wait_event_type
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start"

# Kill blocking query if needed
kubectl exec -it postgres-0 -- psql -c "SELECT pg_terminate_backend(PID)"
```

### Redis Connection Issues

**Symptom:** Cache misses, rate limiting disabled

```bash
# Check Redis status
kubectl exec -it redis-0 -- redis-cli ping

# Check memory
kubectl exec -it redis-0 -- redis-cli INFO memory | grep used_memory_human

# Check connections
kubectl exec -it redis-0 -- redis-cli INFO clients | grep connected_clients

# Clear cache if needed
kubectl exec -it redis-0 -- redis-cli FLUSHDB
```

### High Latency

**Symptom:** p99 latency > 100ms

```bash
# Check cache hit rate
kubectl exec -it redis-0 -- redis-cli INFO stats | grep keyspace

# Check slow queries
kubectl exec -it postgres-0 -- psql -c "
SELECT query, calls, mean_time, total_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10"

# Check CPU/memory
kubectl top pods -l app=titan-aas

# Scale if needed
kubectl scale deployment/titan-aas --replicas=5
```

### High Error Rate

**Symptom:** > 1% 5xx errors

```bash
# Check error logs
kubectl logs -l app=titan-aas --tail=500 | grep -i error

# Check if specific endpoint
kubectl logs -l app=titan-aas --tail=500 | grep "HTTP/1.1\" 5"

# Check database errors
kubectl exec -it postgres-0 -- psql -c "
SELECT * FROM pg_stat_database_conflicts"
```

---

## Authentication Issues

### All Auth Failing (401)

```bash
# Check OIDC configuration
kubectl exec -it titan-aas-xxx -- env | grep OIDC

# Test OIDC endpoint
curl -s "$OIDC_ISSUER/.well-known/openid-configuration"

# Check JWKS cache age in logs
kubectl logs -l app=titan-aas | grep -i jwks
```

### Permission Denied (403)

```bash
# Check user roles in token
# Decode JWT at https://jwt.io

# Check RBAC logs
kubectl logs -l app=titan-aas | grep -i "permission\|403"

# Verify ABAC if enabled
kubectl exec -it titan-aas-xxx -- env | grep ABAC
```

---

## Rate Limiting

### Too Many 429 Responses

```bash
# Check current rate limit config
kubectl exec -it titan-aas-xxx -- env | grep RATE_LIMIT

# Check Redis rate limit keys
kubectl exec -it redis-0 -- redis-cli KEYS "ratelimit:*" | wc -l

# Clear rate limit for IP
kubectl exec -it redis-0 -- redis-cli DEL "ratelimit:ip:192.168.1.100"

# Increase limit temporarily
kubectl set env deployment/titan-aas RATE_LIMIT_REQUESTS=500
```

---

## Database Operations

### Migration Issues

```bash
# Check current migration
kubectl exec -it titan-aas-xxx -- titan db current

# Run pending migrations
kubectl exec -it titan-aas-xxx -- titan db upgrade

# Rollback last migration
kubectl exec -it titan-aas-xxx -- titan db downgrade -1

# Show migration history
kubectl exec -it titan-aas-xxx -- titan db history
```

### Backup/Restore

```bash
# Create backup
kubectl exec -it postgres-0 -- pg_dump -U titan titan > backup.sql

# Restore backup
kubectl exec -i postgres-0 -- psql -U titan titan < backup.sql
```

---

## Rollback Procedures

### Application Rollback

```bash
# View rollout history
kubectl rollout history deployment/titan-aas

# Rollback to previous version
kubectl rollout undo deployment/titan-aas

# Rollback to specific revision
kubectl rollout undo deployment/titan-aas --to-revision=3

# Verify rollback
kubectl rollout status deployment/titan-aas
```

### Emergency Stop

```bash
# Scale to zero (stop all traffic)
kubectl scale deployment/titan-aas --replicas=0

# Investigate
kubectl logs -l app=titan-aas --tail=1000 > emergency-logs.txt

# Restore
kubectl scale deployment/titan-aas --replicas=3
```

---

## Monitoring Commands

### Quick Status

```bash
# Pod status
kubectl get pods -l app=titan-aas -o wide

# Resource usage
kubectl top pods -l app=titan-aas

# Recent events
kubectl get events --field-selector involvedObject.name=titan-aas --sort-by='.lastTimestamp'
```

### Metrics

```bash
# Prometheus metrics
curl http://localhost:8080/metrics | grep http_requests

# Request rate
curl -s http://localhost:8080/metrics | grep 'http_requests_total{' | head -5

# Error rate
curl -s http://localhost:8080/metrics | grep 'http_requests_total{status="5'
```

---

## Security Incident Response

### Suspected Breach

```bash
# 1. Enable audit log forwarding (if not already)
kubectl set env deployment/titan-aas AUDIT_LOG_LEVEL=DEBUG

# 2. Capture current state
kubectl logs -l app=titan-aas --tail=10000 > incident-logs.txt

# 3. Check authentication failures
grep -i "401\|authentication\|unauthorized" incident-logs.txt

# 4. Check suspicious IPs
grep -oE "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" incident-logs.txt | sort | uniq -c | sort -rn | head -20

# 5. Block suspicious IP (if using nginx ingress)
kubectl annotate ingress titan-aas nginx.ingress.kubernetes.io/whitelist-source-range="0.0.0.0/0" --overwrite
# Then update to block specific IPs
```

### Token Compromise

```bash
# 1. Revoke at OIDC provider (external action)

# 2. Clear Redis cache to force re-validation
kubectl exec -it redis-0 -- redis-cli FLUSHDB

# 3. Restart to clear any in-memory state
kubectl rollout restart deployment/titan-aas

# 4. Monitor for continued access attempts
kubectl logs -f -l app=titan-aas | grep -i "auth\|401\|403"
```

---

## Contact & Escalation

| Level | Contact | When |
|-------|---------|------|
| L1 | On-call engineer | First response |
| L2 | Platform team | DB/Redis issues |
| L3 | Core developers | Application bugs |
| Vendor | Anthropic support | Critical bugs |

---

## Quick Links

- [Full Runbook](deployment-runbook.md)
- [HA Guidance](ha-guidance.md)
- [Security Modes](security-modes.md)
- [Capacity Planning](capacity-planning.md)
- [Benchmarks](benchmarks.md)
