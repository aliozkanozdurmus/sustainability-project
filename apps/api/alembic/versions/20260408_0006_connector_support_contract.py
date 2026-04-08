"""Add connector support contract, operations, and agent tracking.

Revision ID: 20260408_0006
Revises: 20260406_0005
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260408_0006"
down_revision: Union[str, Sequence[str], None] = "20260406_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connector_agents",
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("agent_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("agent_kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("supported_connectors_json", sa.JSON(), nullable=True),
        sa.Column("capabilities_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("heartbeat_payload_json", sa.JSON(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_key"),
    )
    op.create_index(op.f("ix_connector_agents_agent_key"), "connector_agents", ["agent_key"], unique=False)
    op.create_index(op.f("ix_connector_agents_project_id"), "connector_agents", ["project_id"], unique=False)
    op.create_index(op.f("ix_connector_agents_tenant_id"), "connector_agents", ["tenant_id"], unique=False)

    with op.batch_alter_table("integration_configs") as batch_op:
        batch_op.add_column(sa.Column("certified_variant", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("product_version", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("support_tier", sa.String(length=32), nullable=False, server_default="beta"))
        batch_op.add_column(sa.Column("connectivity_mode", sa.String(length=64), nullable=False, server_default="customer_network_agent"))
        batch_op.add_column(sa.Column("credential_ref", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("health_band", sa.String(length=16), nullable=False, server_default="red"))
        batch_op.add_column(sa.Column("health_status_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("assigned_agent_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("normalization_policy_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_preflight_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_preview_sync_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(op.f("ix_integration_configs_assigned_agent_id"), ["assigned_agent_id"], unique=False)
        batch_op.create_foreign_key(
            op.f("fk_integration_configs_assigned_agent_id_connector_agents"),
            "connector_agents",
            ["assigned_agent_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "connector_operation_runs",
        sa.Column("integration_config_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_agent_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("connector_type", sa.String(length=64), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("replay_mode", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_stage", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("operator_message", sa.Text(), nullable=True),
        sa.Column("support_hint", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("result_payload_json", sa.JSON(), nullable=True),
        sa.Column("diagnostics_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["connector_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["integration_config_id"], ["integration_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_connector_operation_runs_assigned_agent_id"), "connector_operation_runs", ["assigned_agent_id"], unique=False)
    op.create_index(op.f("ix_connector_operation_runs_integration_config_id"), "connector_operation_runs", ["integration_config_id"], unique=False)
    op.create_index(op.f("ix_connector_operation_runs_project_id"), "connector_operation_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_connector_operation_runs_requested_by_user_id"), "connector_operation_runs", ["requested_by_user_id"], unique=False)
    op.create_index(op.f("ix_connector_operation_runs_tenant_id"), "connector_operation_runs", ["tenant_id"], unique=False)

    op.create_table(
        "connector_artifacts",
        sa.Column("integration_config_id", sa.String(length=36), nullable=False),
        sa.Column("connector_operation_run_id", sa.String(length=36), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("artifact_metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connector_operation_run_id"], ["connector_operation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["integration_config_id"], ["integration_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_connector_artifacts_connector_operation_run_id"), "connector_artifacts", ["connector_operation_run_id"], unique=False)
    op.create_index(op.f("ix_connector_artifacts_integration_config_id"), "connector_artifacts", ["integration_config_id"], unique=False)
    op.create_index(op.f("ix_connector_artifacts_project_id"), "connector_artifacts", ["project_id"], unique=False)
    op.create_index(op.f("ix_connector_artifacts_tenant_id"), "connector_artifacts", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_connector_artifacts_tenant_id"), table_name="connector_artifacts")
    op.drop_index(op.f("ix_connector_artifacts_project_id"), table_name="connector_artifacts")
    op.drop_index(op.f("ix_connector_artifacts_integration_config_id"), table_name="connector_artifacts")
    op.drop_index(op.f("ix_connector_artifacts_connector_operation_run_id"), table_name="connector_artifacts")
    op.drop_table("connector_artifacts")

    op.drop_index(op.f("ix_connector_operation_runs_tenant_id"), table_name="connector_operation_runs")
    op.drop_index(op.f("ix_connector_operation_runs_requested_by_user_id"), table_name="connector_operation_runs")
    op.drop_index(op.f("ix_connector_operation_runs_project_id"), table_name="connector_operation_runs")
    op.drop_index(op.f("ix_connector_operation_runs_integration_config_id"), table_name="connector_operation_runs")
    op.drop_index(op.f("ix_connector_operation_runs_assigned_agent_id"), table_name="connector_operation_runs")
    op.drop_table("connector_operation_runs")

    with op.batch_alter_table("integration_configs") as batch_op:
        batch_op.drop_constraint(op.f("fk_integration_configs_assigned_agent_id_connector_agents"), type_="foreignkey")
        batch_op.drop_index(op.f("ix_integration_configs_assigned_agent_id"))
        batch_op.drop_column("last_preview_sync_at")
        batch_op.drop_column("last_preflight_at")
        batch_op.drop_column("last_discovered_at")
        batch_op.drop_column("normalization_policy_json")
        batch_op.drop_column("assigned_agent_id")
        batch_op.drop_column("health_status_json")
        batch_op.drop_column("health_band")
        batch_op.drop_column("credential_ref")
        batch_op.drop_column("connectivity_mode")
        batch_op.drop_column("support_tier")
        batch_op.drop_column("product_version")
        batch_op.drop_column("certified_variant")

    op.drop_index(op.f("ix_connector_agents_tenant_id"), table_name="connector_agents")
    op.drop_index(op.f("ix_connector_agents_project_id"), table_name="connector_agents")
    op.drop_index(op.f("ix_connector_agents_agent_key"), table_name="connector_agents")
    op.drop_table("connector_agents")
