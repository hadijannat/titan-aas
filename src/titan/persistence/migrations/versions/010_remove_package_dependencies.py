"""Remove package dependency tracking table.

Revision ID: 010_remove_package_dependencies
Revises: 009_operation_invocations
Create Date: 2026-01-14

This migration removes the aasx_package_dependencies table, which is no longer
used by the codebase.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers
revision: str = "010_remove_package_dependencies"
down_revision: str | None = "009_operation_invocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("aasx_package_dependencies")


def downgrade() -> None:
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
        sa.Index("idx_pkg_deps_package_id", "package_id"),
        sa.Index("idx_pkg_deps_depends_on_id", "depends_on_id"),
        sa.UniqueConstraint("package_id", "depends_on_id", name="uq_pkg_dependency"),
    )
