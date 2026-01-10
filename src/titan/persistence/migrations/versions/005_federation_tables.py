"""Add federation sync tables for hub-spoke synchronization.

Revision ID: 005_federation_tables
Revises: 004_optimize_jsonb_indexes
Create Date: 2026-01-10

This migration adds tables required for federation sync:

1. federation_sync_state: Track sync cursor per peer/entity type
2. federation_conflicts: Store unresolved sync conflicts
3. federation_pending_changes: Persistent offline queue (replaces in-memory)
4. federation_sync_log: Audit trail for sync operations
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "005_federation_tables"
down_revision: str | None = "004_optimize_jsonb_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Federation Sync State - tracks sync progress per peer/entity type
    op.create_table(
        "federation_sync_state",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("peer_id", sa.String(255), nullable=False, index=True),
        sa.Column(
            "entity_type",
            sa.String(50),
            nullable=False,
            comment="aas, submodel, concept_description",
        ),
        sa.Column("last_sync_cursor", sa.String(255), nullable=True, comment="Pagination cursor"),
        sa.Column(
            "last_sync_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful sync time",
        ),
        sa.Column("items_synced", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("peer_id", "entity_type", name="uq_sync_state_peer_entity"),
    )

    # Federation Conflicts - stores unresolved conflicts for manual resolution
    op.create_table(
        "federation_conflicts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("peer_id", sa.String(255), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Text, nullable=False, index=True),
        sa.Column("local_etag", sa.String(64), nullable=False),
        sa.Column("remote_etag", sa.String(64), nullable=False),
        sa.Column("local_doc", postgresql.JSONB, nullable=False),
        sa.Column("remote_doc", postgresql.JSONB, nullable=False),
        sa.Column(
            "resolution_strategy",
            sa.String(50),
            nullable=True,
            comment="last_write_wins, local_preferred, remote_preferred, manual",
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_federation_conflicts_unresolved",
        "federation_conflicts",
        ["peer_id", "entity_type"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    # Federation Pending Changes - persistent offline queue
    op.create_table(
        "federation_pending_changes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Text, nullable=False),
        sa.Column(
            "action",
            sa.String(20),
            nullable=False,
            comment="create, update, delete",
        ),
        sa.Column("data", sa.LargeBinary, nullable=True, comment="Canonical JSON bytes"),
        sa.Column("etag", sa.String(64), nullable=True),
        sa.Column(
            "priority",
            sa.String(10),
            nullable=False,
            server_default="normal",
            comment="high, normal, low",
        ),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("target_peer_id", sa.String(255), nullable=True, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_pending_changes_priority",
        "federation_pending_changes",
        ["priority", "created_at"],
    )

    # Federation Sync Log - audit trail for sync operations
    op.create_table(
        "federation_sync_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("peer_id", sa.String(255), nullable=False, index=True),
        sa.Column(
            "sync_direction",
            sa.String(10),
            nullable=False,
            comment="push, pull, bidirectional",
        ),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("items_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conflicts_detected", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="running",
            comment="running, completed, failed, cancelled",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_sync_log_peer_time",
        "federation_sync_log",
        ["peer_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("federation_sync_log")
    op.drop_table("federation_pending_changes")
    op.drop_table("federation_conflicts")
    op.drop_table("federation_sync_state")
