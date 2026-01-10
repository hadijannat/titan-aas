"""SQLAlchemy ORM models for AAS persistence.

Each table stores both JSONB (for queries) and canonical bytes (for streaming):
- doc: JSONB column for PostgreSQL queries, filters, GIN indexes
- doc_bytes: BYTEA column with canonical JSON for fast streaming reads

The etag is SHA256 of doc_bytes for conditional requests.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


def generate_etag(doc_bytes: bytes) -> str:
    """Generate ETag from canonical JSON bytes."""
    return hashlib.sha256(doc_bytes).hexdigest()


class AasTable(Base):
    """Asset Administration Shell table.

    Stores AAS with dual JSONB + bytes pattern for fast read/write operations.
    """

    __tablename__ = "aas"

    # Primary key (internal UUID)
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # AAS identifier (the user-facing identifier)
    identifier: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    # Base64URL encoded identifier for path matching
    identifier_b64: Mapped[str] = mapped_column(
        String(4000), unique=True, nullable=False, index=True
    )

    # JSONB for queries and filters
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Canonical JSON bytes for streaming
    doc_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # ETag (SHA256 of doc_bytes)
    etag: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Indexes for common queries
    __table_args__ = (
        # GIN index for JSONB containment queries
        Index("idx_aas_doc_gin", doc, postgresql_using="gin"),
        # Index on global asset ID (extracted from JSONB)
        Index(
            "idx_aas_global_asset_id",
            doc["assetInformation"]["globalAssetId"].astext,
        ),
    )


class SubmodelTable(Base):
    """Submodel table.

    Stores Submodels with dual JSONB + bytes pattern.
    Includes semantic_id extraction for efficient semantic queries.
    """

    __tablename__ = "submodels"

    # Primary key (internal UUID)
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # Submodel identifier
    identifier: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    # Base64URL encoded identifier
    identifier_b64: Mapped[str] = mapped_column(
        String(4000), unique=True, nullable=False, index=True
    )

    # Extracted semantic ID for efficient queries
    semantic_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    # JSONB for queries and filters
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Canonical JSON bytes for streaming
    doc_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # ETag (SHA256 of doc_bytes)
    etag: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Indexes
    __table_args__ = (
        # GIN index for JSONB containment queries
        Index("idx_submodels_doc_gin", doc, postgresql_using="gin"),
    )


class ConceptDescriptionTable(Base):
    """Concept Description table.

    Stores ConceptDescriptions with dual JSONB + bytes pattern.
    """

    __tablename__ = "concept_descriptions"

    # Primary key (internal UUID)
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # ConceptDescription identifier
    identifier: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    # Base64URL encoded identifier
    identifier_b64: Mapped[str] = mapped_column(
        String(4000), unique=True, nullable=False, index=True
    )

    # JSONB for queries and filters
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Canonical JSON bytes for streaming
    doc_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # ETag (SHA256 of doc_bytes)
    etag: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Indexes
    __table_args__ = (
        # GIN index for JSONB containment queries
        Index("idx_concept_descriptions_doc_gin", doc, postgresql_using="gin"),
    )


class AasDescriptorTable(Base):
    """AAS Registry descriptor table.

    Stores AAS descriptors for the Registry service.
    """

    __tablename__ = "aas_descriptors"

    # Primary key (internal UUID)
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # AAS identifier
    identifier: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    # Base64URL encoded identifier
    identifier_b64: Mapped[str] = mapped_column(
        String(4000), unique=True, nullable=False, index=True
    )

    # Global asset ID for discovery
    global_asset_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    # JSONB for queries
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Canonical JSON bytes
    doc_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # ETag
    etag: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SubmodelDescriptorTable(Base):
    """Submodel Registry descriptor table.

    Stores Submodel descriptors for the Registry service.
    """

    __tablename__ = "submodel_descriptors"

    # Primary key (internal UUID)
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # Submodel identifier
    identifier: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    # Base64URL encoded identifier
    identifier_b64: Mapped[str] = mapped_column(
        String(4000), unique=True, nullable=False, index=True
    )

    # Semantic ID for discovery
    semantic_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    # JSONB for queries
    doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Canonical JSON bytes
    doc_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # ETag
    etag: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BlobAssetTable(Base):
    """Blob assets table for externalized binary content.

    The "Binary Blob Trap" fix:
    - Large File/Blob elements are stored in an object store
    - This table tracks metadata and storage locations
    - Prevents TOAST table bloat and Redis OOM
    """

    __tablename__ = "blob_assets"

    # Primary key (internal UUID)
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # Reference to the parent submodel
    submodel_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, index=True
    )

    # The idShortPath to the element containing this blob
    id_short_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Storage backend: "local", "s3", "minio", "azure"
    storage_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="local"
    )

    # Storage location (path, S3 URI, etc.)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)

    # Content type (MIME type)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)

    # Original filename if available
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Size in bytes
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # SHA256 hash of content for integrity verification
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # Unique constraint on submodel + path
        Index(
            "idx_blob_assets_submodel_path",
            submodel_id,
            id_short_path,
            unique=True,
        ),
        # Index for content deduplication
        Index("idx_blob_assets_content_hash", content_hash),
    )
