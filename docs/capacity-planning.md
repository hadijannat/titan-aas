# Capacity Planning Guide

This document provides sizing guidelines for Titan-AAS deployments based on workload characteristics.

---

## Quick Reference

### Deployment Sizes

| Size | AAS Count | Submodels | Replicas | Memory | CPU | RPS Target |
|------|-----------|-----------|----------|--------|-----|------------|
| Small | 1K | 5K | 2 | 1GB | 1 | 2,000 |
| Medium | 10K | 50K | 3 | 2GB | 2 | 10,000 |
| Large | 100K | 500K | 5+ | 4GB | 4 | 25,000+ |
| XLarge | 1M+ | 5M+ | 10+ | 8GB+ | 8+ | 50,000+ |

---

## Workload Characteristics

### Read/Write Ratio

Titan-AAS is optimized for read-heavy workloads typical of Industrial IoT scenarios.

| Pattern | Read % | Write % | Recommended Config |
|---------|--------|---------|-------------------|
| Monitoring | 99% | 1% | Standard caching |
| Reporting | 95% | 5% | Aggressive caching |
| Interactive | 80% | 20% | Balanced |
| Sync/ETL | 50% | 50% | Write optimization |

### Request Patterns

| Pattern | Description | Impact |
|---------|-------------|--------|
| Burst | Sudden spike (e.g., shift change) | Need headroom |
| Sustained | Continuous load | Steady-state sizing |
| Periodic | Regular spikes (e.g., hourly reports) | Predictable scaling |

---

## Component Sizing

### Titan-AAS Application

**Memory sizing formula:**
```
Base: 256MB
+ 10MB per 1000 AAS (metadata caching)
+ 20MB per 1000 concurrent connections
+ 100MB for response buffers
```

**CPU sizing formula:**
```
1 vCPU per 3,000 cached read RPS
1 vCPU per 500 uncached read RPS
1 vCPU per 300 write RPS
```

**Example calculations:**

| Workload | RPS | Recommended CPU | Recommended Memory |
|----------|-----|-----------------|-------------------|
| 5K cached reads | 5,000 | 2 vCPU | 1GB |
| 15K cached reads | 15,000 | 5 vCPU | 2GB |
| 10K reads + 500 writes | 10,500 | 5 vCPU | 2GB |

### PostgreSQL

**Connection pool sizing:**
```
Connections = (workers * pool_size) + max_overflow

Default: 40 pool_size + 10 overflow = 50 per instance
3 instances = 150 connections required
```

**Memory sizing:**
```
shared_buffers: 25% of RAM (up to 8GB)
effective_cache_size: 75% of RAM
work_mem: 32-64MB per connection
maintenance_work_mem: 256MB-1GB
```

**Disk sizing:**
```
Base storage: 100MB (schema + indexes)
Per AAS: ~10KB (document + indexes)
Per Submodel: ~20KB (document + indexes + elements)

100K AAS + 500K Submodels ≈ 11GB
```

**Recommended PostgreSQL instances:**

| Dataset Size | vCPU | Memory | Storage | IOPS |
|--------------|------|--------|---------|------|
| Small (1K) | 2 | 4GB | 20GB SSD | 1,000 |
| Medium (10K) | 4 | 8GB | 50GB SSD | 3,000 |
| Large (100K) | 8 | 16GB | 200GB NVMe | 10,000 |
| XLarge (1M+) | 16+ | 64GB+ | 1TB+ NVMe | 50,000+ |

### Redis

**Memory sizing:**
```
Per cached AAS: ~5KB (serialized JSON)
Per cached Submodel: ~10KB (serialized JSON)
Rate limit keys: ~200 bytes per active client
Session data: ~1KB per session

100K AAS + 500K Submodels (50% cache hit) ≈ 3GB
```

**Recommended Redis instances:**

| Workload | Memory | Deployment |
|----------|--------|------------|
| Small | 512MB | Single instance |
| Medium | 2GB | Single instance |
| Large | 8GB | Sentinel (3 nodes) |
| XLarge | 32GB+ | Redis Cluster |

---

## Performance Targets

### Latency SLOs

| Operation | Target p50 | Target p99 | Cache |
|-----------|------------|------------|-------|
| Read single entity | < 2ms | < 10ms | Hit |
| Read single entity | < 5ms | < 25ms | Miss |
| List (paginated) | < 5ms | < 50ms | Hit |
| List (paginated) | < 20ms | < 100ms | Miss |
| Create entity | < 20ms | < 100ms | N/A |
| Update entity | < 25ms | < 150ms | N/A |

### Throughput Targets

| Metric | Development | Production | High-Scale |
|--------|-------------|------------|------------|
| Read RPS (cached) | 2,000 | 15,000 | 50,000+ |
| Read RPS (uncached) | 500 | 5,000 | 20,000+ |
| Write RPS | 100 | 800 | 5,000+ |
| Concurrent connections | 50 | 500 | 5,000+ |

---

## Scaling Strategies

### Vertical Scaling

When to scale up:

| Symptom | Component | Action |
|---------|-----------|--------|
| High CPU utilization | Application | Add CPU cores |
| Memory pressure | Application | Add RAM |
| Slow queries | PostgreSQL | Add RAM for buffers |
| High IOPS | PostgreSQL | Switch to NVMe |
| Cache evictions | Redis | Add memory |

### Horizontal Scaling

When to scale out:

| Symptom | Component | Action |
|---------|-----------|--------|
| CPU saturated | Application | Add replicas |
| Connection exhaustion | Application | Add replicas |
| Read bottleneck | PostgreSQL | Add read replicas |
| Cache hit rate low | Redis | Add memory or nodes |

### Scaling Thresholds

Recommended HPA configuration:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        averageUtilization: 70  # Scale at 70% CPU
  - type: Resource
    resource:
      name: memory
      target:
        averageUtilization: 80  # Scale at 80% memory
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
```

---

## Resource Configurations

### Small Deployment (1K AAS)

```yaml
# Application
replicas: 2
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "1Gi"
    cpu: "1"

# PostgreSQL
resources:
  memory: "2Gi"
  cpu: "1"
storage: 20Gi

# Redis
resources:
  memory: "512Mi"
```

### Medium Deployment (10K AAS)

```yaml
# Application
replicas: 3
resources:
  requests:
    memory: "1Gi"
    cpu: "1"
  limits:
    memory: "2Gi"
    cpu: "2"

# PostgreSQL (with read replica)
primary:
  memory: "8Gi"
  cpu: "4"
  storage: 100Gi
replica:
  memory: "4Gi"
  cpu: "2"
  storage: 100Gi

# Redis Sentinel
sentinel:
  replicas: 3
  memory: "2Gi"
```

### Large Deployment (100K AAS)

```yaml
# Application
replicas: 5
resources:
  requests:
    memory: "2Gi"
    cpu: "2"
  limits:
    memory: "4Gi"
    cpu: "4"

hpa:
  minReplicas: 5
  maxReplicas: 20

# PostgreSQL
primary:
  memory: "32Gi"
  cpu: "8"
  storage: 500Gi
  storageClass: nvme-ssd
replicas:
  count: 2
  memory: "16Gi"
  cpu: "4"

# Redis Cluster
cluster:
  nodes: 6  # 3 masters + 3 replicas
  memory: "8Gi"
```

---

## Cost Estimation

### Cloud Provider Reference (Monthly)

| Component | Small | Medium | Large |
|-----------|-------|--------|-------|
| Application (3 pods) | $75 | $200 | $600 |
| PostgreSQL (managed) | $50 | $200 | $800 |
| Redis (managed) | $25 | $75 | $300 |
| Load Balancer | $20 | $20 | $40 |
| Storage (100GB) | $10 | $25 | $100 |
| **Total** | **~$180** | **~$520** | **~$1,840** |

*Estimates based on typical cloud pricing. Actual costs vary by provider and region.*

---

## Monitoring for Capacity

### Key Metrics to Watch

| Metric | Warning | Critical |
|--------|---------|----------|
| CPU utilization | > 70% | > 90% |
| Memory utilization | > 75% | > 90% |
| DB connections used | > 80% | > 95% |
| Redis memory used | > 70% | > 90% |
| Request latency p99 | > 100ms | > 500ms |
| Error rate | > 0.1% | > 1% |

### Capacity Alerts

```yaml
# prometheus/alerts/capacity.yml
groups:
- name: capacity
  rules:
  - alert: TitanCPUHighUtilization
    expr: avg(rate(container_cpu_usage_seconds_total{container="titan-aas"}[5m])) > 0.7
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "High CPU utilization - consider scaling"

  - alert: TitanMemoryHighUtilization
    expr: container_memory_usage_bytes{container="titan-aas"} / container_spec_memory_limit_bytes > 0.8
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "High memory utilization - consider scaling"

  - alert: PostgreSQLConnectionsHigh
    expr: pg_stat_activity_count / pg_settings_max_connections > 0.8
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "PostgreSQL connection pool nearly exhausted"
```

---

## Growth Planning

### Forecasting

Track these metrics monthly:

1. **Entity growth rate**: AAS and Submodels created per month
2. **Request growth rate**: RPS increase over time
3. **Storage growth rate**: Database size increase
4. **User growth rate**: Concurrent connections increase

### Planning Horizon

| Metric | Action Trigger | Lead Time |
|--------|----------------|-----------|
| CPU > 60% sustained | Plan scale-up | 2 weeks |
| Memory > 70% sustained | Plan scale-up | 2 weeks |
| Storage > 70% | Add capacity | 1 week |
| Approaching connection limit | Add replicas | 1 week |

### Scaling Events

Document expected scaling triggers:

| Event | Expected Impact | Pre-scaling Required |
|-------|-----------------|---------------------|
| New production line | +10K AAS | Yes |
| Peak season | +50% traffic | Yes (HPA handles) |
| Data migration | +100K Submodels | Yes |
| New integration | +1000 RPS | Maybe |
