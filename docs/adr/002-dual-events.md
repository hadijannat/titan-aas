# ADR-002: Dual Event Systems with WebSocket and MQTT

## Status
Accepted

## Context
Titan-AAS needs to support real-time event notifications for:
1. **Web browsers**: Dashboard UIs, monitoring consoles, interactive applications
2. **Industrial IoT devices**: PLCs, sensors, edge gateways, SCADA systems

Two primary protocols serve these use cases:
- **WebSocket**: Full-duplex browser communication, native JavaScript support
- **MQTT**: Lightweight pub/sub protocol designed for IoT, widely supported by industrial devices

## Decision
We implement **both** WebSocket and MQTT event broadcasting:

- **WebSocket** for **browser clients**: Admin dashboards, monitoring UIs, web applications
- **MQTT** for **IoT integration**: PLCs, edge devices, industrial gateways, SCADA systems

Both receive the same event stream from the internal event bus.

## Rationale

### Why not just WebSocket?
1. **IoT device support**: Most industrial devices (PLCs, sensors) don't support WebSocket but have native MQTT clients
2. **Network resilience**: MQTT handles unreliable networks better with QoS levels and session persistence
3. **Lightweight**: MQTT has lower overhead for constrained devices
4. **Industry standard**: MQTT is the de-facto standard for industrial IoT communication

### Why not just MQTT?
1. **Browser support**: MQTT-over-WebSocket requires additional setup; native WebSocket is simpler for web clients
2. **Development experience**: JavaScript WebSocket API is more familiar to web developers
3. **No broker dependency**: WebSocket works without additional infrastructure for browser-only deployments

### Why both?
1. **Different clients, different needs**: Web developers expect WebSocket; industrial integrators expect MQTT
2. **Deployment flexibility**: Use WebSocket-only for simple setups, add MQTT for industrial integration
3. **Protocol bridging**: Titan-AAS acts as a bridge between web and industrial worlds

## Implementation Details

### Event Bus Architecture
```
Database Change
      ↓
  Event Bus (Redis Streams)
      ↓
 ┌────┴────┐
 ↓         ↓
WebSocket  MQTT
Handler    Handler
 ↓         ↓
Browser   IoT
Clients   Devices
```

### WebSocket
- Endpoint: `/ws/events`
- JSON messages with event type and payload
- Authentication via query parameter or initial message
- Subscription filtering by entity type and ID

### MQTT
- Topic structure: `titan/{entity_type}/{identifier}/events`
- JSON payload matching AAS event schema
- Configurable QoS level (default: 1)
- Optional message retention for last-known-good values
- Bidirectional: subscribe to `titan/element/+/+/value` for value updates

## Consequences

### Positive
- Seamless integration with both web applications and industrial systems
- No protocol translation needed at client level
- Flexible deployment options (WebSocket-only or full MQTT integration)
- Standard protocols with wide tooling support

### Negative
- Two event systems to maintain and monitor
- MQTT requires broker infrastructure (Mosquitto, etc.)
- Event schema must be compatible with both protocols

## Alternatives Considered

1. **WebSocket only**: Rejected due to poor IoT device support
2. **MQTT only**: Rejected due to browser complexity
3. **Server-Sent Events (SSE)**: Rejected as unidirectional only
4. **gRPC streaming**: Rejected due to limited browser support and industrial adoption
