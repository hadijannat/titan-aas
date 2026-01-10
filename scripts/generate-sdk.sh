#!/usr/bin/env bash
#
# Generate SDK clients from OpenAPI specification
#
# Usage:
#   ./scripts/generate-sdk.sh [options]
#
# Options:
#   --python      Generate Python SDK only
#   --typescript  Generate TypeScript SDK only
#   --all         Generate all SDKs (default)
#   --server URL  API server URL (default: http://localhost:8080)
#   --output DIR  Output directory (default: ./sdk)
#   --clean       Remove existing SDK directories before generation
#
# Requirements:
#   - Java 11+ (for openapi-generator-cli)
#   - npm (for installing openapi-generator-cli)
#   - Running Titan-AAS server (or OpenAPI spec file)
#
# Examples:
#   # Generate all SDKs from running server
#   ./scripts/generate-sdk.sh --all
#
#   # Generate Python SDK from specific server
#   ./scripts/generate-sdk.sh --python --server https://aas.example.com
#
#   # Generate from local spec file
#   OPENAPI_SPEC=./openapi.json ./scripts/generate-sdk.sh --all
#

set -euo pipefail

# Default configuration
SERVER_URL="${SERVER_URL:-http://localhost:8080}"
OUTPUT_DIR="${OUTPUT_DIR:-./sdk}"
OPENAPI_SPEC="${OPENAPI_SPEC:-}"
GENERATE_PYTHON=false
GENERATE_TYPESCRIPT=false
CLEAN_FIRST=false

# SDK version (matches Titan-AAS version)
SDK_VERSION="0.1.0"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --python)
            GENERATE_PYTHON=true
            shift
            ;;
        --typescript)
            GENERATE_TYPESCRIPT=true
            shift
            ;;
        --all)
            GENERATE_PYTHON=true
            GENERATE_TYPESCRIPT=true
            shift
            ;;
        --server)
            SERVER_URL="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --clean)
            CLEAN_FIRST=true
            shift
            ;;
        --help|-h)
            head -35 "$0" | tail -32
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Default to generating all if none specified
if [[ "$GENERATE_PYTHON" == "false" && "$GENERATE_TYPESCRIPT" == "false" ]]; then
    GENERATE_PYTHON=true
    GENERATE_TYPESCRIPT=true
fi

# Check for openapi-generator-cli
check_generator() {
    if ! command -v openapi-generator-cli &> /dev/null; then
        log_warn "openapi-generator-cli not found, installing via npm..."
        npm install -g @openapitools/openapi-generator-cli
    fi
}

# Get OpenAPI spec (from file or server)
get_openapi_spec() {
    local spec_file="${OUTPUT_DIR}/openapi.json"
    mkdir -p "${OUTPUT_DIR}"

    if [[ -n "$OPENAPI_SPEC" && -f "$OPENAPI_SPEC" ]]; then
        log_info "Using OpenAPI spec from file: $OPENAPI_SPEC"
        cp "$OPENAPI_SPEC" "$spec_file"
    else
        log_info "Fetching OpenAPI spec from: ${SERVER_URL}/openapi.json"
        if ! curl -sf "${SERVER_URL}/openapi.json" -o "$spec_file"; then
            log_error "Failed to fetch OpenAPI spec from ${SERVER_URL}/openapi.json"
            log_error "Make sure the Titan-AAS server is running or provide OPENAPI_SPEC path"
            exit 1
        fi
    fi

    echo "$spec_file"
}

# Generate Python SDK
generate_python() {
    local spec_file="$1"
    local python_dir="${OUTPUT_DIR}/python"

    log_info "Generating Python SDK..."

    if [[ "$CLEAN_FIRST" == "true" && -d "$python_dir" ]]; then
        log_info "Cleaning existing Python SDK..."
        rm -rf "$python_dir"
    fi

    openapi-generator-cli generate \
        -i "$spec_file" \
        -g python \
        -o "$python_dir" \
        --additional-properties=packageName=titan_client \
        --additional-properties=projectName=titan-aas-client \
        --additional-properties=packageVersion="${SDK_VERSION}" \
        --additional-properties=generateSourceCodeOnly=false \
        --additional-properties=library=urllib3

    # Create a simple README
    cat > "${python_dir}/README.md" << 'EOF'
# Titan-AAS Python Client

Python SDK for the Titan-AAS (Asset Administration Shell) API.

## Installation

```bash
pip install ./sdk/python
# or
pip install -e ./sdk/python  # Editable install for development
```

## Usage

```python
from titan_client import ApiClient, Configuration
from titan_client.api import AssetAdministrationShellRepositoryApiApi

# Configure the client
config = Configuration(host="http://localhost:8080")

# Create API client
with ApiClient(config) as client:
    api = AssetAdministrationShellRepositoryApiApi(client)

    # List all shells
    shells = api.get_all_asset_administration_shells()
    for shell in shells:
        print(f"Shell: {shell.id_short}")

    # Get a specific shell by ID (base64url encoded)
    shell = api.get_asset_administration_shell_by_id("encoded-id")
```

## API Documentation

See the Titan-AAS API documentation at `/docs` or `/redoc` on your server.

## Generated

This SDK was auto-generated using [OpenAPI Generator](https://openapi-generator.tech).
EOF

    log_info "Python SDK generated at: ${python_dir}"
}

# Generate TypeScript SDK
generate_typescript() {
    local spec_file="$1"
    local ts_dir="${OUTPUT_DIR}/typescript"

    log_info "Generating TypeScript SDK..."

    if [[ "$CLEAN_FIRST" == "true" && -d "$ts_dir" ]]; then
        log_info "Cleaning existing TypeScript SDK..."
        rm -rf "$ts_dir"
    fi

    openapi-generator-cli generate \
        -i "$spec_file" \
        -g typescript-fetch \
        -o "$ts_dir" \
        --additional-properties=npmName=titan-aas-client \
        --additional-properties=npmVersion="${SDK_VERSION}" \
        --additional-properties=supportsES6=true \
        --additional-properties=typescriptThreePlus=true

    # Create a simple README
    cat > "${ts_dir}/README.md" << 'EOF'
# Titan-AAS TypeScript Client

TypeScript/JavaScript SDK for the Titan-AAS (Asset Administration Shell) API.

## Installation

```bash
npm install ./sdk/typescript
# or
yarn add ./sdk/typescript
```

## Usage

```typescript
import { Configuration, AssetAdministrationShellRepositoryApiApi } from 'titan-aas-client';

// Configure the client
const config = new Configuration({
  basePath: 'http://localhost:8080',
});

// Create API client
const api = new AssetAdministrationShellRepositoryApiApi(config);

// List all shells
async function listShells() {
  const shells = await api.getAllAssetAdministrationShells();
  shells.forEach(shell => {
    console.log(`Shell: ${shell.idShort}`);
  });
}

// Get a specific shell by ID (base64url encoded)
async function getShell(encodedId: string) {
  const shell = await api.getAssetAdministrationShellById({ aasIdentifier: encodedId });
  console.log(shell);
}
```

## API Documentation

See the Titan-AAS API documentation at `/docs` or `/redoc` on your server.

## Generated

This SDK was auto-generated using [OpenAPI Generator](https://openapi-generator.tech).
EOF

    log_info "TypeScript SDK generated at: ${ts_dir}"
}

# Main execution
main() {
    log_info "Titan-AAS SDK Generator"
    log_info "======================"

    check_generator

    local spec_file
    spec_file=$(get_openapi_spec)

    if [[ "$GENERATE_PYTHON" == "true" ]]; then
        generate_python "$spec_file"
    fi

    if [[ "$GENERATE_TYPESCRIPT" == "true" ]]; then
        generate_typescript "$spec_file"
    fi

    log_info "SDK generation complete!"
    log_info "Generated SDKs are in: ${OUTPUT_DIR}"
}

main "$@"
