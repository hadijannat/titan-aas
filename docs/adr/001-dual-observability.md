# ADR-001: Dual Observability with Prometheus and OpenTelemetry

## Status
Accepted

## Context
Titan-AAS requires comprehensive observability for production deployments. There are two main observability signals we need to capture:

1. **Metrics**: Quantitative measurements over time (request rates, latencies, error counts, resource utilization)
2. **Traces**: Distributed request flows across services with timing and causality information

Two major observability standards exist in the cloud-native ecosystem:
- **Prometheus**: Pull-based metrics collection with a rich ecosystem of exporters, alerting (Alertmanager), and dashboards (Grafana)
- **OpenTelemetry (OTEL)**: Vendor-neutral standard for traces, metrics, and logs with wide language support

## Decision
We implement **both** Prometheus and OpenTelemetry, using each for its primary strength:

- **Prometheus** for **metrics**: Request counts, latencies (histograms), cache hit rates, connection pool sizes, error rates
- **OpenTelemetry** for **traces**: Distributed tracing across HTTP requests, database queries, cache operations, and MQTT messages

## Rationale

### Why not just Prometheus?
Prometheus excels at metrics but has limited tracing support. While Prometheus can correlate metrics with trace IDs via exemplars, it cannot provide the full distributed trace visualization that OpenTelemetry offers.

### Why not just OpenTelemetry?
OpenTelemetry supports all three signals (traces, metrics, logs), but:
1. The Prometheus ecosystem is more mature for alerting (Alertmanager rules, Grafana dashboards)
2. Many existing monitoring stacks are Prometheus-native
3. Pull-based Prometheus metrics are simpler to operate (no collector infrastructure required for basic setups)

### Why both?
1. **Best-of-breed**: Each tool excels at its primary use case
2. **Ecosystem compatibility**: Works with existing Prometheus stacks AND OpenTelemetry backends (Jaeger, Tempo, etc.)
3. **Flexibility**: Operators can choose their preferred backend for each signal
4. **Low overhead**: Both are lightweight when properly configured

## Implementation Details

### Prometheus Metrics
- Exposed at `/metrics` endpoint in Prometheus exposition format
- Key metrics: `titan_http_requests_total`, `titan_http_request_duration_seconds`, `titan_cache_hit_total`, etc.
- Custom middleware adds request-scoped labels (method, path, status)

### OpenTelemetry Traces
- OTLP exporter sends traces to configured collector (Jaeger, Tempo, etc.)
- Automatic instrumentation for FastAPI, SQLAlchemy, Redis, httpx
- Custom spans for business operations (template instantiation, AASX parsing)
- Trace context propagation via W3C Trace Context headers

## Consequences

### Positive
- Rich visibility into both real-time metrics and request flows
- Compatible with existing monitoring infrastructure
- Enables correlation between metrics spikes and specific trace investigations

### Negative
- Two observability systems to configure and maintain
- Slightly higher resource usage (though both are efficient)
- Operators need familiarity with both ecosystems

## Alternatives Considered

1. **Prometheus only**: Rejected due to limited tracing support
2. **OpenTelemetry only**: Rejected due to less mature alerting ecosystem
3. **Datadog/New Relic unified**: Rejected due to vendor lock-in and cost
