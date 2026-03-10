"""Add composite indexes for run observability queries.

Revision ID: 20260305_0003
Revises: 20260305_0002
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260305_0003"
down_revision: Union[str, Sequence[str], None] = "20260305_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_verification_results_report_attempt_status_checked_at",
        "verification_results",
        ["report_run_id", "run_attempt", "status", "checked_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_report_event_occurred_at",
        "audit_events",
        ["report_run_id", "event_type", "event_name", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_report_event_occurred_at", table_name="audit_events")
    op.drop_index(
        "ix_verification_results_report_attempt_status_checked_at",
        table_name="verification_results",
    )
