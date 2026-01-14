# 🚀 Titan-AAS: Try It Yourself

> A hands-on guide to verify the claimed functionalities from the [LinkedIn post](https://www.linkedin.com/posts/hadi-jannat_assetadministrationshell-digitaltwin-industry40-activity-7415759993414873088--Q53)

---

## ⏱️ 5-Minute Quickstart

```bash
# Clone and start
git clone https://github.com/hadijannat/titan-aas.git
cd titan-aas

# For local dev without OIDC (explicitly opt-in)
export ALLOW_ANONYMOUS_ADMIN=true

docker compose -f deployment/docker-compose.yml up -d

# Verify it's running
curl http://localhost:8080/health/live
# Expected: {"status":"ok"}
```

---

## ✅ Verify Each Claimed Functionality

### 1. Create an Asset Administration Shell (Write Path)

**Claim**: "Writes: validate (Pydantic v2) → canonical JSON (orjson) → persist"

```bash
# Create a digital twin for a robot arm
curl -X POST http://localhost:8080/shells \
  -H "Content-Type: application/json" \
  -d '{
    "id": "urn:titan:aas:robot-arm-001",
    "idShort": "RobotArm001",
    "assetInformation": {
      "assetKind": "Instance",
      "globalAssetId": "urn:titan:asset:kuka-kr-16"
    }
  }'
```

**Expected Output**:
```json
{
  "id": "urn:titan:aas:robot-arm-001",
  "idShort": "RobotArm001",
  "assetInformation": {
    "assetKind": "Instance",
    "globalAssetId": "urn:titan:asset:kuka-kr-16"
  }
}
```

---

### 2. Create a Submodel with Properties

```bash
# Create a Technical Data submodel
curl -X POST http://localhost:8080/submodels \
  -H "Content-Type: application/json" \
  -d '{
    "id": "urn:titan:submodel:technical-data-001",
    "idShort": "TechnicalData",
    "semanticId": {
      "type": "ExternalReference",
      "keys": [{"type": "GlobalReference", "value": "https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2"}]
    },
    "submodelElements": [
      {
        "modelType": "Property",
        "idShort": "MaxPayload",
        "valueType": "xs:double",
        "value": "16.0"
      },
      {
        "modelType": "Property",
        "idShort": "ReachRadius",
        "valueType": "xs:double",
        "value": "1611.0"
      }
    ]
  }'
```

---

### 3. Fast Path: Stream Bytes Directly (No Modifiers)

**Claim**: "If no modifiers, stream bytes directly from Redis or Postgres"

```bash
# Calculate base64url encoded ID
ID="urn:titan:aas:robot-arm-001"
B64_ID=$(echo -n "$ID" | base64 | tr '+/' '-_' | tr -d '=')

# Fast path read - returns raw bytes (latency varies by environment)
time curl -s "http://localhost:8080/shells/$B64_ID"
```

**What to look for**: Response time should be low on warm cache, but will vary with
network, hardware, and cache state.

---

### 4. Slow Path: With Projection Modifiers

**Claim**: "If modifiers are requested, route to a slow path projection engine"

```bash
# Get submodel ID encoded
SM_ID="urn:titan:submodel:technical-data-001"
SM_B64=$(echo -n "$SM_ID" | base64 | tr '+/' '-_' | tr -d '=')

# Slow path: Get only the value of a property ($value modifier)
curl -s "http://localhost:8080/submodels/$SM_B64/submodel-elements/MaxPayload/\$value"
# Expected: 16.0

# Slow path: Get metadata only ($metadata modifier)
curl -s "http://localhost:8080/submodels/$SM_B64/submodel-elements/MaxPayload/\$metadata"

# Slow path: Minimal response (level=core)
curl -s "http://localhost:8080/submodels/$SM_B64?level=core"
```

---

### 5. List All Shells and Submodels

```bash
# List all AAS
curl -s http://localhost:8080/shells | jq '.result | length'

# List all Submodels
curl -s http://localhost:8080/submodels | jq '.result | length'

# Filter submodels by semantic ID
curl -s "http://localhost:8080/submodels?semantic_id=https://admin-shell.io/ZVEI/TechnicalData/Submodel/1/2"
```

---

### 6. WebSocket Real-time Events

**Claim**: "WebSocket push for dashboards and HMIs"

```bash
# In terminal 1: Connect to WebSocket (requires wscat)
# npm install -g wscat
wscat -c ws://localhost:8080/ws/events

# In terminal 2: Create a shell to trigger event
curl -X POST http://localhost:8080/shells \
  -H "Content-Type: application/json" \
  -d '{"id": "urn:titan:aas:test-event", "idShort": "EventTest", "assetInformation": {"assetKind": "Instance"}}'
```

**Expected WebSocket output**:
```json
{"eventType": "aas.created", "entityId": "urn:titan:aas:test-event", "timestamp": "..."}
```

---

### 7. Conditional Requests (ETags)

```bash
# Get with ETag
RESPONSE=$(curl -sI "http://localhost:8080/shells/$B64_ID")
ETAG=$(echo "$RESPONSE" | grep -i etag | awk '{print $2}' | tr -d '\r')

# Conditional GET - returns 304 if not modified
curl -s -o /dev/null -w "%{http_code}" \
  -H "If-None-Match: $ETAG" \
  "http://localhost:8080/shells/$B64_ID"
# Expected: 304
```

---

### 8. Explore the OpenAPI Documentation

**Claim**: "Contract-driven REST APIs aligned to normative OpenAPI definitions"

Open in browser: **http://localhost:8080/docs**

You'll see Swagger UI for the implemented endpoints. IDTA coverage is partial and
tracked in the conformance matrix.

---

## 🧹 Cleanup

```bash
# Delete test resources
curl -X DELETE "http://localhost:8080/shells/$B64_ID"
curl -X DELETE "http://localhost:8080/submodels/$SM_B64"

# Stop the stack
docker compose -f deployment/docker-compose.yml down -v
```

---

## 📊 Benchmark: Fast Path vs Slow Path

```bash
# Install hyperfine for benchmarking
# brew install hyperfine

# Fast path (no modifiers)
hyperfine --warmup 10 \
  "curl -s http://localhost:8080/shells/$B64_ID"

# Slow path (with $value modifier)  
hyperfine --warmup 10 \
  "curl -s http://localhost:8080/submodels/$SM_B64/submodel-elements/MaxPayload/\$value"
```

**Expected**: Fast path should be 2-5x faster than slow path.

---

## 🔗 More Resources

- [GitHub Repository](https://github.com/hadijannat/titan-aas)
- [API Documentation](http://localhost:8080/docs)
- [Architecture Overview](docs/architecture.md)
