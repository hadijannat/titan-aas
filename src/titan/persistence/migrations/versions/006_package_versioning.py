"""Add version tracking to AASX packages.

Revision ID: 006_package_versioning
Revises: 005_federation_tables
Create Date: 2026-01-11

This migration adds version tracking fields to aasx_packages table:

1. version: Integer version number (default 1)
2. version_comment: Optional description of changes in this version
3. created_by: User who created this version
4. previous_version_id: Foreign key to parent version for version history
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "006_package_versioning"
down_revision: str | None = "005_federation_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add version tracking columns to aasx_packages table."""
    # Add version tracking columns
    op.add_column(
        "aasx_packages",
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    op.add_column(
        "aasx_packages",
        sa.Column("version_comment", sa.Text, nullable=True),
    )
    op.add_column(
        "aasx_packages",
        sa.Column("created_by", sa.Text, nullable=True),
    )
    op.add_column(
        "aasx_packages",
        sa.Column(
            "previous_version_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
    )

    # Add foreign key constraint for version history
    op.create_foreign_key(
        "fk_aasx_packages_previous_version",
        "aasx_packages",
        "aasx_packages",
        ["previous_version_id"],
        ["id"],
        ondelete="SET NULL",  # If parent version deleted, set to NULL
    )

    # Add index for version queries
    op.create_index(
        "idx_aasx_packages_previous_version",
        "aasx_packages",
        ["previous_version_id"],
    )


def downgrade() -> None:
    """Remove version tracking columns."""
    # Drop index
    op.drop_index("idx_aasx_packages_previous_version", table_name="aasx_packages")

    # Drop foreign key
    op.drop_constraint("fk_aasx_packages_previous_version", "aasx_packages", type_="foreignkey")

    # Drop columns
    op.drop_column("aasx_packages", "previous_version_id")
    op.drop_column("aasx_packages", "created_by")
    op.drop_column("aasx_packages", "version_comment")
    op.drop_column("aasx_packages", "version")
