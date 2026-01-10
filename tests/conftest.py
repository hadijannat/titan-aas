"""Global pytest configuration and fixtures.

Provides SSP marker infrastructure for spec conformance tracking.
"""

from __future__ import annotations


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "ssp(id): mark test with IDTA Service Specification Profile test case ID"
    )


def pytest_collection_modifyitems(items):
    """Extract SSP markers into user_properties for conformance reporting."""
    for item in items:
        for marker in item.iter_markers(name="ssp"):
            if marker.args:
                ssp_id = marker.args[0]
                item.user_properties.append(("ssp_id", ssp_id))
