"""SQLAlchemy ORM models for AAS persistence.

Each table stores both JSONB (for queries) and canonical bytes (for streaming):
- doc: JSONB column for PostgreSQL queries, filters, GIN indexes
- doc_bytes: BYTEA column with canonical JSON for fast streaming reads

The etag is SHA256 of doc_bytes for conditional requests.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import uuid4

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

    # Extracted kind for template filtering (SSP-003/004)
    kind: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

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
    submodel_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False, index=True)

    # The idShortPath to the element containing this blob
    id_short_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Storage backend: "local", "s3", "minio", "azure"
    storage_type: Mapped[str] = mapped_column(String(50), nullable=False, default="local")

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


class AasxPackageTable(Base):
    """AASX package table.

    Stores metadata for uploaded AASX packages.
    Package files are stored in blob storage.
    """

    __tablename__ = "aasx_packages"

    # Primary key (internal UUID, also used as packageId)
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # Package filename
    filename: Mapped[str] = mapped_column(Text, nullable=False)

    # Storage location (blob storage URI)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)

    # Package size in bytes
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # SHA256 hash of package content
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Number of shells in package
    shell_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Number of submodels in package
    submodel_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Number of concept descriptions in package
    concept_description_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # JSONB package info (shell IDs, submodel IDs, etc.)
    package_info: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

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
        # Index for content deduplication
        Index("idx_aasx_packages_content_hash", content_hash),
        # Index for filename search
        Index("idx_aasx_packages_filename", filename),
    )


# =============================================================================
# Federation Sync Tables
# =============================================================================


class FederationSyncStateTable(Base):
    """Tracks sync progress per peer and entity type.

    Stores the cursor position for delta sync operations.
    """

    __tablename__ = "federation_sync_state"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    peer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    last_sync_cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sync_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    items_synced: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class FederationConflictTable(Base):
    """Stores unresolved sync conflicts for manual resolution.

    When local and remote versions differ, stores both for resolution.
    """

    __tablename__ = "federation_conflicts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    peer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    local_etag: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_etag: Mapped[str] = mapped_column(String(64), nullable=False)
    local_doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    remote_doc: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resolution_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FederationPendingChangeTable(Base):
    """Persistent offline queue for pending sync changes.

    Replaces in-memory queue for durability across restarts.
    """

    __tablename__ = "federation_pending_changes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    etag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")
    attempts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_peer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index("idx_pending_priority", priority, created_at),)


class FederationSyncLogTable(Base):
    """Audit trail for sync operations.

    Records each sync attempt with results and timing.
    """

    __tablename__ = "federation_sync_log"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    peer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sync_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    items_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    items_failed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    conflicts_detected: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
