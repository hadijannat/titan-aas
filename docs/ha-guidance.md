# High Availability Guidance

This document provides guidance for deploying Titan-AAS in a highly available configuration.

---

## Architecture Overview

Titan-AAS supports Active-Active deployments with horizontal scaling:

```
                          ┌─────────────────┐
                          │  Load Balancer  │
                          └────────┬────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        ┌─────┴─────┐        ┌─────┴─────┐        ┌─────┴─────┐
        │  Titan-1  │        │  Titan-2  │        │  Titan-3  │
        │  (Leader) │        │ (Replica) │        │ (Replica) │
        └─────┬─────┘        └─────┬─────┘        └─────┬─────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
        ┌─────┴─────┐        ┌─────┴─────┐        ┌─────┴─────┐
        │  Redis    │        │PostgreSQL │        │PostgreSQL │
        │(Primary)  │        │ (Primary) │        │ (Replica) │
        └───────────┘        └───────────┘        └───────────┘
```

### Components

| Component | Role | Scaling | Notes |
|-----------|------|---------|-------|
| Titan-AAS | Application | Horizontal | Stateless, all instances equivalent |
| PostgreSQL | Persistent store | Primary + replicas | Read replicas for scaling |
| Redis | Cache + events | Cluster or Sentinel | Required for HA |

---

## Active-Active Configuration

All Titan-AAS instances can serve both read and write requests:

### Load Balancer Configuration

```nginx
# nginx.conf example
upstream titan {
    least_conn;
    server titan-1:8080 weight=1;
    server titan-2:8080 weight=1;
    server titan-3:8080 weight=1;

    keepalive 32;
}

server {
    location / {
        proxy_pass http://titan;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }
}
```

### Health Check Configuration

Configure load balancer health checks:

```yaml
# Kubernetes Ingress example
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    nginx.ingress.kubernetes.io/healthcheck-path: /health/live
    nginx.ingress.kubernetes.io/healthcheck-interval-seconds: "5"
```

| Endpoint | Purpose | Use For |
|----------|---------|---------|
| `/health/live` | Liveness | Quick responsiveness check |
| `/health/ready` | Readiness | Full dependency check (DB + Redis) |

---

## Redis Leader Election

Titan-AAS uses Redis-based leader election for singleton tasks. See [ADR-0004](adr/0004-redis-leader-election.md) for details.

### How It Works

1. One instance acquires a Redis lock (`SET NX EX`)
2. Leader runs singleton tasks (cleanup, aggregation)
3. Lock has 30-second TTL with 10-second renewal
4. If leader fails, another instance acquires lock within 30s

### Tasks Requiring Leadership

| Task | Frequency | Impact of Duplication |
|------|-----------|----------------------|
| Blob cleanup | Every 6 hours | Minimal (idempotent) |
| Session cleanup | Every 15 min | Minimal (idempotent) |
| Metrics aggregation | Every 5 min | Data inconsistency |
| External sync | Configurable | Duplicate requests |

### Monitoring Leader Election

```bash
# Check current leader
redis-cli GET leader:cleanup-worker

# Watch leadership changes
redis-cli MONITOR | grep leader
```

---

## PostgreSQL High Availability

### Primary-Replica Setup

```
┌──────────────┐     Streaming      ┌──────────────┐
│  PostgreSQL  │ ─────Replication──►│  PostgreSQL  │
│   Primary    │                    │   Replica    │
└──────────────┘                    └──────────────┘
      ▲                                   ▲
      │ Writes                            │ Reads (optional)
      │                                   │
┌─────┴─────────────────────────────────────┴─────┐
│                   Titan-AAS                      │
└──────────────────────────────────────────────────┘
```

### Connection Configuration

```bash
# Primary for all operations (default)
DATABASE_URL=postgresql+asyncpg://titan:pass@pg-primary:5432/titan

# Read replica for scaling (future enhancement)
# DATABASE_READ_URL=postgresql+asyncpg://titan:pass@pg-replica:5432/titan
```

### Failover Considerations

For PostgreSQL failover:

1. **Automatic failover**: Use Patroni, pg_auto_failover, or cloud-managed PostgreSQL
2. **Connection pooling**: PgBouncer handles reconnection on failover
3. **DNS-based failover**: Update DNS to point to new primary

---

## Redis High Availability

### Redis Sentinel

For production deployments, use Redis Sentinel for automatic failover:

```bash
# Environment configuration
REDIS_URL=redis://sentinel1:26379,sentinel2:26379,sentinel3:26379/0?sentinelMaster=mymaster
```

### Redis Cluster

For larger deployments, Redis Cluster provides automatic sharding:

```bash
# Cluster mode requires cluster-aware client configuration
REDIS_URL=redis://node1:6379,node2:6379,node3:6379/0?cluster=true
```

### Failure Modes

| Scenario | Impact | Recovery |
|----------|--------|----------|
| Single Redis failure | Brief cache miss | Sentinel promotes replica |
| Full Redis outage | Cache disabled, rate limit disabled | Manual intervention |
| Network partition | May cause cache inconsistency | Sentinel elects new primary |

---

## Kubernetes Deployment

### Horizontal Pod Autoscaler

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: titan-aas
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: titan-aas
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Pod Disruption Budget

Ensure minimum availability during updates:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: titan-aas-pdb
spec:
  minAvailable: 2  # Or use percentage: 66%
  selector:
    matchLabels:
      app: titan-aas
```

### Anti-Affinity Rules

Spread pods across nodes:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: titan-aas
spec:
  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: titan-aas
              topologyKey: kubernetes.io/hostname
```

### Topology Spread

For multi-zone deployments:

```yaml
spec:
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app: titan-aas
```

---

## Failure Modes and Recovery

### Database Unavailable

**Symptoms:**
- `/health/ready` returns unhealthy
- API requests return 503 or timeout
- Log errors: "Connection refused" or "too many connections"

**Recovery:**
1. Check PostgreSQL status: `pg_isready -h $DB_HOST`
2. Verify connection count: `SELECT count(*) FROM pg_stat_activity`
3. Check disk space: `df -h /var/lib/postgresql`
4. Restart if needed: `systemctl restart postgresql`

**Automatic Handling:**
- Connection pool retries with backoff
- Readiness probe fails, pod removed from service

### Redis Unavailable

**Symptoms:**
- Cache misses (increased latency)
- Rate limiting disabled (fails open)
- WebSocket events not broadcast
- Leader election paused

**Recovery:**
1. Check Redis status: `redis-cli ping`
2. Check memory: `redis-cli INFO memory`
3. Check replication: `redis-cli INFO replication`
4. Restart if needed: `systemctl restart redis`

**Automatic Handling:**
- Requests continue (cache bypass)
- Rate limiting fails open (allows traffic)
- Leader tasks pause until Redis returns

### OIDC Provider Unavailable

**Symptoms:**
- All authenticated requests fail 401
- Log errors: "Failed to fetch JWKS"

**Recovery:**
1. Check OIDC endpoint: `curl $OIDC_ISSUER/.well-known/openid-configuration`
2. Verify network connectivity
3. Check OIDC provider status

**Automatic Handling:**
- JWKS cache fallback (stale keys used temporarily)
- Monitor cache age via logs

### Network Partition

**Symptoms:**
- Partial failures (some pods affected)
- Inconsistent state between instances
- Split-brain leadership (rare)

**Recovery:**
1. Identify partitioned nodes
2. Resolve network issues
3. Clear Redis locks if split-brain occurred
4. Verify data consistency

---

## Rolling Updates

### Zero-Downtime Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # Create 1 new pod before terminating old
      maxUnavailable: 0  # Never terminate pods unless new is ready
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
      - name: titan-aas
        lifecycle:
          preStop:
            exec:
              command: ["sleep", "5"]  # Allow in-flight requests
```

### Database Migrations

Run migrations before deploying new code:

```bash
# 1. Run migrations in maintenance window or with backward compatibility
titan db upgrade

# 2. Deploy new application version
kubectl set image deployment/titan-aas titan-aas=ghcr.io/hadijannat/titan-aas:v1.2.0

# 3. Monitor rollout
kubectl rollout status deployment/titan-aas
```

**Migration Safety:**
- All migrations are forward-compatible
- New code works with old schema during transition
- Rollback: `titan db downgrade -1`

---

## Monitoring for HA

### Key Metrics

| Metric | Alert Threshold | Meaning |
|--------|-----------------|---------|
| `up` | == 0 | Instance down |
| `http_requests_total{status=~"5.."}` | > 1% | Error rate too high |
| `pg_pool_available_connections` | < 5 | Connection pool exhaustion |
| `redis_connected_clients` | > 1000 | Too many connections |

### Alerting Rules

```yaml
# prometheus/alerts/ha.yml
groups:
- name: titan-ha
  rules:
  - alert: TitanInstanceDown
    expr: up{job="titan-aas"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Titan-AAS instance {{ $labels.instance }} is down"

  - alert: TitanNoLeader
    expr: absent(titan_leader_status == 1)
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "No Titan-AAS leader elected"

  - alert: TitanDatabaseConnectionsLow
    expr: pg_pool_available_connections < 5
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "Database connection pool nearly exhausted"
```

---

## Checklist

Before deploying HA configuration:

- [ ] Minimum 3 Titan-AAS instances
- [ ] PostgreSQL replication configured
- [ ] Redis Sentinel or Cluster deployed
- [ ] Load balancer health checks configured
- [ ] Pod Disruption Budget in place
- [ ] Anti-affinity rules applied
- [ ] Alerting rules deployed
- [ ] Runbook documented for failure scenarios
- [ ] DR procedure tested
