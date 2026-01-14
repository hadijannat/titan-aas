"""Add operation_invocations table for tracking Operation element invocations.

Revision ID: 009_operation_invocations
Revises: 008_package_version_tags
Create Date: 2026-01-14

This migration adds the operation_invocations table for:
- Tracking Operation element invocations (IDTA-01002 Part 2)
- Storing invocation state for async polling
- Auditing operation execution history
- Mapping to external systems via correlation_id (OPC-UA, Modbus)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "009_operation_invocations"
down_revision: str | None = "008_package_version_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Operation Invocations table
    op.create_table(
        "operation_invocations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Invocation ID (used as handleId in REST API)",
        ),
        sa.Column(
            "submodel_id",
            sa.Text,
            nullable=False,
            index=True,
            comment="ID of the submodel containing the Operation",
        ),
        sa.Column(
            "submodel_id_b64",
            sa.String(4000),
            nullable=False,
            index=True,
            comment="Base64URL-encoded submodel ID",
        ),
        sa.Column(
            "id_short_path",
            sa.Text,
            nullable=False,
            comment="Path to Operation element (e.g., StartPump or Controls.StartPump)",
        ),
        sa.Column(
            "execution_state",
            sa.String(20),
            nullable=False,
            server_default="pending",
            index=True,
            comment="pending, running, completed, failed, timeout, cancelled",
        ),
        sa.Column(
            "input_arguments",
            postgresql.JSONB,
            nullable=True,
            comment="Input argument values (array of {idShort, value, valueType})",
        ),
        sa.Column(
            "output_arguments",
            postgresql.JSONB,
            nullable=True,
            comment="Output argument values from completed operation",
        ),
        sa.Column(
            "inoutput_arguments",
            postgresql.JSONB,
            nullable=True,
            comment="In-out argument values (modified by operation)",
        ),
        sa.Column(
            "error_message",
            sa.Text,
            nullable=True,
            comment="Error message for failed invocations",
        ),
        sa.Column(
            "error_code",
            sa.String(100),
            nullable=True,
            comment="Error code for failed invocations",
        ),
        sa.Column(
            "correlation_id",
            sa.String(255),
            nullable=True,
            index=True,
            comment="External correlation ID for OPC-UA/Modbus mapping",
        ),
        sa.Column(
            "timeout_ms",
            sa.BigInteger,
            nullable=True,
            comment="Timeout in milliseconds for async operations",
        ),
        sa.Column(
            "requested_by",
            sa.String(255),
            nullable=True,
            comment="User/service that invoked the operation",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When execution started",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When execution completed",
        ),
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

    # Composite index for querying invocations by submodel and operation
    op.create_index(
        "idx_op_invocations_submodel_path",
        "operation_invocations",
        ["submodel_id", "id_short_path"],
    )

    # Index for polling by state (pending/running operations)
    op.create_index(
        "idx_op_invocations_state_created",
        "operation_invocations",
        ["execution_state", "created_at"],
    )

    # Index for correlation ID lookups (OPC-UA/Modbus response mapping)
    op.create_index(
        "idx_op_invocations_correlation",
        "operation_invocations",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_op_invocations_correlation")
    op.drop_index("idx_op_invocations_state_created")
    op.drop_index("idx_op_invocations_submodel_path")
    op.drop_table("operation_invocations")
