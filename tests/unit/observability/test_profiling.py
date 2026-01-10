"""Tests for performance profiling."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from titan.observability.profiling import (
    EndpointStats,
    ProfileCollector,
    ProfileStats,
    ProfilingMiddleware,
    RequestStats,
    get_collector,
    profile_request,
    reset_collector,
)


class TestRequestStats:
    """Tests for RequestStats dataclass."""

    def test_request_stats_creation(self) -> None:
        """RequestStats can be created."""
        stats = RequestStats(
            path="/shells",
            method="GET",
            status_code=200,
            duration_ms=10.5,
            timestamp=1000.0,
        )

        assert stats.path == "/shells"
        assert stats.method == "GET"
        assert stats.status_code == 200
        assert stats.duration_ms == 10.5


class TestEndpointStats:
    """Tests for EndpointStats dataclass."""

    def test_endpoint_stats_creation(self) -> None:
        """EndpointStats can be created."""
        stats = EndpointStats(
            path="/shells",
            method="GET",
        )

        assert stats.path == "/shells"
        assert stats.request_count == 0
        assert stats.avg_duration_ms == 0.0

    def test_record_request(self) -> None:
        """Recording a request updates stats."""
        stats = EndpointStats(path="/shells", method="GET")

        stats.record(10.0)
        stats.record(20.0)

        assert stats.request_count == 2
        assert stats.total_duration_ms == 30.0
        assert stats.avg_duration_ms == 15.0
        assert stats.min_duration_ms == 10.0
        assert stats.max_duration_ms == 20.0

    def test_record_error(self) -> None:
        """Recording an error increments error count."""
        stats = EndpointStats(path="/shells", method="GET")

        stats.record(10.0, is_error=False)
        stats.record(20.0, is_error=True)

        assert stats.error_count == 1


class TestProfileStats:
    """Tests for ProfileStats dataclass."""

    def test_profile_stats_to_dict(self) -> None:
        """ProfileStats converts to dictionary."""
        stats = ProfileStats(
            total_requests=100,
            total_errors=5,
            avg_duration_ms=15.5,
            p50_duration_ms=10.0,
            p95_duration_ms=50.0,
            p99_duration_ms=100.0,
        )

        data = stats.to_dict()

        assert data["requests"]["total"] == 100
        assert data["requests"]["errors"] == 5
        assert data["requests"]["avg_duration_ms"] == 15.5

    def test_cache_hit_rate(self) -> None:
        """Cache hit rate is calculated correctly."""
        stats = ProfileStats(
            cache_hits=80,
            cache_misses=20,
        )

        data = stats.to_dict()

        assert data["cache"]["hit_rate"] == 0.8


class TestProfileCollector:
    """Tests for ProfileCollector."""

    @pytest.fixture
    def collector(self) -> ProfileCollector:
        """Create fresh collector."""
        return ProfileCollector()

    def test_record_request(self, collector: ProfileCollector) -> None:
        """Recording requests updates history."""
        collector.record_request("/shells", "GET", 200, 10.0)

        stats = collector.get_stats()
        assert stats.total_requests == 1

    def test_record_multiple_requests(self, collector: ProfileCollector) -> None:
        """Recording multiple requests aggregates stats."""
        collector.record_request("/shells", "GET", 200, 10.0)
        collector.record_request("/shells", "GET", 200, 20.0)
        collector.record_request("/shells", "GET", 500, 30.0)

        stats = collector.get_stats()
        assert stats.total_requests == 3
        assert stats.total_errors == 1
        assert stats.avg_duration_ms == 20.0

    def test_percentiles(self, collector: ProfileCollector) -> None:
        """Percentiles are calculated correctly."""
        for i in range(100):
            collector.record_request("/test", "GET", 200, float(i + 1))

        stats = collector.get_stats()
        assert stats.p50_duration_ms == pytest.approx(50.5, abs=1)
        assert stats.p95_duration_ms == pytest.approx(95.5, abs=1)
        assert stats.p99_duration_ms == pytest.approx(99.5, abs=1)

    def test_record_cache_hit(self, collector: ProfileCollector) -> None:
        """Cache hits are recorded."""
        collector.record_cache_hit()
        collector.record_cache_hit()
        collector.record_cache_miss()

        stats = collector.get_stats()
        assert stats.cache_hits == 2
        assert stats.cache_misses == 1

    def test_record_db_query(self, collector: ProfileCollector) -> None:
        """Database queries are recorded."""
        collector.record_db_query(5.0)
        collector.record_db_query(15.0)

        stats = collector.get_stats()
        assert stats.db_query_count == 2
        assert stats.avg_query_duration_ms == 10.0

    def test_get_endpoint_stats(self, collector: ProfileCollector) -> None:
        """Endpoint stats are aggregated correctly."""
        collector.record_request("/shells", "GET", 200, 10.0)
        collector.record_request("/shells", "GET", 200, 20.0)
        collector.record_request("/submodels", "POST", 201, 30.0)

        endpoint_stats = collector.get_endpoint_stats()

        assert len(endpoint_stats) == 2

        shells_stats = next(
            s for s in endpoint_stats if s.path == "/shells"
        )
        assert shells_stats.request_count == 2
        assert shells_stats.avg_duration_ms == 15.0

    def test_reset(self, collector: ProfileCollector) -> None:
        """Reset clears all stats."""
        collector.record_request("/shells", "GET", 200, 10.0)
        collector.record_cache_hit()

        collector.reset()

        stats = collector.get_stats()
        assert stats.total_requests == 0
        assert stats.cache_hits == 0

    def test_max_history(self) -> None:
        """History is trimmed to max size."""
        collector = ProfileCollector(max_history=10)

        for i in range(20):
            collector.record_request("/test", "GET", 200, 1.0)

        assert len(collector._request_history) == 10


class TestGlobalCollector:
    """Tests for global collector functions."""

    def test_get_collector_singleton(self) -> None:
        """get_collector returns singleton."""
        reset_collector()

        c1 = get_collector()
        c2 = get_collector()

        assert c1 is c2

    def test_reset_collector(self) -> None:
        """reset_collector creates new instance."""
        c1 = get_collector()
        reset_collector()
        c2 = get_collector()

        assert c1 is not c2


class TestProfileRequestContext:
    """Tests for profile_request context manager."""

    def test_profile_request_records(self) -> None:
        """profile_request records duration."""
        reset_collector()
        collector = get_collector()

        with profile_request("/test", "GET"):
            pass  # Simulate request

        stats = collector.get_stats()
        assert stats.total_requests == 1


class TestProfilingMiddleware:
    """Tests for ProfilingMiddleware."""

    def test_middleware_records_requests(self) -> None:
        """Middleware records all requests."""
        app = FastAPI()
        collector = ProfileCollector()
        app.add_middleware(ProfilingMiddleware, collector=collector)

        @app.get("/test")
        async def test_endpoint() -> dict[str, str]:
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200

        stats = collector.get_stats()
        assert stats.total_requests == 1

    def test_middleware_records_errors(self) -> None:
        """Middleware records error responses."""
        app = FastAPI()
        collector = ProfileCollector()
        app.add_middleware(ProfilingMiddleware, collector=collector)

        @app.get("/error")
        async def error_endpoint() -> dict[str, str]:
            from fastapi import HTTPException

            raise HTTPException(status_code=500, detail="Error")

        client = TestClient(app)
        response = client.get("/error")

        assert response.status_code == 500

        stats = collector.get_stats()
        assert stats.total_errors == 1
