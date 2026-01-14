"""Load testing for Titan-AAS using Locust.

Usage:
    # Run with web UI
    locust -f tests/load/locustfile.py

    # Run headless
    locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 1m

    # Run with custom host
    locust -f tests/load/locustfile.py --host http://localhost:8080

    # Run with 15K RPS validation
    locust -f tests/load/locustfile.py --headless -u 500 -r 50 -t 5m

Scenarios:
- ReadOnlyUser: 80% read, 20% list operations
- WriteUser: Mix of CRUD operations
- CacheTestUser: Repeated reads to test cache performance

Performance Targets (15K+ RPS):
- p50 latency: < 10ms
- p99 latency: < 100ms
- Error rate: < 0.1%
"""

from __future__ import annotations

import base64
import os
import random
import string
from typing import Any

from locust import HttpUser, between, events, task

# Performance thresholds for validation
# Can be overridden via environment variables
THRESHOLDS = {
    "p99_ms": float(os.getenv("LOAD_TEST_P99_MS", "100")),
    "max_error_rate": float(os.getenv("LOAD_TEST_MAX_ERROR_RATE", "0.001")),
    "min_rps": float(os.getenv("LOAD_TEST_MIN_RPS", "0")),  # 0 = disabled
}


def load_auth_headers() -> dict[str, str]:
    """Return Authorization headers for load tests when a token is provided."""
    token = os.getenv("LOAD_TEST_TOKEN", "").strip()
    if not token:
        return {}
    if not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    return {"Authorization": token}


@events.quitting.add_listener
def check_thresholds(environment: Any, **kwargs: Any) -> None:
    """Validate performance against 15K RPS targets on test completion.

    This listener runs when the load test finishes and validates that
    performance metrics meet the defined thresholds. If validation fails,
    the process exits with code 1 for CI integration.
    """
    if environment.stats.total.num_requests == 0:
        print("WARNING: No requests were made during the test")
        return

    stats = environment.stats.total
    errors_found = False

    # Check error rate
    error_rate = stats.fail_ratio
    if error_rate > THRESHOLDS["max_error_rate"]:
        print(f"FAIL: Error rate {error_rate:.2%} > {THRESHOLDS['max_error_rate']:.2%}")
        errors_found = True
    else:
        print(f"PASS: Error rate {error_rate:.2%} <= {THRESHOLDS['max_error_rate']:.2%}")

    # Check p99 latency
    p99 = stats.get_response_time_percentile(0.99) or 0
    if p99 > THRESHOLDS["p99_ms"]:
        print(f"FAIL: p99 latency {p99:.1f}ms > {THRESHOLDS['p99_ms']:.1f}ms")
        errors_found = True
    else:
        print(f"PASS: p99 latency {p99:.1f}ms <= {THRESHOLDS['p99_ms']:.1f}ms")

    # Check minimum RPS (if configured)
    if THRESHOLDS["min_rps"] > 0:
        rps = stats.total_rps
        if rps < THRESHOLDS["min_rps"]:
            print(f"FAIL: RPS {rps:.1f} < {THRESHOLDS['min_rps']:.1f}")
            errors_found = True
        else:
            print(f"PASS: RPS {rps:.1f} >= {THRESHOLDS['min_rps']:.1f}")

    # Print summary
    print("\nSummary:")
    print(f"  Total requests: {stats.num_requests}")
    print(f"  Total failures: {stats.num_failures}")
    print(f"  Median response time: {stats.median_response_time:.1f}ms")
    print(f"  Average response time: {stats.avg_response_time:.1f}ms")
    print(f"  p95 response time: {stats.get_response_time_percentile(0.95):.1f}ms")
    print(f"  p99 response time: {p99:.1f}ms")
    print(f"  Requests/sec: {stats.total_rps:.1f}")

    if errors_found:
        print("\nLoad test FAILED - performance thresholds not met")
        environment.process_exit_code = 1
    else:
        print("\nLoad test PASSED - all thresholds met")


def generate_id() -> str:
    """Generate a random identifier."""
    return "urn:example:aas:" + "".join(random.choices(string.ascii_lowercase, k=8))


def encode_id(identifier: str) -> str:
    """Base64URL encode an identifier."""
    return base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")


def create_aas_payload(identifier: str | None = None) -> dict[str, Any]:
    """Create a minimal AAS payload."""
    identifier = identifier or generate_id()
    return {
        "modelType": "AssetAdministrationShell",
        "id": identifier,
        "idShort": f"AAS_{identifier[-8:]}",
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": f"urn:example:asset:{identifier[-8:]}",
        },
    }


def create_submodel_payload(identifier: str | None = None) -> dict[str, Any]:
    """Create a minimal Submodel payload."""
    identifier = identifier or generate_id()
    return {
        "modelType": "Submodel",
        "id": identifier,
        "idShort": f"SM_{identifier[-8:]}",
        "submodelElements": [
            {
                "modelType": "Property",
                "idShort": "TestProperty",
                "valueType": "xs:string",
                "value": "test_value",
            },
            {
                "modelType": "Property",
                "idShort": "Counter",
                "valueType": "xs:integer",
                "value": str(random.randint(0, 1000)),
            },
        ],
    }


class AuthenticatedUser(HttpUser):
    """Base user that optionally applies auth headers for load testing."""

    abstract = True

    def on_start(self) -> None:
        headers = load_auth_headers()
        if headers:
            self.client.headers.update(headers)


class ReadOnlyUser(AuthenticatedUser):
    """User that performs read-only operations.

    Simulates typical API consumers that mostly read data.
    """

    wait_time = between(0.1, 0.5)  # Fast reads
    weight = 8  # 80% of users

    # Store IDs for subsequent reads
    known_aas_ids: list[str] = []
    known_submodel_ids: list[str] = []

    @task(5)
    def list_shells(self) -> None:
        """List all shells."""
        with self.client.get(
            "/shells",
            name="/shells (list)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # Remember IDs for subsequent reads
                for item in data.get("result", [])[:10]:
                    if item.get("id") and item["id"] not in self.known_aas_ids:
                        self.known_aas_ids.append(item["id"])
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @task(5)
    def list_submodels(self) -> None:
        """List all submodels."""
        with self.client.get(
            "/submodels",
            name="/submodels (list)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                for item in data.get("result", [])[:10]:
                    if item.get("id") and item["id"] not in self.known_submodel_ids:
                        self.known_submodel_ids.append(item["id"])
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @task(10)
    def get_shell(self) -> None:
        """Get a specific shell."""
        if not self.known_aas_ids:
            return  # Need to list first

        aas_id = random.choice(self.known_aas_ids)
        encoded_id = encode_id(aas_id)

        with self.client.get(
            f"/shells/{encoded_id}",
            name="/shells/{id} (get)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Remove from known list
                if aas_id in self.known_aas_ids:
                    self.known_aas_ids.remove(aas_id)
                response.success()  # Expected if deleted
            else:
                response.failure(f"Status {response.status_code}")

    @task(10)
    def get_submodel(self) -> None:
        """Get a specific submodel."""
        if not self.known_submodel_ids:
            return

        sm_id = random.choice(self.known_submodel_ids)
        encoded_id = encode_id(sm_id)

        with self.client.get(
            f"/submodels/{encoded_id}",
            name="/submodels/{id} (get)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                if sm_id in self.known_submodel_ids:
                    self.known_submodel_ids.remove(sm_id)
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @task(3)
    def get_submodel_value(self) -> None:
        """Get submodel with $value modifier."""
        if not self.known_submodel_ids:
            return

        sm_id = random.choice(self.known_submodel_ids)
        encoded_id = encode_id(sm_id)

        self.client.get(
            f"/submodels/{encoded_id}/$value",
            name="/submodels/{id}/$value",
        )


class WriteUser(AuthenticatedUser):
    """User that performs write operations.

    Simulates applications that create and update data.
    """

    wait_time = between(0.5, 2)  # Slower writes
    weight = 2  # 20% of users

    created_aas_ids: list[str] = []
    created_submodel_ids: list[str] = []

    @task(3)
    def create_shell(self) -> None:
        """Create a new shell."""
        payload = create_aas_payload()

        with self.client.post(
            "/shells",
            json=payload,
            name="/shells (create)",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.created_aas_ids.append(payload["id"])
                response.success()
            elif response.status_code == 409:
                response.success()  # Already exists
            else:
                response.failure(f"Status {response.status_code}: {response.text}")

    @task(3)
    def create_submodel(self) -> None:
        """Create a new submodel."""
        payload = create_submodel_payload()

        with self.client.post(
            "/submodels",
            json=payload,
            name="/submodels (create)",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                self.created_submodel_ids.append(payload["id"])
                response.success()
            elif response.status_code == 409:
                response.success()
            else:
                response.failure(f"Status {response.status_code}: {response.text}")

    @task(2)
    def update_shell(self) -> None:
        """Update an existing shell."""
        if not self.created_aas_ids:
            return

        aas_id = random.choice(self.created_aas_ids)
        encoded_id = encode_id(aas_id)
        payload = create_aas_payload(aas_id)

        with self.client.put(
            f"/shells/{encoded_id}",
            json=payload,
            name="/shells/{id} (update)",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 204):
                response.success()
            elif response.status_code == 404:
                if aas_id in self.created_aas_ids:
                    self.created_aas_ids.remove(aas_id)
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @task(2)
    def update_submodel(self) -> None:
        """Update an existing submodel."""
        if not self.created_submodel_ids:
            return

        sm_id = random.choice(self.created_submodel_ids)
        encoded_id = encode_id(sm_id)
        payload = create_submodel_payload(sm_id)

        with self.client.put(
            f"/submodels/{encoded_id}",
            json=payload,
            name="/submodels/{id} (update)",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 204):
                response.success()
            elif response.status_code == 404:
                if sm_id in self.created_submodel_ids:
                    self.created_submodel_ids.remove(sm_id)
                response.success()
            else:
                response.failure(f"Status {response.status_code}")

    @task(1)
    def delete_shell(self) -> None:
        """Delete a shell."""
        if not self.created_aas_ids:
            return

        aas_id = self.created_aas_ids.pop()
        encoded_id = encode_id(aas_id)

        with self.client.delete(
            f"/shells/{encoded_id}",
            name="/shells/{id} (delete)",
            catch_response=True,
        ) as response:
            if response.status_code in (200, 204, 404):
                response.success()
            else:
                response.failure(f"Status {response.status_code}")


class CacheTestUser(AuthenticatedUser):
    """User that tests cache performance.

    Repeatedly reads the same resources to measure cache hit performance.
    """

    wait_time = between(0.01, 0.05)  # Very fast reads
    weight = 1  # Small percentage

    target_id: str | None = None

    def on_start(self) -> None:
        """Initialize with a target ID."""
        super().on_start()
        # Create a resource to read repeatedly
        payload = create_submodel_payload()
        response = self.client.post("/submodels", json=payload)
        if response.status_code == 201:
            self.target_id = payload["id"]

    @task
    def cache_read(self) -> None:
        """Repeatedly read the same resource."""
        if not self.target_id:
            return

        encoded_id = encode_id(self.target_id)
        self.client.get(
            f"/submodels/{encoded_id}",
            name="/submodels/{id} (cache test)",
        )

    def on_stop(self) -> None:
        """Clean up."""
        if self.target_id:
            encoded_id = encode_id(self.target_id)
            self.client.delete(f"/submodels/{encoded_id}")
