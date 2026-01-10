"""Persistence layer for Titan-AAS.

This module provides:
- Async PostgreSQL engine and session factory
- SQLAlchemy ORM models with JSONB + canonical bytes storage
- Repository pattern with fast/slow path methods
- Alembic migrations

The dual storage pattern (JSONB + doc_bytes) enables:
- JSONB: PostgreSQL queries, filters, GIN indexes
- doc_bytes: Canonical JSON bytes for streaming (no serialization on read)
"""

from titan.persistence.db import get_engine, get_session, init_db
from titan.persistence.repositories import (
    AasRepository,
    ConceptDescriptionRepository,
    SubmodelRepository,
)
from titan.persistence.tables import AasTable, ConceptDescriptionTable, SubmodelTable

__all__ = [
    # DB
    "get_engine",
    "get_session",
    "init_db",
    # Tables
    "AasTable",
    "SubmodelTable",
    "ConceptDescriptionTable",
    # Repositories
    "AasRepository",
    "SubmodelRepository",
    "ConceptDescriptionRepository",
]
