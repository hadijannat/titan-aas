#!/usr/bin/env python3
"""Functional validation tests for Titan-AAS and BaSyx Python SDK.

Proves both implementations work correctly by running identical CRUD operations
and verifying data integrity.

Usage:
    python benchmarks/functional_tests.py                    # Test both servers
    python benchmarks/functional_tests.py --target titan     # Test Titan only
    python benchmarks/functional_tests.py --target basyx     # Test BaSyx only
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ServerConfig:
    """Server configuration for testing."""

    name: str
    base_url: str
    shells_path: str
    submodels_path: str
    timeout: float = 30.0


@dataclass
class TestResult:
    """Result of a single test."""

    name: str
    passed: bool
    duration_ms: float
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestSuite:
    """Collection of test results."""

    server: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        return (self.passed / self.total * 100) if self.total > 0 else 0.0


# Server configurations
TITAN_CONFIG = ServerConfig(
    name="Titan-AAS",
    base_url="http://localhost:8080",
    shells_path="/shells",
    submodels_path="/submodels",
)

BASYX_CONFIG = ServerConfig(
    name="BaSyx Python SDK",
    base_url="http://localhost:8081",
    shells_path="/shells",
    submodels_path="/submodels",
)


def encode_id(identifier: str) -> str:
    """Encode identifier to Base64URL for URL paths."""
    encoded = base64.urlsafe_b64encode(identifier.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def create_test_aas(id_short: str) -> dict[str, Any]:
    """Create a test AAS payload."""
    aas_id = f"urn:example:aas:{id_short}:{uuid.uuid4().hex[:8]}"
    asset_id = f"urn:example:asset:{id_short}:{uuid.uuid4().hex[:8]}"
    return {
        "modelType": "AssetAdministrationShell",
        "id": aas_id,
        "idShort": id_short,
        "assetInformation": {
            "assetKind": "Instance",
            "globalAssetId": asset_id,
        },
    }


def create_test_submodel(id_short: str, num_properties: int = 5) -> dict[str, Any]:
    """Create a test Submodel payload with properties."""
    sm_id = f"urn:example:submodel:{id_short}:{uuid.uuid4().hex[:8]}"
    elements = []
    for i in range(num_properties):
        elements.append(
            {
                "modelType": "Property",
                "idShort": f"Property{i}",
                "valueType": "xs:string",
                "value": f"value_{i}_{uuid.uuid4().hex[:4]}",
            }
        )
    return {
        "modelType": "Submodel",
        "id": sm_id,
        "idShort": id_short,
        "submodelElements": elements,
    }


class FunctionalTester:
    """Runs functional tests against an AAS server."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.client = httpx.Client(base_url=config.base_url, timeout=config.timeout)
        self.suite = TestSuite(server=config.name)

    def close(self) -> None:
        self.client.close()

    def run_test(self, name: str, test_func: callable) -> TestResult:
        """Run a single test and record the result."""
        start = time.perf_counter()
        try:
            details = test_func()
            duration_ms = (time.perf_counter() - start) * 1000
            result = TestResult(
                name=name,
                passed=True,
                duration_ms=duration_ms,
                details=details or {},
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            result = TestResult(
                name=name,
                passed=False,
                duration_ms=duration_ms,
                error=str(e),
            )
        self.suite.results.append(result)
        return result

    def check_server_health(self) -> bool:
        """Check if the server is reachable."""
        try:
            # Try shells endpoint as health check
            resp = self.client.get(self.config.shells_path)
            return resp.status_code in (200, 404)  # 404 is OK if no shells exist
        except Exception:
            return False

    # =========================================================================
    # AAS (Shell) Tests
    # =========================================================================

    def test_create_aas(self) -> dict[str, Any]:
        """Test creating an AAS."""
        aas = create_test_aas("TestShell")
        resp = self.client.post(
            self.config.shells_path,
            json=aas,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        return {"aas_id": aas["id"], "status_code": resp.status_code}

    def test_get_aas(self) -> dict[str, Any]:
        """Test retrieving an AAS."""
        # Create first
        aas = create_test_aas("GetTest")
        create_resp = self.client.post(
            self.config.shells_path,
            json=aas,
            headers={"Content-Type": "application/json"},
        )
        assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"

        # Then retrieve
        encoded_id = encode_id(aas["id"])
        get_resp = self.client.get(f"{self.config.shells_path}/{encoded_id}")
        assert get_resp.status_code == 200, f"Get failed: {get_resp.status_code}: {get_resp.text}"

        retrieved = get_resp.json()
        assert retrieved["id"] == aas["id"], "ID mismatch"
        assert retrieved["idShort"] == aas["idShort"], "idShort mismatch"

        return {"aas_id": aas["id"], "data_matches": True}

    def test_list_aas(self) -> dict[str, Any]:
        """Test listing AAS with pagination."""
        # Create a few AAS first
        for i in range(3):
            aas = create_test_aas(f"ListTest{i}")
            resp = self.client.post(
                self.config.shells_path,
                json=aas,
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 201

        # List all
        list_resp = self.client.get(self.config.shells_path)
        assert list_resp.status_code == 200, f"List failed: {list_resp.status_code}"

        data = list_resp.json()
        # Both servers should return a list or paged result
        if isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict) and "result" in data:
            count = len(data["result"])
        else:
            count = 0

        assert count >= 3, f"Expected at least 3 AAS, got {count}"
        return {"count": count}

    def test_update_aas(self) -> dict[str, Any]:
        """Test updating an AAS."""
        # Create
        aas = create_test_aas("UpdateTest")
        create_resp = self.client.post(
            self.config.shells_path,
            json=aas,
            headers={"Content-Type": "application/json"},
        )
        assert create_resp.status_code == 201

        # Update
        aas["idShort"] = "UpdatedShell"
        encoded_id = encode_id(aas["id"])
        update_resp = self.client.put(
            f"{self.config.shells_path}/{encoded_id}",
            json=aas,
            headers={"Content-Type": "application/json"},
        )
        assert update_resp.status_code in (
            200,
            204,
        ), f"Update failed: {update_resp.status_code}: {update_resp.text}"

        # Verify update persisted
        get_resp = self.client.get(f"{self.config.shells_path}/{encoded_id}")
        assert get_resp.status_code == 200
        retrieved = get_resp.json()
        assert retrieved["idShort"] == "UpdatedShell", "Update not persisted"

        return {"aas_id": aas["id"], "update_persisted": True}

    def test_delete_aas(self) -> dict[str, Any]:
        """Test deleting an AAS."""
        # Create
        aas = create_test_aas("DeleteTest")
        create_resp = self.client.post(
            self.config.shells_path,
            json=aas,
            headers={"Content-Type": "application/json"},
        )
        assert create_resp.status_code == 201

        # Delete
        encoded_id = encode_id(aas["id"])
        delete_resp = self.client.delete(f"{self.config.shells_path}/{encoded_id}")
        assert delete_resp.status_code in (
            200,
            204,
        ), f"Delete failed: {delete_resp.status_code}"

        # Verify deleted
        get_resp = self.client.get(f"{self.config.shells_path}/{encoded_id}")
        assert get_resp.status_code == 404, f"Expected 404, got {get_resp.status_code}"

        return {"aas_id": aas["id"], "deleted": True}

    # =========================================================================
    # Submodel Tests
    # =========================================================================

    def test_create_submodel(self) -> dict[str, Any]:
        """Test creating a Submodel."""
        sm = create_test_submodel("TestSubmodel", num_properties=5)
        resp = self.client.post(
            self.config.submodels_path,
            json=sm,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        return {"submodel_id": sm["id"], "status_code": resp.status_code}

    def test_get_submodel(self) -> dict[str, Any]:
        """Test retrieving a Submodel."""
        # Create
        sm = create_test_submodel("GetSubmodelTest", num_properties=3)
        create_resp = self.client.post(
            self.config.submodels_path,
            json=sm,
            headers={"Content-Type": "application/json"},
        )
        assert create_resp.status_code == 201

        # Retrieve
        encoded_id = encode_id(sm["id"])
        get_resp = self.client.get(f"{self.config.submodels_path}/{encoded_id}")
        assert get_resp.status_code == 200, f"Get failed: {get_resp.status_code}"

        retrieved = get_resp.json()
        assert retrieved["id"] == sm["id"], "ID mismatch"
        assert len(retrieved.get("submodelElements", [])) == 3, "Element count mismatch"

        return {"submodel_id": sm["id"], "data_matches": True}

    def test_list_submodels(self) -> dict[str, Any]:
        """Test listing Submodels."""
        # Create a few
        for i in range(3):
            sm = create_test_submodel(f"ListSubmodel{i}")
            resp = self.client.post(
                self.config.submodels_path,
                json=sm,
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 201

        # List
        list_resp = self.client.get(self.config.submodels_path)
        assert list_resp.status_code == 200

        data = list_resp.json()
        if isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict) and "result" in data:
            count = len(data["result"])
        else:
            count = 0

        assert count >= 3, f"Expected at least 3 Submodels, got {count}"
        return {"count": count}

    # =========================================================================
    # Data Integrity Tests
    # =========================================================================

    def test_roundtrip_integrity(self) -> dict[str, Any]:
        """Test that created data can be retrieved exactly."""
        # Create AAS with specific data
        aas = create_test_aas("IntegrityTest")
        aas["description"] = [{"language": "en", "text": "Test description for integrity"}]

        create_resp = self.client.post(
            self.config.shells_path,
            json=aas,
            headers={"Content-Type": "application/json"},
        )
        assert create_resp.status_code == 201

        # Retrieve and compare
        encoded_id = encode_id(aas["id"])
        get_resp = self.client.get(f"{self.config.shells_path}/{encoded_id}")
        assert get_resp.status_code == 200

        retrieved = get_resp.json()
        assert retrieved["id"] == aas["id"]
        assert retrieved["idShort"] == aas["idShort"]
        assert (
            retrieved["assetInformation"]["globalAssetId"]
            == aas["assetInformation"]["globalAssetId"]
        )

        return {"integrity_verified": True}

    def run_all_tests(self) -> TestSuite:
        """Run all functional tests."""
        print(f"\n{'=' * 60}")
        print(f"Testing: {self.config.name}")
        print(f"Base URL: {self.config.base_url}")
        print(f"{'=' * 60}\n")

        # Check server health first
        if not self.check_server_health():
            print(f"ERROR: Server {self.config.name} is not reachable!")
            self.suite.results.append(
                TestResult(
                    name="Server Health Check",
                    passed=False,
                    duration_ms=0,
                    error=f"Server at {self.config.base_url} is not reachable",
                )
            )
            return self.suite

        tests = [
            ("Create AAS", self.test_create_aas),
            ("Get AAS", self.test_get_aas),
            ("List AAS", self.test_list_aas),
            ("Update AAS", self.test_update_aas),
            ("Delete AAS", self.test_delete_aas),
            ("Create Submodel", self.test_create_submodel),
            ("Get Submodel", self.test_get_submodel),
            ("List Submodels", self.test_list_submodels),
            ("Roundtrip Integrity", self.test_roundtrip_integrity),
        ]

        for name, test_func in tests:
            result = self.run_test(name, test_func)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {name} ({result.duration_ms:.1f}ms)")
            if result.error:
                print(f"        Error: {result.error}")

        return self.suite


def print_summary(suites: list[TestSuite]) -> None:
    """Print summary of all test suites."""
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}\n")

    for suite in suites:
        status = "PASS" if suite.failed == 0 else "FAIL"
        print(f"{suite.server}:")
        print(f"  Passed: {suite.passed}/{suite.total} ({suite.success_rate:.1f}%)")
        print(f"  Status: [{status}]")
        print()


def export_results(suites: list[TestSuite], output_path: str) -> None:
    """Export results to JSON file."""
    results = {}
    for suite in suites:
        results[suite.server] = {
            "passed": suite.passed,
            "failed": suite.failed,
            "total": suite.total,
            "success_rate": suite.success_rate,
            "tests": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                    "details": r.details,
                }
                for r in suite.results
            ],
        }

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results exported to: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Functional tests for AAS servers")
    parser.add_argument(
        "--target",
        choices=["titan", "basyx", "both"],
        default="both",
        help="Which server(s) to test",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/results/functional_results.json",
        help="Output file for results",
    )
    parser.add_argument(
        "--titan-url",
        default="http://localhost:8080",
        help="Titan-AAS base URL",
    )
    parser.add_argument(
        "--basyx-url",
        default="http://localhost:8081",
        help="BaSyx Python SDK base URL",
    )
    args = parser.parse_args()

    suites: list[TestSuite] = []

    # Configure servers with custom URLs if provided
    titan_config = ServerConfig(
        name="Titan-AAS",
        base_url=args.titan_url,
        shells_path="/shells",
        submodels_path="/submodels",
    )
    basyx_config = ServerConfig(
        name="BaSyx Python SDK",
        base_url=args.basyx_url,
        shells_path="/shells",
        submodels_path="/submodels",
    )

    if args.target in ("titan", "both"):
        tester = FunctionalTester(titan_config)
        try:
            suites.append(tester.run_all_tests())
        finally:
            tester.close()

    if args.target in ("basyx", "both"):
        tester = FunctionalTester(basyx_config)
        try:
            suites.append(tester.run_all_tests())
        finally:
            tester.close()

    print_summary(suites)
    export_results(suites, args.output)

    # Exit with error if any tests failed
    total_failed = sum(s.failed for s in suites)
    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
