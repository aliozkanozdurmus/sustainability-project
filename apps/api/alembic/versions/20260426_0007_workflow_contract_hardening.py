"""Add workflow contract hardening columns.

Revision ID: 20260426_0007
Revises: 20260408_0006
Create Date: 2026-04-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260426_0007"
down_revision: Union[str, Sequence[str], None] = "20260408_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.add_column(sa.Column("normalization_policy_ref", sa.String(length=1024), nullable=True))

    with op.batch_alter_table("verification_results") as batch_op:
        batch_op.add_column(sa.Column("reason_code", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("policy_version", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("citation_span_refs_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("verification_results") as batch_op:
        batch_op.drop_column("citation_span_refs_json")
        batch_op.drop_column("blocking")
        batch_op.drop_column("policy_version")
        batch_op.drop_column("reason_code")

    with op.batch_alter_table("calculation_runs") as batch_op:
        batch_op.drop_column("normalization_policy_ref")
