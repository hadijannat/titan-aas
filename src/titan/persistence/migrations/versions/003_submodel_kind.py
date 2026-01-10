"""Add kind column to submodels for template filtering.

Revision ID: 003_submodel_kind
Revises: 002_blob_storage
Create Date: 2026-01-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "003_submodel_kind"
down_revision: Union[str, None] = "002_blob_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("submodels", sa.Column("kind", sa.String(20), nullable=True))
    op.create_index("idx_submodels_kind", "submodels", ["kind"])


def downgrade() -> None:
    op.drop_index("idx_submodels_kind", table_name="submodels")
    op.drop_column("submodels", "kind")
