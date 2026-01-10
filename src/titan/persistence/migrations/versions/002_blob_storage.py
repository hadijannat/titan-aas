"""Add blob storage table for large binary assets.

Revision ID: 002_blob_storage
Revises: 001_initial
Create Date: 2025-01-10

The "Binary Blob Trap" fix:
- Large File/Blob elements are stored separately in an object store
- This table tracks metadata and storage locations
- Prevents TOAST table bloat and Redis OOM
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "002_blob_storage"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Blob assets table - stores metadata for externalized binary content
    op.create_table(
        "blob_assets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # Reference to the parent submodel
        sa.Column("submodel_id", postgresql.UUID(as_uuid=False), nullable=False),
        # The idShortPath to the element containing this blob
        sa.Column("id_short_path", sa.Text(), nullable=False),
        # Storage backend: "local", "s3", "minio", "azure"
        sa.Column("storage_type", sa.String(50), nullable=False, server_default="local"),
        # Storage location (path, S3 URI, etc.)
        sa.Column("storage_uri", sa.Text(), nullable=False),
        # Content type (MIME type)
        sa.Column("content_type", sa.String(255), nullable=False),
        # Original filename if available
        sa.Column("filename", sa.Text(), nullable=True),
        # Size in bytes
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        # SHA256 hash of content for integrity verification
        sa.Column("content_hash", sa.String(64), nullable=False),
        # Timestamps
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
        ),
    )

    # Indexes
    op.create_index(
        "idx_blob_assets_submodel_id",
        "blob_assets",
        ["submodel_id"],
    )
    op.create_index(
        "idx_blob_assets_submodel_path",
        "blob_assets",
        ["submodel_id", "id_short_path"],
        unique=True,
    )
    op.create_index(
        "idx_blob_assets_content_hash",
        "blob_assets",
        ["content_hash"],
    )

    # Foreign key to submodels table
    op.create_foreign_key(
        "fk_blob_assets_submodel",
        "blob_assets",
        "submodels",
        ["submodel_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_blob_assets_submodel", "blob_assets", type_="foreignkey")
    op.drop_table("blob_assets")
