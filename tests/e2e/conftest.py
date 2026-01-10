"""E2E test fixtures using Docker Compose."""

import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Generator

import httpx
import pytest

# Path to deployment directory
DEPLOYMENT_DIR = Path(__file__).parent.parent.parent / "deployment"
COMPOSE_FILE = DEPLOYMENT_DIR / "docker-compose.yml"

# Base URL for the API
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8080")

# Timeout for waiting for services
STARTUP_TIMEOUT = 120  # seconds


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def docker_compose_up() -> Generator[None, None, None]:
    """Start Docker Compose stack for E2E tests.

    This fixture is session-scoped, so the stack is started once
    for all tests and torn down at the end.
    """
    # Check if we should use existing stack (for CI or local development)
    if os.environ.get("E2E_USE_EXISTING_STACK"):
        yield
        return

    compose_env = os.environ.copy()
    if "MOSQUITTO_PORT" not in compose_env and not _is_port_available(1883):
        fallback_port = _pick_free_port()
        compose_env["MOSQUITTO_PORT"] = str(fallback_port)
        print(f"⚠️  Port 1883 in use; using MOSQUITTO_PORT={fallback_port} for E2E stack.")

    # Start Docker Compose
    print(f"\n📦 Starting Docker Compose stack from {COMPOSE_FILE}...")
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--build"],
        check=True,
        capture_output=True,
        env=compose_env,
    )

    # Wait for services to be ready
    start_time = time.time()
    while time.time() - start_time < STARTUP_TIMEOUT:
        try:
            response = httpx.get(f"{BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                health = response.json()
                if health.get("status") == "healthy":
                    print("✅ Stack is healthy!")
                    break
        except Exception:
            pass
        time.sleep(2)
        print("⏳ Waiting for stack to be ready...")
    else:
        # Timeout - get logs and fail
        logs = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "logs", "--tail=50"],
            capture_output=True,
            text=True,
            env=compose_env,
        )
        pytest.fail(
            f"Stack failed to start in {STARTUP_TIMEOUT}s.\nLogs:\n{logs.stdout}\n{logs.stderr}"
        )

    yield

    # Cleanup
    print("\n🧹 Stopping Docker Compose stack...")
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"],
        check=True,
        capture_output=True,
        env=compose_env,
    )


@pytest.fixture
def client(docker_compose_up: None) -> httpx.Client:
    """HTTP client for API requests."""
    return httpx.Client(base_url=BASE_URL, timeout=30)


@pytest.fixture
def async_client(docker_compose_up: None) -> httpx.AsyncClient:
    """Async HTTP client for API requests."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=30)


@pytest.fixture
def sample_aas() -> dict:
    """Sample Asset Administration Shell for testing."""
    return {
        "modelType": "AssetAdministrationShell",
        "id": "urn:example:aas:e2e-test-1",
        "idShort": "E2ETestAAS",
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": "urn:example:asset:e2e-test-1",
        },
        "description": [
            {"language": "en", "text": "E2E Test AAS"},
        ],
    }


@pytest.fixture
def sample_submodel() -> dict:
    """Sample Submodel for testing."""
    return {
        "modelType": "Submodel",
        "id": "urn:example:submodel:e2e-test-1",
        "idShort": "E2ETestSubmodel",
        "semanticId": {
            "type": "ExternalReference",
            "keys": [
                {
                    "type": "GlobalReference",
                    "value": "urn:example:semantic:e2e-test",
                }
            ],
        },
        "submodelElements": [
            {
                "modelType": "Property",
                "idShort": "Temperature",
                "valueType": "xs:double",
                "value": "25.5",
            },
            {
                "modelType": "Property",
                "idShort": "Status",
                "valueType": "xs:string",
                "value": "active",
            },
            {
                "modelType": "SubmodelElementCollection",
                "idShort": "Metadata",
                "value": [
                    {
                        "modelType": "Property",
                        "idShort": "Version",
                        "valueType": "xs:string",
                        "value": "1.0.0",
                    },
                ],
            },
        ],
    }


@pytest.fixture
def base64url_encode():
    """Helper to Base64URL encode identifiers."""
    import base64

    def encode(identifier: str) -> str:
        return base64.urlsafe_b64encode(identifier.encode()).rstrip(b"=").decode()

    return encode
