"""Load test configuration for 15,000+ RPS validation.

This configuration defines the performance targets for production-ready
Titan-AAS deployment. These thresholds should be validated in CI and
before production releases.

Usage:
    # Import in locustfile or test scripts
    from tests.load.config_15k import TARGETS

    # Or use directly with locust
    locust -f tests/load/locustfile.py \
        --headless \
        -u 500 \
        -r 50 \
        -t 5m \
        --html benchmark-results/report.html
"""

from __future__ import annotations

# Performance targets for 15K+ RPS production workloads
TARGETS = {
    # Throughput targets
    "min_rps": 15000,  # Minimum requests per second
    "target_rps": 20000,  # Target requests per second
    # Latency targets (milliseconds)
    "p50_ms": 10,  # Median latency
    "p95_ms": 50,  # 95th percentile
    "p99_ms": 100,  # 99th percentile
    "max_ms": 500,  # Maximum acceptable latency
    # Error rate targets
    "max_error_rate": 0.001,  # 0.1% max error rate
    # Cache performance
    "min_cache_hit_ratio": 0.85,  # 85% cache hit ratio
}

# Load test configuration for different environments
LOAD_PROFILES = {
    "ci": {
        # CI environment (limited resources)
        "users": 100,
        "spawn_rate": 20,
        "duration": "60s",
        "target_rps": 5000,  # Lower target for CI
        "p99_ms": 200,  # More lenient for CI
        "max_error_rate": 0.01,  # 1% allowed in CI
    },
    "staging": {
        # Staging environment (production-like)
        "users": 300,
        "spawn_rate": 30,
        "duration": "180s",
        "target_rps": 10000,
        "p99_ms": 150,
        "max_error_rate": 0.005,
    },
    "production": {
        # Production validation
        "users": 500,
        "spawn_rate": 50,
        "duration": "300s",
        "target_rps": 15000,
        "p99_ms": 100,
        "max_error_rate": 0.001,
    },
}

# Endpoint-specific latency targets (cached reads)
ENDPOINT_TARGETS = {
    "/shells/{id}": {
        "p50_ms": 1.0,
        "p95_ms": 2.0,
        "p99_ms": 5.0,
    },
    "/submodels/{id}": {
        "p50_ms": 1.0,
        "p95_ms": 2.0,
        "p99_ms": 5.0,
    },
    "/shells": {
        "p50_ms": 5.0,
        "p95_ms": 10.0,
        "p99_ms": 20.0,
    },
    "/submodels": {
        "p50_ms": 5.0,
        "p95_ms": 10.0,
        "p99_ms": 20.0,
    },
}

# Database connection pool requirements for 15K+ RPS
# Based on Little's Law: connections = RPS * avg_query_time
# 15000 RPS * 3ms avg = 45 concurrent connections
DB_POOL_REQUIREMENTS = {
    "pool_size": 40,  # Base connections
    "max_overflow": 10,  # Burst capacity
    "pool_timeout": 30,  # Wait timeout (seconds)
    "pool_recycle": 1800,  # Connection max age (30 min)
}

# Redis connection pool requirements
REDIS_REQUIREMENTS = {
    "max_connections": 50,
    "socket_timeout": 5,
    "socket_connect_timeout": 5,
}
