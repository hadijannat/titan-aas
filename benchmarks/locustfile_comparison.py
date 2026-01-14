"""Locust load test for Titan-AAS vs BaSyx Python SDK comparison.

Runs identical workloads against both servers for fair comparison.

Usage:
    # Test Titan-AAS (default)
    locust -f benchmarks/locustfile_comparison.py --host http://localhost:8080

    # Test BaSyx Python SDK
    locust -f benchmarks/locustfile_comparison.py --host http://localhost:8081

    # Headless mode with specific parameters
    locust -f benchmarks/locustfile_comparison.py --headless \
        --host http://localhost:8080 \
        --users 50 --spawn-rate 10 --run-time 60s

    # Compare both (run separately and compare reports)
    locust -f benchmarks/locustfile_comparison.py --host http://localhost:8080 \
        --headless --users 50 --run-time 60s --html benchmarks/results/titan_report.html
    locust -f benchmarks/locustfile_comparison.py --host http://localhost:8081 \
        --headless --users 50 --run-time 60s --html benchmarks/results/basyx_report.html
"""

from __future__ import annotations

import base64
import json
import random
import uuid

from locust import HttpUser, between, events, tag, task


def encode_id(identifier: str) -> str:
    """Encode identifier to Base64URL."""
    encoded = base64.urlsafe_b64encode(identifier.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def create_aas_payload(id_short: str) -> dict:
    """Create a test AAS payload."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "modelType": "AssetAdministrationShell",
        "id": f"urn:benchmark:aas:{id_short}:{unique_id}",
        "idShort": id_short,
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": f"urn:benchmark:asset:{id_short}:{unique_id}",
        },
    }


def create_submodel_payload(id_short: str, num_elements: int = 5) -> dict:
    """Create a test Submodel payload."""
    unique_id = uuid.uuid4().hex[:8]
    elements = [
        {
            "modelType": "Property",
            "idShort": f"Property{i}",
            "valueType": "xs:string",
            "value": f"value_{uuid.uuid4().hex[:4]}",
        }
        for i in range(num_elements)
    ]
    return {
        "modelType": "Submodel",
        "id": f"urn:benchmark:submodel:{id_short}:{unique_id}",
        "idShort": id_short,
        "submodelElements": elements,
    }


class AASBenchmarkUser(HttpUser):
    """Simulates typical AAS API usage patterns.

    Workload distribution (based on real-world industrial usage):
    - 70% reads (list, get by ID)
    - 20% creates
    - 10% updates/deletes
    """

    # Wait 0.5-2 seconds between tasks (simulates real user behavior)
    wait_time = between(0.5, 2)

    # Track created resources for subsequent operations
    created_aas_ids: list[str] = []
    created_submodel_ids: list[str] = []

    def on_start(self) -> None:
        """Initialize user session - create some initial data."""
        # Create a few AAS and Submodels to work with
        for i in range(3):
            aas = create_aas_payload(f"InitAAS{i}")
            resp = self.client.post(
                "/shells",
                json=aas,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 201:
                self.created_aas_ids.append(aas["id"])

            sm = create_submodel_payload(f"InitSM{i}")
            resp = self.client.post(
                "/submodels",
                json=sm,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 201:
                self.created_submodel_ids.append(sm["id"])

    # =========================================================================
    # Read Operations (70% of workload)
    # =========================================================================

    @task(30)
    @tag("read", "list")
    def list_shells(self) -> None:
        """List all AAS (shells)."""
        self.client.get("/shells", name="/shells [LIST]")

    @task(20)
    @tag("read", "get")
    def get_shell_by_id(self) -> None:
        """Get a specific AAS by ID."""
        if not self.created_aas_ids:
            return
        aas_id = random.choice(self.created_aas_ids)  # noqa: S311
        encoded_id = encode_id(aas_id)
        self.client.get(f"/shells/{encoded_id}", name="/shells/{id} [GET]")

    @task(10)
    @tag("read", "list")
    def list_submodels(self) -> None:
        """List all Submodels."""
        self.client.get("/submodels", name="/submodels [LIST]")

    @task(10)
    @tag("read", "get")
    def get_submodel_by_id(self) -> None:
        """Get a specific Submodel by ID."""
        if not self.created_submodel_ids:
            return
        sm_id = random.choice(self.created_submodel_ids)  # noqa: S311
        encoded_id = encode_id(sm_id)
        self.client.get(f"/submodels/{encoded_id}", name="/submodels/{id} [GET]")

    # =========================================================================
    # Create Operations (20% of workload)
    # =========================================================================

    @task(12)
    @tag("write", "create")
    def create_shell(self) -> None:
        """Create a new AAS."""
        aas = create_aas_payload(f"BenchAAS{len(self.created_aas_ids)}")
        with self.client.post(
            "/shells",
            json=aas,
            headers={"Content-Type": "application/json"},
            name="/shells [CREATE]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                self.created_aas_ids.append(aas["id"])
                resp.success()
            elif resp.status_code == 409:  # Conflict - already exists
                resp.success()  # Don't count as failure
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(8)
    @tag("write", "create")
    def create_submodel(self) -> None:
        """Create a new Submodel."""
        sm = create_submodel_payload(f"BenchSM{len(self.created_submodel_ids)}")
        with self.client.post(
            "/submodels",
            json=sm,
            headers={"Content-Type": "application/json"},
            name="/submodels [CREATE]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                self.created_submodel_ids.append(sm["id"])
                resp.success()
            elif resp.status_code == 409:
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    # =========================================================================
    # Update/Delete Operations (10% of workload)
    # =========================================================================

    @task(5)
    @tag("write", "update")
    def update_shell(self) -> None:
        """Update an existing AAS."""
        if not self.created_aas_ids:
            return
        aas_id = random.choice(self.created_aas_ids)  # noqa: S311
        encoded_id = encode_id(aas_id)

        # Get current state
        get_resp = self.client.get(f"/shells/{encoded_id}", name="/shells/{id} [GET for UPDATE]")
        if get_resp.status_code != 200:
            return

        # Update idShort
        aas = get_resp.json()
        aas["idShort"] = f"Updated_{uuid.uuid4().hex[:4]}"

        with self.client.put(
            f"/shells/{encoded_id}",
            json=aas,
            headers={"Content-Type": "application/json"},
            name="/shells/{id} [UPDATE]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 204):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(5)
    @tag("write", "delete")
    def delete_shell(self) -> None:
        """Delete an AAS."""
        if len(self.created_aas_ids) < 5:
            # Keep at least 5 AAS for other operations
            return
        aas_id = self.created_aas_ids.pop()
        encoded_id = encode_id(aas_id)

        with self.client.delete(
            f"/shells/{encoded_id}",
            name="/shells/{id} [DELETE]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 204, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")


class ReadHeavyUser(HttpUser):
    """User that only performs read operations.

    Use this to measure pure read performance without write contention.
    """

    wait_time = between(0.1, 0.5)

    @task(5)
    def list_shells(self) -> None:
        """List all AAS."""
        self.client.get("/shells", name="/shells [READ-ONLY]")

    @task(5)
    def list_submodels(self) -> None:
        """List all Submodels."""
        self.client.get("/submodels", name="/submodels [READ-ONLY]")


# Event hooks for custom reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    """Log test configuration at start."""
    print("\n" + "=" * 60)
    print("Benchmark Configuration")
    print("=" * 60)
    print(f"Target: {environment.host}")
    print(f"Users: {environment.parsed_options.num_users}")
    print(f"Spawn Rate: {environment.parsed_options.spawn_rate}")
    print(f"Run Time: {environment.parsed_options.run_time}")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:
    """Print summary at end of test."""
    stats = environment.stats
    print("\n" + "=" * 60)
    print("Benchmark Summary")
    print("=" * 60)
    print(f"Total Requests: {stats.total.num_requests}")
    print(f"Total Failures: {stats.total.num_failures}")
    print(f"Failure Rate: {stats.total.fail_ratio * 100:.2f}%")
    print(f"Avg Response Time: {stats.total.avg_response_time:.2f}ms")
    print(f"Requests/sec: {stats.total.total_rps:.2f}")
    print("=" * 60 + "\n")


# Optionally export results to JSON
@events.quitting.add_listener
def on_quitting(environment, **kwargs) -> None:
    """Export results to JSON file."""
    if not environment.parsed_options.html:
        return

    stats = environment.stats
    results = {
        "host": environment.host,
        "total_requests": stats.total.num_requests,
        "total_failures": stats.total.num_failures,
        "fail_ratio": stats.total.fail_ratio,
        "avg_response_time_ms": stats.total.avg_response_time,
        "median_response_time_ms": stats.total.median_response_time,
        "requests_per_second": stats.total.total_rps,
        "endpoints": {},
    }

    for entry in stats.entries.values():
        results["endpoints"][entry.name] = {
            "requests": entry.num_requests,
            "failures": entry.num_failures,
            "avg_response_time_ms": entry.avg_response_time,
            "median_response_time_ms": entry.median_response_time,
            "p95_response_time_ms": entry.get_response_time_percentile(0.95),
            "p99_response_time_ms": entry.get_response_time_percentile(0.99),
        }

    # Save JSON alongside HTML report
    json_path = environment.parsed_options.html.replace(".html", ".json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results exported to: {json_path}")
