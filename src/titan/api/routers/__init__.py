"""API routers for Titan-AAS.

Provides modular endpoint organization per IDTA-01002 Part 2.
"""

from titan.api.routers import (
    aas_repository,
    blobs,
    concept_description_repository,
    description,
    discovery,
    health,
    metrics,
    registry,
    serialization,
    submodel_repository,
    system,
    websocket,
)

__all__ = [
    "aas_repository",
    "blobs",
    "concept_description_repository",
    "description",
    "discovery",
    "health",
    "metrics",
    "registry",
    "serialization",
    "submodel_repository",
    "system",
    "websocket",
]
