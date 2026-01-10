# Titan-AAS Deployment Runbook

This runbook covers deployment, operations, and troubleshooting for Titan-AAS.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Docker Compose Deployment](#docker-compose-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Configuration Reference](#configuration-reference)
6. [Operations](#operations)
7. [Troubleshooting](#troubleshooting)
8. [Backup and Recovery](#backup-and-recovery)

---

## Prerequisites

### Required Tools

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | 24.0+ | Container runtime |
| Docker Compose | 2.20+ | Local orchestration |
| kubectl | 1.28+ | Kubernetes CLI |
| Helm | 3.12+ | Kubernetes package manager |
| uv | 0.1+ | Python package manager |

### Infrastructure Requirements

**Minimum (Development):**
- 2 CPU cores
- 4GB RAM
- 20GB disk

**Recommended (Production):**
- 4+ CPU cores
- 8GB+ RAM
- 100GB+ SSD disk
- PostgreSQL 16+ (managed preferred)
- Redis 7+ (managed preferred)

---

## Local Development

### Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/titan-aas.git
cd titan-aas

# Install dependencies
uv sync

# Start infrastructure
cd deployment
docker compose up -d postgres redis mosquitto

# Run migrations
uv run -- alembic upgrade head

# Start development server
uv run -- python -m titan.main
```

### Running Tests

```bash
# Unit tests
uv run -- pytest tests/unit -v

# Integration tests (requires Docker)
uv run -- pytest tests/integration -v

# All tests
uv run -- pytest

# With coverage
uv run -- pytest --cov=src/titan --cov-report=html
```

---

## Docker Compose Deployment

### Full Stack Deployment

```bash
cd deployment

# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f titan
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| titan | 8080 | Main API server |
| postgres | 5432 | Database |
| redis | 6379 | Cache |
| mosquitto | 1883, 9001 | MQTT broker |
| prometheus | 9090 | Metrics |
| grafana | 3000 | Dashboards |
| jaeger | 16686 | Tracing UI |

### Verify Deployment

```bash
# Health check
curl http://localhost:8080/health

# API test
curl http://localhost:8080/shells

# Prometheus
curl http://localhost:9090/-/healthy

# Grafana (admin/admin)
open http://localhost:3000
```

---

## Kubernetes Deployment

### Prerequisites

```bash
# Add Helm repos
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Create namespace
kubectl create namespace titan
```

### Install with Helm

```bash
cd charts/titan-aas

# Install with default values
helm install titan . -n titan

# Install with custom values
helm install titan . -n titan -f values-production.yaml

# Upgrade
helm upgrade titan . -n titan

# Uninstall
helm uninstall titan -n titan
```

### Production Values Example

```yaml
# values-production.yaml
replicaCount: 3

image:
  repository: ghcr.io/your-org/titan-aas
  tag: v1.0.0

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: aas.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: aas-tls
      hosts:
        - aas.example.com

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi

oidc:
  enabled: true
  issuer: https://idp.example.com/realms/titan
  audience: titan-aas

postgresql:
  enabled: false  # Use external managed database

externalDatabase:
  host: postgres.example.com
  port: 5432
  database: titan
  existingSecret: titan-db-credentials
  existingSecretPasswordKey: password

redis:
  enabled: false  # Use external managed Redis

externalRedis:
  host: redis.example.com
  port: 6379
  existingSecret: titan-redis-credentials
```

### Verify Kubernetes Deployment

```bash
# Check pods
kubectl get pods -n titan

# Check services
kubectl get svc -n titan

# View logs
kubectl logs -f deployment/titan-titan-aas -n titan

# Port forward for testing
kubectl port-forward svc/titan-titan-aas 8080:8080 -n titan
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TITAN_ENV` | development | Environment (development/staging/production) |
| `TITAN_HOST` | 0.0.0.0 | Bind address |
| `TITAN_PORT` | 8080 | HTTP port |
| `TITAN_LOG_LEVEL` | INFO | Log level (DEBUG/INFO/WARNING/ERROR) |
| `DATABASE_URL` | - | PostgreSQL connection string |
| `REDIS_URL` | - | Redis connection string |
| `MQTT_BROKER` | localhost | MQTT broker hostname |
| `MQTT_PORT` | 1883 | MQTT port |
| `OIDC_ISSUER` | - | OIDC issuer URL |
| `OIDC_AUDIENCE` | titan-aas | OIDC audience |
| `BLOB_STORAGE_TYPE` | local | Blob storage (local/s3) |
| `S3_BUCKET` | - | S3 bucket for blobs |
| `S3_ENDPOINT` | - | S3-compatible endpoint |
| `ENABLE_TRACING` | false | Enable OpenTelemetry tracing |
| `OTLP_ENDPOINT` | - | OTLP collector endpoint |
| `ENABLE_METRICS` | true | Enable Prometheus metrics |

### Database Connection String

```
postgresql+asyncpg://user:password@host:5432/database
```

Options:
- `?ssl=require` - Enable SSL
- `?pool_size=20` - Connection pool size
- `?max_overflow=10` - Max overflow connections

---

## Operations

### Scaling

**Docker Compose:**
```bash
docker compose up -d --scale titan=3
```

**Kubernetes:**
```bash
# Manual scaling
kubectl scale deployment titan-titan-aas --replicas=5 -n titan

# HPA will auto-scale based on CPU/memory
kubectl get hpa -n titan
```

### Database Migrations

```bash
# Apply migrations
uv run -- alembic upgrade head

# Rollback one version
uv run -- alembic downgrade -1

# Show current version
uv run -- alembic current

# Generate new migration
uv run -- alembic revision --autogenerate -m "Add new table"
```

### Log Aggregation

**Docker Compose:**
```bash
# Follow all logs
docker compose logs -f

# Specific service
docker compose logs -f titan

# Last 100 lines
docker compose logs --tail=100 titan
```

**Kubernetes:**
```bash
# Stern for multi-pod logs
stern titan -n titan

# kubectl
kubectl logs -f -l app.kubernetes.io/name=titan-aas -n titan
```

### Metrics and Monitoring

**Prometheus Queries:**
```promql
# Request rate
rate(http_requests_total{job="titan-aas"}[5m])

# Error rate
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

# P99 latency
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Cache hit rate
sum(rate(cache_hits_total[5m])) / (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
```

**Grafana Dashboards:**
- Access at http://localhost:3000 (admin/admin)
- Pre-configured Titan-AAS dashboard included

---

## Troubleshooting

### Common Issues

#### Service Won't Start

```bash
# Check container logs
docker compose logs titan

# Common causes:
# - Database not ready: Wait for postgres healthcheck
# - Missing environment variables: Check .env file
# - Port conflict: Change TITAN_PORT
```

#### High Latency

1. **Check cache hit rate:**
   ```promql
   sum(rate(cache_hits_total[5m])) / (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
   ```
   Should be >95%

2. **Check database queries:**
   ```bash
   # Slow query log
   docker compose exec postgres psql -U titan -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
   ```

3. **Check connection pool:**
   ```promql
   db_pool_connections_active / db_pool_connections_max
   ```
   Should be <80%

#### Memory Issues

```bash
# Check container memory
docker stats

# Kubernetes
kubectl top pods -n titan

# Common causes:
# - Large response payloads: Use pagination
# - Connection leaks: Check pool metrics
# - Cache size: Tune Redis maxmemory
```

#### Database Connection Errors

```bash
# Test connection
docker compose exec titan python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
engine = create_async_engine('postgresql+asyncpg://titan:titan@postgres:5432/titan')
asyncio.run(engine.dispose())
print('Connection OK')
"

# Check pool exhaustion
# If db_pool_connections_active == db_pool_connections_max, increase pool size
```

#### Redis Connection Errors

```bash
# Test connection
docker compose exec titan python -c "
import redis
r = redis.from_url('redis://redis:6379/0')
r.ping()
print('Connection OK')
"
```

### Debug Mode

```bash
# Enable debug logging
TITAN_LOG_LEVEL=DEBUG docker compose up titan
```

### Health Check Failures

```bash
# Detailed health check
curl -s http://localhost:8080/health | jq

# Expected output:
{
  "status": "healthy",
  "checks": {
    "database": {"status": "up"},
    "redis": {"status": "up"},
    "mqtt": {"status": "up"}
  }
}
```

---

## Backup and Recovery

### PostgreSQL Backup

```bash
# Create backup
docker compose exec postgres pg_dump -U titan titan > backup.sql

# Compressed backup
docker compose exec postgres pg_dump -U titan -Fc titan > backup.dump

# Restore
docker compose exec -T postgres psql -U titan titan < backup.sql
```

### Scheduled Backups (Kubernetes)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: titan-db-backup
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:16-alpine
              command:
                - /bin/sh
                - -c
                - |
                  pg_dump -h $DB_HOST -U $DB_USER $DB_NAME | gzip > /backups/titan-$(date +%Y%m%d).sql.gz
              envFrom:
                - secretRef:
                    name: titan-db-credentials
              volumeMounts:
                - name: backup-volume
                  mountPath: /backups
          volumes:
            - name: backup-volume
              persistentVolumeClaim:
                claimName: backup-pvc
          restartPolicy: OnFailure
```

### Redis Backup

```bash
# Trigger RDB snapshot
docker compose exec redis redis-cli BGSAVE

# Copy RDB file
docker compose cp redis:/data/dump.rdb ./redis-backup.rdb
```

### Disaster Recovery

1. **Stop services:**
   ```bash
   docker compose down
   ```

2. **Restore database:**
   ```bash
   docker compose up -d postgres
   docker compose exec -T postgres psql -U titan titan < backup.sql
   ```

3. **Restore Redis (optional):**
   ```bash
   docker compose cp ./redis-backup.rdb redis:/data/dump.rdb
   ```

4. **Start services:**
   ```bash
   docker compose up -d
   ```

5. **Verify:**
   ```bash
   curl http://localhost:8080/health
   ```

---

## Security Checklist

- [ ] OIDC authentication enabled
- [ ] TLS enabled for all endpoints
- [ ] Database credentials in secrets (not env vars)
- [ ] Network policies restricting pod communication
- [ ] Resource limits set on all containers
- [ ] Security scanning in CI/CD pipeline
- [ ] Regular dependency updates
- [ ] Audit logging enabled
- [ ] Backup encryption enabled
