"""Add report artifacts table for publish outputs.

Revision ID: 20260305_0004
Revises: 20260305_0003
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260305_0004"
down_revision: Union[str, Sequence[str], None] = "20260305_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_artifacts",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("report_run_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_report_artifacts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["report_run_id"],
            ["report_runs.id"],
            name=op.f("fk_report_artifacts_report_run_id_report_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_report_artifacts_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_artifacts")),
        sa.UniqueConstraint("report_run_id", "artifact_type", name=op.f("uq_report_artifacts_report_run_id")),
    )
    op.create_index(op.f("ix_report_artifacts_checksum"), "report_artifacts", ["checksum"], unique=False)
    op.create_index(op.f("ix_report_artifacts_project_id"), "report_artifacts", ["project_id"], unique=False)
    op.create_index(op.f("ix_report_artifacts_report_run_id"), "report_artifacts", ["report_run_id"], unique=False)
    op.create_index(op.f("ix_report_artifacts_tenant_id"), "report_artifacts", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_report_artifacts_tenant_id"), table_name="report_artifacts")
    op.drop_index(op.f("ix_report_artifacts_report_run_id"), table_name="report_artifacts")
    op.drop_index(op.f("ix_report_artifacts_project_id"), table_name="report_artifacts")
    op.drop_index(op.f("ix_report_artifacts_checksum"), table_name="report_artifacts")
    op.drop_table("report_artifacts")
