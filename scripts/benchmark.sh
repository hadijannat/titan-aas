#!/bin/bash
# Titan-AAS Benchmark Script
# Runs load tests and collects performance metrics

set -e

# Configuration
HOST="${TITAN_HOST:-http://localhost:8080}"
USERS="${LOCUST_USERS:-100}"
SPAWN_RATE="${LOCUST_SPAWN_RATE:-10}"
RUN_TIME="${LOCUST_RUN_TIME:-60s}"
OUTPUT_DIR="${OUTPUT_DIR:-./benchmark-results}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Titan-AAS Benchmark ===${NC}"
echo "Host: $HOST"
echo "Users: $USERS"
echo "Spawn rate: $SPAWN_RATE/s"
echo "Duration: $RUN_TIME"
echo ""

# Check if server is running
echo -e "${YELLOW}Checking server availability...${NC}"
if ! curl -s "${HOST}/health" > /dev/null; then
    echo -e "${RED}Error: Server not responding at ${HOST}${NC}"
    echo "Start the server with: titan serve"
    exit 1
fi
echo -e "${GREEN}Server is running${NC}"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Seed some data for read tests
echo -e "${YELLOW}Seeding test data...${NC}"
for i in {1..10}; do
    AAS_ID="urn:benchmark:aas:seed-${i}"
    curl -s -X POST "${HOST}/shells" \
        -H "Content-Type: application/json" \
        -d "{\"modelType\":\"AssetAdministrationShell\",\"id\":\"${AAS_ID}\",\"idShort\":\"SeedAAS${i}\",\"assetInformation\":{\"assetKind\":\"Instance\",\"globalAssetId\":\"urn:benchmark:asset:${i}\"}}" \
        > /dev/null 2>&1 || true

    SM_ID="urn:benchmark:submodel:seed-${i}"
    curl -s -X POST "${HOST}/submodels" \
        -H "Content-Type: application/json" \
        -d "{\"modelType\":\"Submodel\",\"id\":\"${SM_ID}\",\"idShort\":\"SeedSubmodel${i}\",\"submodelElements\":[{\"modelType\":\"Property\",\"idShort\":\"Value\",\"valueType\":\"xs:string\",\"value\":\"benchmark\"}]}" \
        > /dev/null 2>&1 || true
done
echo -e "${GREEN}Seeded 10 AAS and 10 Submodels${NC}"
echo ""

# Run Locust load test
echo -e "${YELLOW}Running Locust load test...${NC}"
echo "Output: ${OUTPUT_DIR}/locust_${TIMESTAMP}"

python -m locust \
    -f tests/load/locustfile.py \
    --host="${HOST}" \
    --headless \
    --users="${USERS}" \
    --spawn-rate="${SPAWN_RATE}" \
    --run-time="${RUN_TIME}" \
    --html="${OUTPUT_DIR}/locust_${TIMESTAMP}.html" \
    --csv="${OUTPUT_DIR}/locust_${TIMESTAMP}" \
    2>&1 | tee "${OUTPUT_DIR}/locust_${TIMESTAMP}.log"

echo ""
echo -e "${GREEN}=== Benchmark Complete ===${NC}"
echo ""

# Parse and display results
if [ -f "${OUTPUT_DIR}/locust_${TIMESTAMP}_stats.csv" ]; then
    echo -e "${YELLOW}Performance Summary:${NC}"
    echo ""

    # Display key metrics using awk
    awk -F',' 'NR>1 {
        if ($1 == "Aggregated") {
            printf "Total Requests: %s\n", $3
            printf "Failures: %s (%.2f%%)\n", $4, ($4/$3)*100
            printf "Avg Response Time: %s ms\n", $6
            printf "Min Response Time: %s ms\n", $7
            printf "Max Response Time: %s ms\n", $8
            printf "Median Response Time: %s ms\n", $9
            printf "RPS: %s\n", $10
        }
    }' "${OUTPUT_DIR}/locust_${TIMESTAMP}_stats.csv"

    echo ""
    echo -e "${YELLOW}Per-Endpoint Results:${NC}"
    awk -F',' 'NR>1 && $1 != "Aggregated" {
        printf "%-40s Avg: %6s ms  RPS: %6s\n", $2, $6, $10
    }' "${OUTPUT_DIR}/locust_${TIMESTAMP}_stats.csv"
fi

echo ""
echo -e "${GREEN}Results saved to: ${OUTPUT_DIR}/${NC}"
echo "  - HTML report: locust_${TIMESTAMP}.html"
echo "  - CSV stats: locust_${TIMESTAMP}_stats.csv"
echo "  - Log: locust_${TIMESTAMP}.log"

# Optional: Run wrk for raw throughput test
if command -v wrk &> /dev/null; then
    echo ""
    echo -e "${YELLOW}Running wrk throughput test (30s)...${NC}"

    # Pick a seeded submodel for raw throughput
    SM_ID="urn:benchmark:submodel:seed-1"
    ENCODED_ID=$(echo -n "$SM_ID" | base64 | tr '+/' '-_' | tr -d '=')

    wrk -t4 -c100 -d30s "${HOST}/submodels/${ENCODED_ID}" \
        | tee "${OUTPUT_DIR}/wrk_${TIMESTAMP}.txt"
fi

echo ""
echo -e "${GREEN}Benchmark finished!${NC}"
