from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class IdTimestampMixin:
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        onupdate=now_utc,
        nullable=False,
    )


class Tenant(IdTimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class User(IdTimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Membership(IdTimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)


class Project(IdTimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    reporting_currency: Mapped[str] = mapped_column(String(8), default="TRY", nullable=False)
    fiscal_year_start: Mapped[date | None] = mapped_column(Date)
    fiscal_year_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class ReportingFrameworkVersion(IdTimestampMixin, Base):
    __tablename__ = "reporting_framework_versions"
    __table_args__ = (UniqueConstraint("framework_code", "version"),)

    framework_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)


class SourceDocument(IdTimestampMixin, Base):
    __tablename__ = "source_documents"

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), index=True)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False)


class ExtractionRecord(IdTimestampMixin, Base):
    __tablename__ = "extraction_records"

    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    extraction_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float)
    extracted_text_uri: Mapped[str | None] = mapped_column(String(1024))
    raw_payload_uri: Mapped[str | None] = mapped_column(String(1024))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class Chunk(IdTimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("source_document_id", "chunk_index"),)

    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extraction_record_id: Mapped[str | None] = mapped_column(
        ForeignKey("extraction_records.id", ondelete="SET NULL"),
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    section_label: Mapped[str | None] = mapped_column(String(256))
    token_count: Mapped[int | None] = mapped_column(Integer)


class Embedding(IdTimestampMixin, Base):
    __tablename__ = "embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", "model_name"),)

    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    vector_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_ref: Mapped[str] = mapped_column(String(1024), nullable=False)


class ReportRun(IdTimestampMixin, Base):
    __tablename__ = "report_runs"

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    framework_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("reporting_framework_versions.id", ondelete="SET NULL"),
        index=True,
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ReportArtifact(IdTimestampMixin, Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (UniqueConstraint("report_run_id", "artifact_type"),)

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_run_id: Mapped[str] = mapped_column(
        ForeignKey("report_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


class RetrievalRun(IdTimestampMixin, Base):
    __tablename__ = "retrieval_runs"

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("report_runs.id", ondelete="SET NULL"),
        index=True,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(32), default="hybrid", nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    result_count: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )


class ReportSection(IdTimestampMixin, Base):
    __tablename__ = "report_sections"
    __table_args__ = (UniqueConstraint("report_run_id", "section_code"),)

    report_run_id: Mapped[str] = mapped_column(
        ForeignKey("report_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_code: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    content_uri: Mapped[str | None] = mapped_column(String(1024))
    ordinal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Claim(IdTimestampMixin, Base):
    __tablename__ = "claims"

    report_section_id: Mapped[str] = mapped_column(
        ForeignKey("report_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)


class ClaimCitation(IdTimestampMixin, Base):
    __tablename__ = "claim_citations"
    __table_args__ = (UniqueConstraint("claim_id", "chunk_id", "span_start", "span_end"),)

    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)


class CalculationRun(IdTimestampMixin, Base):
    __tablename__ = "calculation_runs"

    report_run_id: Mapped[str] = mapped_column(
        ForeignKey("report_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[str | None] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"),
        index=True,
    )
    formula_name: Mapped[str] = mapped_column(String(128), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    inputs_ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    output_value: Mapped[float | None] = mapped_column(Float)
    output_unit: Mapped[str | None] = mapped_column(String(64))
    trace_log_ref: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )


class VerificationResult(IdTimestampMixin, Base):
    __tablename__ = "verification_results"
    __table_args__ = (
        UniqueConstraint("claim_id", "run_execution_id"),
        Index(
            "ix_verification_results_report_attempt_status_checked_at",
            "report_run_id",
            "run_attempt",
            "status",
            "checked_at",
        ),
    )

    report_run_id: Mapped[str] = mapped_column(
        ForeignKey("report_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_execution_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    verifier_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
    )


class AuditEvent(IdTimestampMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index(
            "ix_audit_events_report_event_occurred_at",
            "report_run_id",
            "event_type",
            "event_name",
            "occurred_at",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        index=True,
    )
    report_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("report_runs.id", ondelete="SET NULL"),
        index=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_payload: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        nullable=False,
        index=True,
    )
