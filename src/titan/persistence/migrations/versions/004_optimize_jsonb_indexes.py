"""Optimize JSONB indexes for high-throughput queries (15K+ RPS).

Revision ID: 004_optimize_jsonb_indexes
Revises: 003_submodel_kind
Create Date: 2026-01-10

This migration optimizes JSONB indexes for production workloads:

1. Replace standard GIN indexes with jsonb_path_ops variant:
   - 5-10x smaller index size
   - Faster @> (containment) queries
   - Optimized for key/value lookups

2. Add expression indexes for high-frequency query paths:
   - idShort on AAS and submodels
   - assetKind on AAS assetInformation

Note: jsonb_path_ops does NOT support ?, ?|, ?& (key existence) operators.
If those operators are needed, keep the original GIN index.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "004_optimize_jsonb_indexes"
down_revision: str | None = "003_submodel_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop existing GIN indexes (standard operator class)
    op.drop_index("idx_aas_doc_gin", table_name="aas")
    op.drop_index("idx_submodels_doc_gin", table_name="submodels")
    op.drop_index("idx_concept_descriptions_doc_gin", table_name="concept_descriptions")

    # Recreate with jsonb_path_ops (5-10x smaller, faster containment queries)
    op.execute("""
        CREATE INDEX idx_aas_doc_gin ON aas
        USING GIN (doc jsonb_path_ops)
    """)
    op.execute("""
        CREATE INDEX idx_submodels_doc_gin ON submodels
        USING GIN (doc jsonb_path_ops)
    """)
    op.execute("""
        CREATE INDEX idx_concept_descriptions_doc_gin ON concept_descriptions
        USING GIN (doc jsonb_path_ops)
    """)

    # Add expression indexes for common query paths
    # idShort on AAS (frequently filtered)
    op.execute("""
        CREATE INDEX idx_aas_id_short ON aas
        ((doc->>'idShort'))
    """)

    # idShort on submodels (frequently filtered)
    op.execute("""
        CREATE INDEX idx_submodels_id_short ON submodels
        ((doc->>'idShort'))
    """)

    # assetKind on AAS assetInformation (Instance vs Type filtering)
    op.execute("""
        CREATE INDEX idx_aas_asset_kind ON aas
        ((doc->'assetInformation'->>'assetKind'))
    """)


def downgrade() -> None:
    # Drop expression indexes
    op.drop_index("idx_aas_asset_kind", table_name="aas")
    op.drop_index("idx_submodels_id_short", table_name="submodels")
    op.drop_index("idx_aas_id_short", table_name="aas")

    # Drop jsonb_path_ops GIN indexes
    op.drop_index("idx_concept_descriptions_doc_gin", table_name="concept_descriptions")
    op.drop_index("idx_submodels_doc_gin", table_name="submodels")
    op.drop_index("idx_aas_doc_gin", table_name="aas")

    # Recreate original GIN indexes (default operator class)
    op.execute("""
        CREATE INDEX idx_aas_doc_gin ON aas
        USING GIN (doc)
    """)
    op.execute("""
        CREATE INDEX idx_submodels_doc_gin ON submodels
        USING GIN (doc)
    """)
    op.execute("""
        CREATE INDEX idx_concept_descriptions_doc_gin ON concept_descriptions
        USING GIN (doc)
    """)
