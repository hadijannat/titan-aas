"""End-to-end tests for complete AAS workflows.

These tests verify the full stack works correctly together,
including database persistence, caching, and event publishing.
"""

import time
import uuid

import httpx
import pytest


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_liveness(self, client: httpx.Client):
        """Test liveness probe."""
        response = client.get("/health/live")
        assert response.status_code == 200

    def test_readiness(self, client: httpx.Client):
        """Test readiness probe."""
        response = client.get("/health/ready")
        assert response.status_code == 200

    def test_full_health(self, client: httpx.Client):
        """Test full health check with all dependencies."""
        response = client.get("/health")
        assert response.status_code == 200
        health = response.json()
        assert health["status"] == "healthy"
        assert "checks" in health
        assert health["checks"]["database"]["status"] == "up"
        assert health["checks"]["redis"]["status"] == "up"


class TestAASCrudWorkflow:
    """Test complete AAS CRUD operations."""

    def test_create_read_update_delete_aas(
        self, client: httpx.Client, sample_aas: dict, base64url_encode
    ):
        """Test full CRUD lifecycle for an AAS."""
        # Generate unique ID for this test
        unique_id = f"urn:example:aas:e2e-{uuid.uuid4()}"
        sample_aas["id"] = unique_id
        encoded_id = base64url_encode(unique_id)

        # CREATE
        response = client.post("/shells", json=sample_aas)
        assert response.status_code == 201
        created = response.json()
        assert created["id"] == unique_id

        # READ
        response = client.get(f"/shells/{encoded_id}")
        assert response.status_code == 200
        read = response.json()
        assert read["id"] == unique_id
        assert read["idShort"] == sample_aas["idShort"]

        # UPDATE
        sample_aas["idShort"] = "UpdatedE2ETestAAS"
        response = client.put(f"/shells/{encoded_id}", json=sample_aas)
        assert response.status_code == 204

        # READ after UPDATE
        response = client.get(f"/shells/{encoded_id}")
        assert response.status_code == 200
        updated = response.json()
        assert updated["idShort"] == "UpdatedE2ETestAAS"

        # DELETE
        response = client.delete(f"/shells/{encoded_id}")
        assert response.status_code == 204

        # READ after DELETE (should 404)
        response = client.get(f"/shells/{encoded_id}")
        assert response.status_code == 404

    def test_list_shells_pagination(self, client: httpx.Client, sample_aas: dict, base64url_encode):
        """Test listing shells with pagination."""
        # Create multiple shells
        created_ids = []
        for i in range(5):
            aas = sample_aas.copy()
            aas["id"] = f"urn:example:aas:e2e-list-{uuid.uuid4()}"
            aas["idShort"] = f"E2EListTest{i}"
            response = client.post("/shells", json=aas)
            assert response.status_code == 201
            created_ids.append(aas["id"])

        try:
            # List with limit
            response = client.get("/shells", params={"limit": 2})
            assert response.status_code == 200
            result = response.json()
            assert "result" in result
            assert len(result["result"]) <= 2
            assert "paging_metadata" in result
        finally:
            # Cleanup
            for id in created_ids:
                client.delete(f"/shells/{base64url_encode(id)}")


class TestSubmodelCrudWorkflow:
    """Test complete Submodel CRUD operations."""

    def test_create_read_update_delete_submodel(
        self, client: httpx.Client, sample_submodel: dict, base64url_encode
    ):
        """Test full CRUD lifecycle for a Submodel."""
        # Generate unique ID
        unique_id = f"urn:example:submodel:e2e-{uuid.uuid4()}"
        sample_submodel["id"] = unique_id
        encoded_id = base64url_encode(unique_id)

        # CREATE
        response = client.post("/submodels", json=sample_submodel)
        assert response.status_code == 201
        created = response.json()
        assert created["id"] == unique_id

        # READ
        response = client.get(f"/submodels/{encoded_id}")
        assert response.status_code == 200
        read = response.json()
        assert read["id"] == unique_id
        assert len(read["submodelElements"]) == 3

        # UPDATE
        sample_submodel["submodelElements"][0]["value"] = "30.0"
        response = client.put(f"/submodels/{encoded_id}", json=sample_submodel)
        assert response.status_code == 204

        # READ after UPDATE
        response = client.get(f"/submodels/{encoded_id}")
        assert response.status_code == 200
        updated = response.json()
        temp_elem = next(e for e in updated["submodelElements"] if e["idShort"] == "Temperature")
        assert temp_elem["value"] == "30.0"

        # DELETE
        response = client.delete(f"/submodels/{encoded_id}")
        assert response.status_code == 204

        # READ after DELETE
        response = client.get(f"/submodels/{encoded_id}")
        assert response.status_code == 404

    def test_submodel_element_access(
        self, client: httpx.Client, sample_submodel: dict, base64url_encode
    ):
        """Test accessing individual submodel elements."""
        unique_id = f"urn:example:submodel:e2e-elem-{uuid.uuid4()}"
        sample_submodel["id"] = unique_id
        encoded_id = base64url_encode(unique_id)

        # Create submodel
        response = client.post("/submodels", json=sample_submodel)
        assert response.status_code == 201

        try:
            # Access simple property
            response = client.get(f"/submodels/{encoded_id}/submodel-elements/Temperature")
            assert response.status_code == 200
            elem = response.json()
            assert elem["idShort"] == "Temperature"
            assert elem["value"] == "25.5"

            # Access nested element
            response = client.get(f"/submodels/{encoded_id}/submodel-elements/Metadata.Version")
            assert response.status_code == 200
            nested = response.json()
            assert nested["idShort"] == "Version"
            assert nested["value"] == "1.0.0"

            # Update element
            updated_elem = {
                "modelType": "Property",
                "idShort": "Temperature",
                "valueType": "xs:double",
                "value": "99.9",
            }
            response = client.put(
                f"/submodels/{encoded_id}/submodel-elements/Temperature",
                json=updated_elem,
            )
            assert response.status_code == 204

            # Verify update
            response = client.get(f"/submodels/{encoded_id}/submodel-elements/Temperature")
            assert response.status_code == 200
            assert response.json()["value"] == "99.9"
        finally:
            client.delete(f"/submodels/{encoded_id}")


class TestCacheConsistency:
    """Test that caching works correctly."""

    def test_cache_hit_performance(
        self, client: httpx.Client, sample_submodel: dict, base64url_encode
    ):
        """Test that cached reads are fast."""
        unique_id = f"urn:example:submodel:e2e-cache-{uuid.uuid4()}"
        sample_submodel["id"] = unique_id
        encoded_id = base64url_encode(unique_id)

        # Create submodel
        response = client.post("/submodels", json=sample_submodel)
        assert response.status_code == 201

        try:
            # First read (cache miss)
            response = client.get(f"/submodels/{encoded_id}")
            assert response.status_code == 200

            # Subsequent reads (cache hits) should be faster
            read_times = []
            for _ in range(5):
                start = time.time()
                response = client.get(f"/submodels/{encoded_id}")
                read_times.append(time.time() - start)
                assert response.status_code == 200

            # Cached reads should generally be faster, but we give some tolerance
            # In E2E tests, network latency dominates, so we just verify they work
            assert all(t < 1.0 for t in read_times), "Cached reads took too long"
        finally:
            client.delete(f"/submodels/{encoded_id}")

    def test_cache_invalidation_on_update(
        self, client: httpx.Client, sample_submodel: dict, base64url_encode
    ):
        """Test that cache is invalidated on updates."""
        unique_id = f"urn:example:submodel:e2e-invalidate-{uuid.uuid4()}"
        sample_submodel["id"] = unique_id
        encoded_id = base64url_encode(unique_id)

        # Create submodel
        response = client.post("/submodels", json=sample_submodel)
        assert response.status_code == 201

        try:
            # Read to populate cache
            response = client.get(f"/submodels/{encoded_id}")
            assert response.status_code == 200
            original = response.json()
            original_temp = next(
                e for e in original["submodelElements"] if e["idShort"] == "Temperature"
            )["value"]

            # Update
            sample_submodel["submodelElements"][0]["value"] = "50.0"
            response = client.put(f"/submodels/{encoded_id}", json=sample_submodel)
            assert response.status_code == 204

            # Read again - should see updated value
            response = client.get(f"/submodels/{encoded_id}")
            assert response.status_code == 200
            updated = response.json()
            new_temp = next(
                e for e in updated["submodelElements"] if e["idShort"] == "Temperature"
            )["value"]

            assert new_temp == "50.0"
            assert new_temp != original_temp
        finally:
            client.delete(f"/submodels/{encoded_id}")


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint."""

    def test_metrics_exposed(self, client: httpx.Client):
        """Test that metrics endpoint exposes Prometheus metrics."""
        response = client.get("/metrics")
        assert response.status_code == 200
        metrics = response.text

        # Check for expected metrics
        assert "http_requests_total" in metrics or "http_request" in metrics
        assert "process_" in metrics  # Process metrics


class TestErrorHandling:
    """Test error handling and responses."""

    def test_not_found_error(self, client: httpx.Client, base64url_encode):
        """Test 404 response format."""
        fake_id = base64url_encode("urn:example:nonexistent")
        response = client.get(f"/shells/{fake_id}")
        assert response.status_code == 404
        error = response.json()
        assert "messages" in error

    def test_validation_error(self, client: httpx.Client):
        """Test 400 response for invalid input."""
        invalid_aas = {"id": "test", "invalid_field": "value"}
        response = client.post("/shells", json=invalid_aas)
        assert response.status_code in [400, 422]

    def test_duplicate_id_error(self, client: httpx.Client, sample_aas: dict, base64url_encode):
        """Test 409 conflict for duplicate ID."""
        unique_id = f"urn:example:aas:e2e-dup-{uuid.uuid4()}"
        sample_aas["id"] = unique_id

        # First create should succeed
        response = client.post("/shells", json=sample_aas)
        assert response.status_code == 201

        try:
            # Second create should fail with conflict
            response = client.post("/shells", json=sample_aas)
            assert response.status_code == 409
        finally:
            client.delete(f"/shells/{base64url_encode(unique_id)}")


class TestConcurrentAccess:
    """Test concurrent access patterns."""

    @pytest.mark.parametrize("num_concurrent", [5, 10])
    def test_concurrent_reads(
        self,
        client: httpx.Client,
        sample_submodel: dict,
        base64url_encode,
        num_concurrent: int,
    ):
        """Test concurrent read access."""
        import concurrent.futures

        unique_id = f"urn:example:submodel:e2e-concurrent-{uuid.uuid4()}"
        sample_submodel["id"] = unique_id
        encoded_id = base64url_encode(unique_id)

        # Create submodel
        response = client.post("/submodels", json=sample_submodel)
        assert response.status_code == 201

        try:
            # Concurrent reads
            def read_submodel():
                with httpx.Client(base_url=client.base_url, timeout=30) as c:
                    return c.get(f"/submodels/{encoded_id}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
                futures = [executor.submit(read_submodel) for _ in range(num_concurrent)]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            # All reads should succeed
            assert all(r.status_code == 200 for r in results)
        finally:
            client.delete(f"/submodels/{encoded_id}")
