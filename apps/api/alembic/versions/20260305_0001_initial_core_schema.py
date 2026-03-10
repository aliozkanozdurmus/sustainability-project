"""Initial core schema

Revision ID: 20260305_0001
Revises:
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260305_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "reporting_framework_versions",
        sa.Column("framework_code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reporting_framework_versions")),
        sa.UniqueConstraint(
            "framework_code",
            "version",
            name=op.f("uq_reporting_framework_versions_framework_code"),
        ),
    )
    op.create_index(
        op.f("ix_reporting_framework_versions_framework_code"),
        "reporting_framework_versions",
        ["framework_code"],
        unique=False,
    )

    op.create_table(
        "memberships",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_memberships_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("tenant_id", "user_id", name=op.f("uq_memberships_tenant_id")),
    )
    op.create_index(op.f("ix_memberships_tenant_id"), "memberships", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("reporting_currency", sa.String(length=8), nullable=False),
        sa.Column("fiscal_year_start", sa.Date(), nullable=True),
        sa.Column("fiscal_year_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_projects_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("tenant_id", "code", name=op.f("uq_projects_tenant_id")),
    )
    op.create_index(op.f("ix_projects_tenant_id"), "projects", ["tenant_id"], unique=False)

    op.create_table(
        "source_documents",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_source_documents_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_source_documents_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_documents")),
    )
    op.create_index(op.f("ix_source_documents_checksum"), "source_documents", ["checksum"], unique=False)
    op.create_index(op.f("ix_source_documents_project_id"), "source_documents", ["project_id"], unique=False)
    op.create_index(op.f("ix_source_documents_tenant_id"), "source_documents", ["tenant_id"], unique=False)

    op.create_table(
        "extraction_records",
        sa.Column("source_document_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("extraction_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("extracted_text_uri", sa.String(length=1024), nullable=True),
        sa.Column("raw_payload_uri", sa.String(length=1024), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name=op.f("fk_extraction_records_source_document_id_source_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_records")),
    )
    op.create_index(op.f("ix_extraction_records_source_document_id"), "extraction_records", ["source_document_id"], unique=False)

    op.create_table(
        "chunks",
        sa.Column("source_document_id", sa.String(length=36), nullable=False),
        sa.Column("extraction_record_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section_label", sa.String(length=256), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["extraction_record_id"], ["extraction_records.id"], name=op.f("fk_chunks_extraction_record_id_extraction_records"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], name=op.f("fk_chunks_source_document_id_source_documents"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint("source_document_id", "chunk_index", name=op.f("uq_chunks_source_document_id")),
    )
    op.create_index(op.f("ix_chunks_extraction_record_id"), "chunks", ["extraction_record_id"], unique=False)
    op.create_index(op.f("ix_chunks_source_document_id"), "chunks", ["source_document_id"], unique=False)

    op.create_table(
        "embeddings",
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("vector_dim", sa.Integer(), nullable=False),
        sa.Column("vector_ref", sa.String(length=1024), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], name=op.f("fk_embeddings_chunk_id_chunks"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embeddings")),
        sa.UniqueConstraint("chunk_id", "model_name", name=op.f("uq_embeddings_chunk_id")),
    )
    op.create_index(op.f("ix_embeddings_chunk_id"), "embeddings", ["chunk_id"], unique=False)

    op.create_table(
        "report_runs",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("framework_version_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_ready", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["framework_version_id"], ["reporting_framework_versions.id"], name=op.f("fk_report_runs_framework_version_id_reporting_framework_versions"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_report_runs_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], name=op.f("fk_report_runs_requested_by_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_report_runs_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_runs")),
    )
    op.create_index(op.f("ix_report_runs_framework_version_id"), "report_runs", ["framework_version_id"], unique=False)
    op.create_index(op.f("ix_report_runs_project_id"), "report_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_report_runs_requested_by_user_id"), "report_runs", ["requested_by_user_id"], unique=False)
    op.create_index(op.f("ix_report_runs_tenant_id"), "report_runs", ["tenant_id"], unique=False)

    op.create_table(
        "retrieval_runs",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("report_run_id", sa.String(length=36), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("retrieval_mode", sa.String(length=32), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_retrieval_runs_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"], name=op.f("fk_retrieval_runs_report_run_id_report_runs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_retrieval_runs_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_runs")),
    )
    op.create_index(op.f("ix_retrieval_runs_project_id"), "retrieval_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_retrieval_runs_report_run_id"), "retrieval_runs", ["report_run_id"], unique=False)
    op.create_index(op.f("ix_retrieval_runs_tenant_id"), "retrieval_runs", ["tenant_id"], unique=False)

    op.create_table(
        "report_sections",
        sa.Column("report_run_id", sa.String(length=36), nullable=False),
        sa.Column("section_code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_uri", sa.String(length=1024), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"], name=op.f("fk_report_sections_report_run_id_report_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_sections")),
        sa.UniqueConstraint("report_run_id", "section_code", name=op.f("uq_report_sections_report_run_id")),
    )
    op.create_index(op.f("ix_report_sections_report_run_id"), "report_sections", ["report_run_id"], unique=False)

    op.create_table(
        "claims",
        sa.Column("report_section_id", sa.String(length=36), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_section_id"], ["report_sections.id"], name=op.f("fk_claims_report_section_id_report_sections"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claims")),
    )
    op.create_index(op.f("ix_claims_report_section_id"), "claims", ["report_section_id"], unique=False)

    op.create_table(
        "claim_citations",
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], name=op.f("fk_claim_citations_chunk_id_chunks"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], name=op.f("fk_claim_citations_claim_id_claims"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], name=op.f("fk_claim_citations_source_document_id_source_documents"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim_citations")),
        sa.UniqueConstraint("claim_id", "chunk_id", "span_start", "span_end", name=op.f("uq_claim_citations_claim_id")),
    )
    op.create_index(op.f("ix_claim_citations_chunk_id"), "claim_citations", ["chunk_id"], unique=False)
    op.create_index(op.f("ix_claim_citations_claim_id"), "claim_citations", ["claim_id"], unique=False)
    op.create_index(op.f("ix_claim_citations_source_document_id"), "claim_citations", ["source_document_id"], unique=False)

    op.create_table(
        "calculation_runs",
        sa.Column("report_run_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column("formula_name", sa.String(length=128), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("inputs_ref", sa.String(length=1024), nullable=False),
        sa.Column("output_value", sa.Float(), nullable=True),
        sa.Column("output_unit", sa.String(length=64), nullable=True),
        sa.Column("trace_log_ref", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], name=op.f("fk_calculation_runs_claim_id_claims"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"], name=op.f("fk_calculation_runs_report_run_id_report_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calculation_runs")),
    )
    op.create_index(op.f("ix_calculation_runs_claim_id"), "calculation_runs", ["claim_id"], unique=False)
    op.create_index(op.f("ix_calculation_runs_report_run_id"), "calculation_runs", ["report_run_id"], unique=False)

    op.create_table(
        "verification_results",
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("verifier_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], name=op.f("fk_verification_results_claim_id_claims"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_results")),
    )
    op.create_index(op.f("ix_verification_results_claim_id"), "verification_results", ["claim_id"], unique=False)
    op.create_index(op.f("ix_verification_results_status"), "verification_results", ["status"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("report_run_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_audit_events_actor_user_id_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_audit_events_project_id_projects"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"], name=op.f("fk_audit_events_report_run_id_report_runs"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_audit_events_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_actor_user_id"), "audit_events", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_audit_events_occurred_at"), "audit_events", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id"], unique=False)
    op.create_index(op.f("ix_audit_events_report_run_id"), "audit_events", ["report_run_id"], unique=False)
    op.create_index(op.f("ix_audit_events_tenant_id"), "audit_events", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_tenant_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_report_run_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_project_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_occurred_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_user_id"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_verification_results_status"), table_name="verification_results")
    op.drop_index(op.f("ix_verification_results_claim_id"), table_name="verification_results")
    op.drop_table("verification_results")

    op.drop_index(op.f("ix_calculation_runs_report_run_id"), table_name="calculation_runs")
    op.drop_index(op.f("ix_calculation_runs_claim_id"), table_name="calculation_runs")
    op.drop_table("calculation_runs")

    op.drop_index(op.f("ix_claim_citations_source_document_id"), table_name="claim_citations")
    op.drop_index(op.f("ix_claim_citations_claim_id"), table_name="claim_citations")
    op.drop_index(op.f("ix_claim_citations_chunk_id"), table_name="claim_citations")
    op.drop_table("claim_citations")

    op.drop_index(op.f("ix_claims_report_section_id"), table_name="claims")
    op.drop_table("claims")

    op.drop_index(op.f("ix_report_sections_report_run_id"), table_name="report_sections")
    op.drop_table("report_sections")

    op.drop_index(op.f("ix_retrieval_runs_tenant_id"), table_name="retrieval_runs")
    op.drop_index(op.f("ix_retrieval_runs_report_run_id"), table_name="retrieval_runs")
    op.drop_index(op.f("ix_retrieval_runs_project_id"), table_name="retrieval_runs")
    op.drop_table("retrieval_runs")

    op.drop_index(op.f("ix_report_runs_tenant_id"), table_name="report_runs")
    op.drop_index(op.f("ix_report_runs_requested_by_user_id"), table_name="report_runs")
    op.drop_index(op.f("ix_report_runs_project_id"), table_name="report_runs")
    op.drop_index(op.f("ix_report_runs_framework_version_id"), table_name="report_runs")
    op.drop_table("report_runs")

    op.drop_index(op.f("ix_embeddings_chunk_id"), table_name="embeddings")
    op.drop_table("embeddings")

    op.drop_index(op.f("ix_chunks_source_document_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_extraction_record_id"), table_name="chunks")
    op.drop_table("chunks")

    op.drop_index(op.f("ix_extraction_records_source_document_id"), table_name="extraction_records")
    op.drop_table("extraction_records")

    op.drop_index(op.f("ix_source_documents_tenant_id"), table_name="source_documents")
    op.drop_index(op.f("ix_source_documents_project_id"), table_name="source_documents")
    op.drop_index(op.f("ix_source_documents_checksum"), table_name="source_documents")
    op.drop_table("source_documents")

    op.drop_index(op.f("ix_projects_tenant_id"), table_name="projects")
    op.drop_table("projects")

    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_tenant_id"), table_name="memberships")
    op.drop_table("memberships")

    op.drop_index(
        op.f("ix_reporting_framework_versions_framework_code"),
        table_name="reporting_framework_versions",
    )
    op.drop_table("reporting_framework_versions")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_tenants_slug"), table_name="tenants")
    op.drop_table("tenants")

