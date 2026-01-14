"""Tests for dashboard API router structure.

These tests verify the dashboard router configuration and endpoint existence
without executing the actual endpoints (which require database/cache/auth).
"""

from fastapi import APIRouter

from titan.api.routers.dashboard import router as dashboard_router
from titan.api.routers.dashboard.cache import router as cache_router
from titan.api.routers.dashboard.connectors import router as connectors_router
from titan.api.routers.dashboard.database import router as database_router
from titan.api.routers.dashboard.events import router as events_router
from titan.api.routers.dashboard.observability import router as observability_router
from titan.api.routers.dashboard.overview import router as overview_router
from titan.api.routers.dashboard.security import router as security_router


class TestDashboardRouterStructure:
    """Test dashboard router structure and configuration."""

    def test_dashboard_router_has_prefix(self) -> None:
        """Dashboard router has /dashboard prefix."""
        assert dashboard_router.prefix == "/dashboard"

    def test_dashboard_router_has_tags(self) -> None:
        """Dashboard router has appropriate tags."""
        assert "Dashboard" in dashboard_router.tags

    def test_dashboard_router_is_api_router(self) -> None:
        """Dashboard router is a FastAPI APIRouter instance."""
        assert isinstance(dashboard_router, APIRouter)


class TestOverviewRouter:
    """Test overview sub-router configuration."""

    def test_overview_router_has_tags(self) -> None:
        """Overview router has appropriate tags."""
        assert any("Overview" in tag for tag in overview_router.tags)

    def test_overview_endpoint_registered(self) -> None:
        """Overview endpoint is registered on the router."""
        paths = [route.path for route in overview_router.routes]
        assert "/overview" in paths

    def test_overview_endpoint_is_get(self) -> None:
        """Overview endpoint uses GET method."""
        for route in overview_router.routes:
            if route.path == "/overview":
                assert "GET" in route.methods


class TestDatabaseRouter:
    """Test database sub-router configuration."""

    def test_database_router_has_tags(self) -> None:
        """Database router has appropriate tags."""
        assert any("Database" in tag for tag in database_router.tags)

    def test_database_router_has_prefix(self) -> None:
        """Database router has correct prefix."""
        assert database_router.prefix == "/database"

    def test_database_stats_endpoint_registered(self) -> None:
        """Database stats endpoint is registered."""
        paths = [route.path for route in database_router.routes]
        assert any("/stats" in path for path in paths)

    def test_database_tables_endpoint_registered(self) -> None:
        """Database tables endpoint is registered."""
        paths = [route.path for route in database_router.routes]
        assert any("/tables" in path for path in paths)


class TestCacheRouter:
    """Test cache sub-router configuration."""

    def test_cache_router_has_tags(self) -> None:
        """Cache router has appropriate tags."""
        assert any("Cache" in tag for tag in cache_router.tags)

    def test_cache_router_has_prefix(self) -> None:
        """Cache router has correct prefix."""
        assert cache_router.prefix == "/cache"

    def test_cache_stats_endpoint_registered(self) -> None:
        """Cache stats endpoint is registered."""
        paths = [route.path for route in cache_router.routes]
        assert any("/stats" in path for path in paths)

    def test_cache_keys_endpoint_registered(self) -> None:
        """Cache keys endpoint is registered."""
        paths = [route.path for route in cache_router.routes]
        assert any("/keys" in path for path in paths)

    def test_cache_invalidate_endpoint_registered(self) -> None:
        """Cache invalidate endpoint is registered."""
        paths = [route.path for route in cache_router.routes]
        assert any("/invalidate" in path for path in paths)


class TestEventsRouter:
    """Test events sub-router configuration."""

    def test_events_router_has_tags(self) -> None:
        """Events router has appropriate tags."""
        assert any("Events" in tag for tag in events_router.tags)

    def test_events_router_has_prefix(self) -> None:
        """Events router has correct prefix."""
        assert events_router.prefix == "/events"

    def test_events_stats_endpoint_registered(self) -> None:
        """Events stats endpoint is registered."""
        paths = [route.path for route in events_router.routes]
        assert any("/stats" in path for path in paths)

    def test_events_stream_endpoint_registered(self) -> None:
        """Events stream endpoint is registered."""
        paths = [route.path for route in events_router.routes]
        assert any("/stream" in path for path in paths)

    def test_events_history_endpoint_registered(self) -> None:
        """Events history endpoint is registered."""
        paths = [route.path for route in events_router.routes]
        assert any("/history" in path for path in paths)


class TestConnectorsRouter:
    """Test connectors sub-router configuration."""

    def test_connectors_router_has_tags(self) -> None:
        """Connectors router has appropriate tags."""
        assert any("Connectors" in tag for tag in connectors_router.tags)

    def test_connectors_router_has_prefix(self) -> None:
        """Connectors router has correct prefix."""
        assert connectors_router.prefix == "/connectors"

    def test_connectors_status_endpoint_registered(self) -> None:
        """Connectors status endpoint is registered."""
        paths = [route.path for route in connectors_router.routes]
        assert any("/status" in path for path in paths)

    def test_opcua_connect_endpoint_registered(self) -> None:
        """OPC-UA connect endpoint is registered."""
        paths = [route.path for route in connectors_router.routes]
        assert any("opcua/connect" in path for path in paths)

    def test_opcua_disconnect_endpoint_registered(self) -> None:
        """OPC-UA disconnect endpoint is registered."""
        paths = [route.path for route in connectors_router.routes]
        assert any("opcua/disconnect" in path for path in paths)

    def test_modbus_connect_endpoint_registered(self) -> None:
        """Modbus connect endpoint is registered."""
        paths = [route.path for route in connectors_router.routes]
        assert any("modbus/connect" in path for path in paths)

    def test_modbus_disconnect_endpoint_registered(self) -> None:
        """Modbus disconnect endpoint is registered."""
        paths = [route.path for route in connectors_router.routes]
        assert any("modbus/disconnect" in path for path in paths)


class TestSecurityRouter:
    """Test security sub-router configuration."""

    def test_security_router_has_tags(self) -> None:
        """Security router has appropriate tags."""
        assert any("Security" in tag for tag in security_router.tags)

    def test_security_router_has_prefix(self) -> None:
        """Security router has correct prefix."""
        assert security_router.prefix == "/security"

    def test_audit_log_endpoint_registered(self) -> None:
        """Audit log endpoint is registered."""
        paths = [route.path for route in security_router.routes]
        assert any("audit-log" in path for path in paths)

    def test_sessions_endpoint_registered(self) -> None:
        """Sessions endpoint is registered."""
        paths = [route.path for route in security_router.routes]
        assert any("/sessions" in path for path in paths)


class TestObservabilityRouter:
    """Test observability sub-router configuration."""

    def test_observability_router_has_tags(self) -> None:
        """Observability router has appropriate tags."""
        assert any("Observability" in tag for tag in observability_router.tags)

    def test_observability_router_has_prefix(self) -> None:
        """Observability router has correct prefix."""
        assert observability_router.prefix == "/observability"

    def test_log_level_endpoint_registered(self) -> None:
        """Log level endpoint is registered."""
        paths = [route.path for route in observability_router.routes]
        assert any("log-level" in path for path in paths)

    def test_profiling_endpoint_registered(self) -> None:
        """Profiling endpoint is registered."""
        paths = [route.path for route in observability_router.routes]
        assert any("/profiling" in path for path in paths)


class TestRouterIntegration:
    """Test that all sub-routers are properly integrated."""

    def test_all_subrouters_included(self) -> None:
        """All sub-routers are included in main dashboard router."""
        # Collect all routes from the main dashboard router
        all_route_paths = []
        for route in dashboard_router.routes:
            if hasattr(route, "path"):
                all_route_paths.append(route.path)
            elif hasattr(route, "routes"):
                # This is a sub-router
                for sub_route in route.routes:
                    if hasattr(sub_route, "path"):
                        all_route_paths.append(sub_route.path)

        # Check that routes from each sub-router are present
        expected_route_groups = [
            "/overview",
            "/database/stats",
            "/cache/stats",
            "/events/stats",
            "/connectors/status",
            "/security/audit-log",
            "/observability/log-level",
        ]

        for expected_path in expected_route_groups:
            found = any(expected_path in path for path in all_route_paths)
            assert found, f"Expected route {expected_path} not found in dashboard router"

    def test_dashboard_router_route_count(self) -> None:
        """Dashboard router has multiple routes from sub-routers."""
        # The dashboard router should have several routes after including all sub-routers
        assert len(dashboard_router.routes) >= 7  # At least 7 sub-routers

    def test_each_subrouter_has_routes(self) -> None:
        """Each sub-router has at least one route defined."""
        subrouters = [
            overview_router,
            database_router,
            cache_router,
            events_router,
            connectors_router,
            security_router,
            observability_router,
        ]
        for router in subrouters:
            assert len(router.routes) > 0, f"Router {router} has no routes"


class TestEndpointMethods:
    """Test HTTP methods on endpoints."""

    def test_overview_uses_get(self) -> None:
        """Overview endpoint uses GET method."""
        for route in overview_router.routes:
            if route.path == "/overview":
                assert "GET" in route.methods

    def test_cache_invalidate_uses_delete(self) -> None:
        """Cache invalidate endpoint uses DELETE method."""
        for route in cache_router.routes:
            if "invalidate" in route.path:
                assert "DELETE" in route.methods

    def test_connectors_connect_uses_post(self) -> None:
        """Connector connect endpoints use POST method."""
        found_connect = False
        for route in connectors_router.routes:
            # Exclude status endpoint which also contains "connect" substring
            if "/connect" in route.path and "status" not in route.path:
                assert "POST" in route.methods
                found_connect = True
        assert found_connect, "No connect endpoints found"

    def test_log_level_supports_put(self) -> None:
        """Log level endpoint supports PUT method."""
        methods_found = set()
        for route in observability_router.routes:
            if "log-level" in route.path:
                methods_found.update(route.methods)
        assert "PUT" in methods_found

    def test_loggers_supports_get(self) -> None:
        """Loggers endpoint supports GET method for reading log levels."""
        methods_found = set()
        for route in observability_router.routes:
            if "/loggers" in route.path:
                methods_found.update(route.methods)
        assert "GET" in methods_found


class TestResponseModels:
    """Test that endpoints have response models defined."""

    def test_overview_has_response_model(self) -> None:
        """Overview endpoint has a response model."""
        for route in overview_router.routes:
            if route.path == "/overview" and "GET" in route.methods:
                # Check that response_model is set
                assert route.response_model is not None

    def test_database_stats_has_response_model(self) -> None:
        """Database stats endpoint has a response model."""
        for route in database_router.routes:
            if "/stats" in route.path and "GET" in route.methods:
                assert route.response_model is not None

    def test_cache_stats_has_response_model(self) -> None:
        """Cache stats endpoint has a response model."""
        for route in cache_router.routes:
            if "/stats" in route.path and "GET" in route.methods:
                assert route.response_model is not None
