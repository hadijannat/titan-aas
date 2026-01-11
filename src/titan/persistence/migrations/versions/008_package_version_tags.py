"""Add version tags to AASX packages.

Revision ID: 008_package_version_tags
Revises: 007_package_dependencies
Create Date: 2026-01-11

This migration adds version tagging support to AASX packages:

1. tags JSONB column: Array of string tags for versions (e.g., ["production", "v2.1.0"])
2. GIN index on tags column for efficient tag queries
3. Enables semantic versioning and deployment stage tracking
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "008_package_version_tags"
down_revision: str | None = "007_package_dependencies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add tags column to aasx_packages table."""
    # Add tags JSONB column
    op.add_column(
        "aasx_packages",
        sa.Column(
            "tags",
            postgresql.JSONB,
            nullable=True,
            comment="Array of string tags for version labeling (e.g., ['production', 'v2.1.0'])",
        ),
    )

    # Create GIN index for efficient tag queries
    op.create_index(
        "idx_aasx_packages_tags",
        "aasx_packages",
        ["tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Remove tags column from aasx_packages table."""
    op.drop_index("idx_aasx_packages_tags", table_name="aasx_packages")
    op.drop_column("aasx_packages", "tags")
