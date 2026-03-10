"""Add run context fields to verification results.

Revision ID: 20260305_0002
Revises: 20260305_0001
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260305_0002"
down_revision: Union[str, Sequence[str], None] = "20260305_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_report_run_id() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE verification_results AS vr
            SET report_run_id = rs.report_run_id
            FROM claims AS c
            JOIN report_sections AS rs ON rs.id = c.report_section_id
            WHERE vr.claim_id = c.id
              AND vr.report_run_id IS NULL
            """
        )
    else:
        op.execute(
            """
            UPDATE verification_results
            SET report_run_id = (
                SELECT rs.report_run_id
                FROM claims AS c
                JOIN report_sections AS rs ON rs.id = c.report_section_id
                WHERE c.id = verification_results.claim_id
            )
            WHERE report_run_id IS NULL
            """
        )

    missing_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM verification_results WHERE report_run_id IS NULL")
    ).scalar_one()
    if missing_count:
        raise RuntimeError(
            f"Backfill failed: {missing_count} verification rows have no report_run_id."
        )


def upgrade() -> None:
    with op.batch_alter_table("verification_results", schema=None) as batch_op:
        batch_op.add_column(sa.Column("report_run_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("run_execution_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("run_attempt", sa.Integer(), nullable=True))

    _backfill_report_run_id()
    op.execute(
        """
        UPDATE verification_results
        SET run_execution_id = 'legacy_' || id
        WHERE run_execution_id IS NULL OR run_execution_id = ''
        """
    )
    op.execute(
        """
        UPDATE verification_results
        SET run_attempt = 1
        WHERE run_attempt IS NULL
        """
    )

    with op.batch_alter_table("verification_results", schema=None) as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_verification_results_report_run_id_report_runs"),
            "report_runs",
            ["report_run_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            op.f("uq_verification_results_claim_id"),
            ["claim_id", "run_execution_id"],
        )
        batch_op.create_index(
            op.f("ix_verification_results_report_run_id"), ["report_run_id"], unique=False
        )
        batch_op.create_index(
            op.f("ix_verification_results_run_execution_id"),
            ["run_execution_id"],
            unique=False,
        )
        batch_op.alter_column(
            "report_run_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.alter_column(
            "run_execution_id",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.alter_column(
            "run_attempt",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("verification_results", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("uq_verification_results_claim_id"),
            type_="unique",
        )
        batch_op.drop_constraint(
            op.f("fk_verification_results_report_run_id_report_runs"),
            type_="foreignkey",
        )
        batch_op.drop_index(op.f("ix_verification_results_run_execution_id"))
        batch_op.drop_index(op.f("ix_verification_results_report_run_id"))
        batch_op.drop_column("run_attempt")
        batch_op.drop_column("run_execution_id")
        batch_op.drop_column("report_run_id")
