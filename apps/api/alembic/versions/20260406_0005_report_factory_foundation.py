"""Add report factory, integrations, and package foundation tables.

Revision ID: 20260406_0005
Revises: 20260305_0004
Create Date: 2026-04-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260406_0005"
down_revision: Union[str, Sequence[str], None] = "20260305_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_profiles",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("headquarters", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("founded_year", sa.Integer(), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("ceo_name", sa.String(length=200), nullable=True),
        sa.Column("ceo_message", sa.Text(), nullable=True),
        sa.Column("sustainability_approach", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_profiles_project_id"), "company_profiles", ["project_id"], unique=False)
    op.create_index(op.f("ix_company_profiles_tenant_id"), "company_profiles", ["tenant_id"], unique=False)

    op.create_table(
        "brand_kits",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("brand_name", sa.String(length=200), nullable=False),
        sa.Column("logo_uri", sa.String(length=1024), nullable=True),
        sa.Column("primary_color", sa.String(length=16), nullable=False),
        sa.Column("secondary_color", sa.String(length=16), nullable=False),
        sa.Column("accent_color", sa.String(length=16), nullable=False),
        sa.Column("font_family_headings", sa.String(length=128), nullable=False),
        sa.Column("font_family_body", sa.String(length=128), nullable=False),
        sa.Column("tone_name", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brand_kits_project_id"), "brand_kits", ["project_id"], unique=False)
    op.create_index(op.f("ix_brand_kits_tenant_id"), "brand_kits", ["tenant_id"], unique=False)

    op.create_table(
        "report_blueprints",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blueprint_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version"),
    )
    op.create_index(op.f("ix_report_blueprints_project_id"), "report_blueprints", ["project_id"], unique=False)
    op.create_index(op.f("ix_report_blueprints_tenant_id"), "report_blueprints", ["tenant_id"], unique=False)

    op.create_table(
        "integration_configs",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("connector_type", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("auth_mode", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=1024), nullable=True),
        sa.Column("resource_path", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mapping_version", sa.String(length=64), nullable=False),
        sa.Column("connection_payload", sa.JSON(), nullable=True),
        sa.Column("sample_payload", sa.JSON(), nullable=True),
        sa.Column("last_cursor", sa.String(length=255), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_integration_configs_connector_type"), "integration_configs", ["connector_type"], unique=False)
    op.create_index(op.f("ix_integration_configs_project_id"), "integration_configs", ["project_id"], unique=False)
    op.create_index(op.f("ix_integration_configs_tenant_id"), "integration_configs", ["tenant_id"], unique=False)

    op.create_table(
        "connector_sync_jobs",
        sa.Column("integration_config_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_stage", sa.String(length=64), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("cursor_before", sa.String(length=255), nullable=True),
        sa.Column("cursor_after", sa.String(length=255), nullable=True),
        sa.Column("diagnostics_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_config_id"], ["integration_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_connector_sync_jobs_integration_config_id"), "connector_sync_jobs", ["integration_config_id"], unique=False)
    op.create_index(op.f("ix_connector_sync_jobs_project_id"), "connector_sync_jobs", ["project_id"], unique=False)
    op.create_index(op.f("ix_connector_sync_jobs_tenant_id"), "connector_sync_jobs", ["tenant_id"], unique=False)

    op.create_table(
        "canonical_facts",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("integration_config_id", sa.String(length=36), nullable=False),
        sa.Column("sync_job_id", sa.String(length=36), nullable=True),
        sa.Column("metric_code", sa.String(length=128), nullable=False),
        sa.Column("metric_name", sa.String(length=255), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("owner", sa.String(length=128), nullable=True),
        sa.Column("freshness_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("trace_ref", sa.String(length=1024), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_config_id"], ["integration_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_job_id"], ["connector_sync_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_config_id", "metric_code", "period_key", "source_record_id"),
    )
    op.create_index(op.f("ix_canonical_facts_integration_config_id"), "canonical_facts", ["integration_config_id"], unique=False)
    op.create_index(op.f("ix_canonical_facts_metric_code"), "canonical_facts", ["metric_code"], unique=False)
    op.create_index(op.f("ix_canonical_facts_period_key"), "canonical_facts", ["period_key"], unique=False)
    op.create_index(op.f("ix_canonical_facts_project_id"), "canonical_facts", ["project_id"], unique=False)
    op.create_index(op.f("ix_canonical_facts_sync_job_id"), "canonical_facts", ["sync_job_id"], unique=False)
    op.create_index(op.f("ix_canonical_facts_tenant_id"), "canonical_facts", ["tenant_id"], unique=False)

    op.create_table(
        "report_packages",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("report_run_id", sa.String(length=36), nullable=False),
        sa.Column("latest_sync_job_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_stage", sa.String(length=64), nullable=False),
        sa.Column("stage_history_json", sa.JSON(), nullable=True),
        sa.Column("package_quality_score", sa.Float(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["latest_sync_job_id"], ["connector_sync_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_run_id"),
    )
    op.create_index(op.f("ix_report_packages_latest_sync_job_id"), "report_packages", ["latest_sync_job_id"], unique=False)
    op.create_index(op.f("ix_report_packages_project_id"), "report_packages", ["project_id"], unique=False)
    op.create_index(op.f("ix_report_packages_report_run_id"), "report_packages", ["report_run_id"], unique=False)
    op.create_index(op.f("ix_report_packages_tenant_id"), "report_packages", ["tenant_id"], unique=False)

    op.create_table(
        "report_visual_assets",
        sa.Column("report_package_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("visual_slot", sa.String(length=64), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("decorative_ai_generated", sa.Boolean(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("storage_uri", sa.String(length=1024), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_package_id"], ["report_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_package_id", "visual_slot"),
    )
    op.create_index(op.f("ix_report_visual_assets_project_id"), "report_visual_assets", ["project_id"], unique=False)
    op.create_index(op.f("ix_report_visual_assets_report_package_id"), "report_visual_assets", ["report_package_id"], unique=False)
    op.create_index(op.f("ix_report_visual_assets_tenant_id"), "report_visual_assets", ["tenant_id"], unique=False)

    op.create_table(
        "kpi_snapshots",
        sa.Column("report_run_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("metric_code", sa.String(length=128), nullable=False),
        sa.Column("metric_name", sa.String(length=255), nullable=False),
        sa.Column("period_key", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("quality_grade", sa.String(length=16), nullable=False),
        sa.Column("freshness_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_fact_ids", sa.JSON(), nullable=True),
        sa.Column("snapshot_metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_run_id", "metric_code", "period_key"),
    )
    op.create_index(op.f("ix_kpi_snapshots_metric_code"), "kpi_snapshots", ["metric_code"], unique=False)
    op.create_index(op.f("ix_kpi_snapshots_project_id"), "kpi_snapshots", ["project_id"], unique=False)
    op.create_index(op.f("ix_kpi_snapshots_report_run_id"), "kpi_snapshots", ["report_run_id"], unique=False)
    op.create_index(op.f("ix_kpi_snapshots_tenant_id"), "kpi_snapshots", ["tenant_id"], unique=False)

    with op.batch_alter_table("report_runs") as batch_op:
        batch_op.add_column(sa.Column("company_profile_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("brand_kit_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("report_blueprint_version", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("connector_scope", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("package_status", sa.String(length=32), nullable=False, server_default="not_started"))
        batch_op.add_column(sa.Column("report_quality_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("latest_sync_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("visual_generation_status", sa.String(length=32), nullable=False, server_default="not_started"))
        batch_op.create_index(op.f("ix_report_runs_company_profile_id"), ["company_profile_id"], unique=False)
        batch_op.create_index(op.f("ix_report_runs_brand_kit_id"), ["brand_kit_id"], unique=False)
        batch_op.create_foreign_key(op.f("fk_report_runs_company_profile_id_company_profiles"), "company_profiles", ["company_profile_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key(op.f("fk_report_runs_brand_kit_id_brand_kits"), "brand_kits", ["brand_kit_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("report_artifacts") as batch_op:
        batch_op.add_column(sa.Column("report_package_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("artifact_metadata_json", sa.JSON(), nullable=True))
        batch_op.create_index(op.f("ix_report_artifacts_report_package_id"), ["report_package_id"], unique=False)
        batch_op.create_foreign_key(op.f("fk_report_artifacts_report_package_id_report_packages"), "report_packages", ["report_package_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("report_artifacts") as batch_op:
        batch_op.drop_constraint(op.f("fk_report_artifacts_report_package_id_report_packages"), type_="foreignkey")
        batch_op.drop_index(op.f("ix_report_artifacts_report_package_id"))
        batch_op.drop_column("artifact_metadata_json")
        batch_op.drop_column("report_package_id")

    with op.batch_alter_table("report_runs") as batch_op:
        batch_op.drop_constraint(op.f("fk_report_runs_brand_kit_id_brand_kits"), type_="foreignkey")
        batch_op.drop_constraint(op.f("fk_report_runs_company_profile_id_company_profiles"), type_="foreignkey")
        batch_op.drop_index(op.f("ix_report_runs_brand_kit_id"))
        batch_op.drop_index(op.f("ix_report_runs_company_profile_id"))
        batch_op.drop_column("visual_generation_status")
        batch_op.drop_column("latest_sync_at")
        batch_op.drop_column("report_quality_score")
        batch_op.drop_column("package_status")
        batch_op.drop_column("connector_scope")
        batch_op.drop_column("report_blueprint_version")
        batch_op.drop_column("brand_kit_id")
        batch_op.drop_column("company_profile_id")

    op.drop_index(op.f("ix_kpi_snapshots_tenant_id"), table_name="kpi_snapshots")
    op.drop_index(op.f("ix_kpi_snapshots_report_run_id"), table_name="kpi_snapshots")
    op.drop_index(op.f("ix_kpi_snapshots_project_id"), table_name="kpi_snapshots")
    op.drop_index(op.f("ix_kpi_snapshots_metric_code"), table_name="kpi_snapshots")
    op.drop_table("kpi_snapshots")

    op.drop_index(op.f("ix_report_visual_assets_tenant_id"), table_name="report_visual_assets")
    op.drop_index(op.f("ix_report_visual_assets_report_package_id"), table_name="report_visual_assets")
    op.drop_index(op.f("ix_report_visual_assets_project_id"), table_name="report_visual_assets")
    op.drop_table("report_visual_assets")

    op.drop_index(op.f("ix_report_packages_tenant_id"), table_name="report_packages")
    op.drop_index(op.f("ix_report_packages_report_run_id"), table_name="report_packages")
    op.drop_index(op.f("ix_report_packages_project_id"), table_name="report_packages")
    op.drop_index(op.f("ix_report_packages_latest_sync_job_id"), table_name="report_packages")
    op.drop_table("report_packages")

    op.drop_index(op.f("ix_canonical_facts_tenant_id"), table_name="canonical_facts")
    op.drop_index(op.f("ix_canonical_facts_sync_job_id"), table_name="canonical_facts")
    op.drop_index(op.f("ix_canonical_facts_project_id"), table_name="canonical_facts")
    op.drop_index(op.f("ix_canonical_facts_period_key"), table_name="canonical_facts")
    op.drop_index(op.f("ix_canonical_facts_metric_code"), table_name="canonical_facts")
    op.drop_index(op.f("ix_canonical_facts_integration_config_id"), table_name="canonical_facts")
    op.drop_table("canonical_facts")

    op.drop_index(op.f("ix_connector_sync_jobs_tenant_id"), table_name="connector_sync_jobs")
    op.drop_index(op.f("ix_connector_sync_jobs_project_id"), table_name="connector_sync_jobs")
    op.drop_index(op.f("ix_connector_sync_jobs_integration_config_id"), table_name="connector_sync_jobs")
    op.drop_table("connector_sync_jobs")

    op.drop_index(op.f("ix_integration_configs_tenant_id"), table_name="integration_configs")
    op.drop_index(op.f("ix_integration_configs_project_id"), table_name="integration_configs")
    op.drop_index(op.f("ix_integration_configs_connector_type"), table_name="integration_configs")
    op.drop_table("integration_configs")

    op.drop_index(op.f("ix_report_blueprints_tenant_id"), table_name="report_blueprints")
    op.drop_index(op.f("ix_report_blueprints_project_id"), table_name="report_blueprints")
    op.drop_table("report_blueprints")

    op.drop_index(op.f("ix_brand_kits_tenant_id"), table_name="brand_kits")
    op.drop_index(op.f("ix_brand_kits_project_id"), table_name="brand_kits")
    op.drop_table("brand_kits")

    op.drop_index(op.f("ix_company_profiles_tenant_id"), table_name="company_profiles")
    op.drop_index(op.f("ix_company_profiles_project_id"), table_name="company_profiles")
    op.drop_table("company_profiles")
