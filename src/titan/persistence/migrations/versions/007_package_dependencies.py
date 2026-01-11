"""Add package dependency tracking tables.

Revision ID: 007_package_dependencies
Revises: 006_package_versioning
Create Date: 2026-01-11

This migration adds package dependency tracking:

1. aasx_package_dependencies table: Tracks dependencies between packages
2. dependency_type: required, optional, recommended, conflicts
3. version_constraint: Semantic version constraints
4. Circular dependency detection support
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "007_package_dependencies"
down_revision: str | None = "006_package_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add package dependency tracking table."""
    op.create_table(
        "aasx_package_dependencies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("aasx_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "depends_on_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("aasx_packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dependency_type",
            sa.String(50),
            nullable=False,
            comment="required, optional, recommended, conflicts",
        ),
        sa.Column(
            "version_constraint",
            sa.Text,
            nullable=True,
            comment="Semantic version constraint (e.g., >=1.0.0,<2.0.0)",
        ),
        sa.Column(
            "description",
            sa.Text,
            nullable=True,
            comment="Human-readable dependency description",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Indexes
        sa.Index("idx_pkg_deps_package_id", "package_id"),
        sa.Index("idx_pkg_deps_depends_on_id", "depends_on_id"),
        # Unique constraint to prevent duplicate dependencies
        sa.UniqueConstraint("package_id", "depends_on_id", name="uq_pkg_dependency"),
    )


def downgrade() -> None:
    """Remove package dependency tracking table."""
    op.drop_table("aasx_package_dependencies")
