"""Initial schema for titan-aas.

Revision ID: 001_initial
Revises:
Create Date: 2025-01-10

Creates tables for:
- aas: Asset Administration Shells
- submodels: Submodels
- concept_descriptions: Concept Descriptions
- aas_descriptors: AAS Registry descriptors
- submodel_descriptors: Submodel Registry descriptors

Each table uses the dual storage pattern:
- doc (JSONB): for PostgreSQL queries and filters
- doc_bytes (BYTEA): canonical JSON for streaming reads
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # AAS table
    op.create_table(
        "aas",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("identifier_b64", sa.String(4000), nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False),
        sa.Column("doc_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("etag", sa.String(64), nullable=False),
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
    op.create_index("idx_aas_identifier", "aas", ["identifier"], unique=True)
    op.create_index("idx_aas_identifier_b64", "aas", ["identifier_b64"], unique=True)
    op.create_index(
        "idx_aas_doc_gin",
        "aas",
        ["doc"],
        postgresql_using="gin",
    )

    # Submodels table
    op.create_table(
        "submodels",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("identifier_b64", sa.String(4000), nullable=False),
        sa.Column("semantic_id", sa.Text(), nullable=True),
        sa.Column("doc", postgresql.JSONB(), nullable=False),
        sa.Column("doc_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("etag", sa.String(64), nullable=False),
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
    op.create_index("idx_submodels_identifier", "submodels", ["identifier"], unique=True)
    op.create_index("idx_submodels_identifier_b64", "submodels", ["identifier_b64"], unique=True)
    op.create_index("idx_submodels_semantic_id", "submodels", ["semantic_id"])
    op.create_index(
        "idx_submodels_doc_gin",
        "submodels",
        ["doc"],
        postgresql_using="gin",
    )

    # Concept Descriptions table
    op.create_table(
        "concept_descriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("identifier_b64", sa.String(4000), nullable=False),
        sa.Column("doc", postgresql.JSONB(), nullable=False),
        sa.Column("doc_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("etag", sa.String(64), nullable=False),
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
    op.create_index(
        "idx_concept_descriptions_identifier",
        "concept_descriptions",
        ["identifier"],
        unique=True,
    )
    op.create_index(
        "idx_concept_descriptions_identifier_b64",
        "concept_descriptions",
        ["identifier_b64"],
        unique=True,
    )
    op.create_index(
        "idx_concept_descriptions_doc_gin",
        "concept_descriptions",
        ["doc"],
        postgresql_using="gin",
    )

    # AAS Descriptors table (Registry)
    op.create_table(
        "aas_descriptors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("identifier_b64", sa.String(4000), nullable=False),
        sa.Column("global_asset_id", sa.Text(), nullable=True),
        sa.Column("doc", postgresql.JSONB(), nullable=False),
        sa.Column("doc_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("etag", sa.String(64), nullable=False),
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
    op.create_index(
        "idx_aas_descriptors_identifier",
        "aas_descriptors",
        ["identifier"],
        unique=True,
    )
    op.create_index(
        "idx_aas_descriptors_identifier_b64",
        "aas_descriptors",
        ["identifier_b64"],
        unique=True,
    )
    op.create_index(
        "idx_aas_descriptors_global_asset_id",
        "aas_descriptors",
        ["global_asset_id"],
    )

    # Submodel Descriptors table (Registry)
    op.create_table(
        "submodel_descriptors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("identifier_b64", sa.String(4000), nullable=False),
        sa.Column("semantic_id", sa.Text(), nullable=True),
        sa.Column("doc", postgresql.JSONB(), nullable=False),
        sa.Column("doc_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("etag", sa.String(64), nullable=False),
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
    op.create_index(
        "idx_submodel_descriptors_identifier",
        "submodel_descriptors",
        ["identifier"],
        unique=True,
    )
    op.create_index(
        "idx_submodel_descriptors_identifier_b64",
        "submodel_descriptors",
        ["identifier_b64"],
        unique=True,
    )
    op.create_index(
        "idx_submodel_descriptors_semantic_id",
        "submodel_descriptors",
        ["semantic_id"],
    )


def downgrade() -> None:
    op.drop_table("submodel_descriptors")
    op.drop_table("aas_descriptors")
    op.drop_table("concept_descriptions")
    op.drop_table("submodels")
    op.drop_table("aas")
