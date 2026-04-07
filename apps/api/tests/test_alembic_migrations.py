# Bu test dosyasi, alembic migrations davranisini dogrular.

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import VerificationResult


API_ROOT = Path(__file__).resolve().parents[1]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    return config


def _seed_pre_migration_verification_row(engine: sa.Engine) -> None:
    now = _utc_now()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO tenants (id, name, slug, status, created_at, updated_at)
                VALUES (:id, :name, :slug, :status, :created_at, :updated_at)
                """
            ),
            {
                "id": "ten_1",
                "name": "Tenant 1",
                "slug": "tenant-1",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO users (id, email, full_name, is_active, created_at, updated_at)
                VALUES (:id, :email, :full_name, :is_active, :created_at, :updated_at)
                """
            ),
            {
                "id": "usr_1",
                "email": "owner@example.com",
                "full_name": "Owner",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO reporting_framework_versions
                    (id, framework_code, version, effective_date, is_active, metadata_json, created_at, updated_at)
                VALUES
                    (:id, :framework_code, :version, :effective_date, :is_active, :metadata_json, :created_at, :updated_at)
                """
            ),
            {
                "id": "frw_1",
                "framework_code": "TSRS2",
                "version": "2026",
                "effective_date": date(2026, 1, 1),
                "is_active": True,
                "metadata_json": "{}",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO projects
                    (id, tenant_id, name, code, reporting_currency, fiscal_year_start, fiscal_year_end, status, created_at, updated_at)
                VALUES
                    (:id, :tenant_id, :name, :code, :reporting_currency, :fiscal_year_start, :fiscal_year_end, :status, :created_at, :updated_at)
                """
            ),
            {
                "id": "prj_1",
                "tenant_id": "ten_1",
                "name": "Project 1",
                "code": "P1",
                "reporting_currency": "TRY",
                "fiscal_year_start": date(2026, 1, 1),
                "fiscal_year_end": date(2026, 12, 31),
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO report_runs
                    (id, tenant_id, project_id, framework_version_id, requested_by_user_id, status, started_at, completed_at, publish_ready, created_at, updated_at)
                VALUES
                    (:id, :tenant_id, :project_id, :framework_version_id, :requested_by_user_id, :status, :started_at, :completed_at, :publish_ready, :created_at, :updated_at)
                """
            ),
            {
                "id": "run_1",
                "tenant_id": "ten_1",
                "project_id": "prj_1",
                "framework_version_id": "frw_1",
                "requested_by_user_id": "usr_1",
                "status": "draft",
                "started_at": now,
                "completed_at": None,
                "publish_ready": False,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO report_sections
                    (id, report_run_id, section_code, title, status, content_uri, ordinal, created_at, updated_at)
                VALUES
                    (:id, :report_run_id, :section_code, :title, :status, :content_uri, :ordinal, :created_at, :updated_at)
                """
            ),
            {
                "id": "sec_1",
                "report_run_id": "run_1",
                "section_code": "TSRS2-CLIMATE",
                "title": "Climate",
                "status": "draft",
                "content_uri": None,
                "ordinal": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO claims
                    (id, report_section_id, statement, confidence, status, created_at, updated_at)
                VALUES
                    (:id, :report_section_id, :statement, :confidence, :status, :created_at, :updated_at)
                """
            ),
            {
                "id": "clm_1",
                "report_section_id": "sec_1",
                "statement": "Sample claim.",
                "confidence": 0.95,
                "status": "draft",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO verification_results
                    (id, claim_id, verifier_version, status, reason, severity, confidence, checked_at, created_at, updated_at)
                VALUES
                    (:id, :claim_id, :verifier_version, :status, :reason, :severity, :confidence, :checked_at, :created_at, :updated_at)
                """
            ),
            {
                "id": "ver_1",
                "claim_id": "clm_1",
                "verifier_version": "legacy-v1",
                "status": "PASS",
                "reason": "Legacy verifier support.",
                "severity": "normal",
                "confidence": 0.91,
                "checked_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )


def test_alembic_verification_results_run_context_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "migration_verification.db"
    database_url = f"sqlite:///{db_path.as_posix()}"
    config = _alembic_config()

    original_database_url = settings.database_url
    settings.database_url = database_url
    try:
        command.upgrade(config, "20260305_0001")

        engine = sa.create_engine(database_url)
        _seed_pre_migration_verification_row(engine)

        command.upgrade(config, "20260305_0004")

        inspector = sa.inspect(engine)
        column_map = {column["name"]: column for column in inspector.get_columns("verification_results")}
        assert column_map["report_run_id"]["nullable"] is False
        assert column_map["run_execution_id"]["nullable"] is False
        assert column_map["run_attempt"]["nullable"] is False

        index_names = {index["name"] for index in inspector.get_indexes("verification_results")}
        assert "ix_verification_results_report_run_id" in index_names
        assert "ix_verification_results_run_execution_id" in index_names
        assert "ix_verification_results_report_attempt_status_checked_at" in index_names

        audit_index_names = {index["name"] for index in inspector.get_indexes("audit_events")}
        assert "ix_audit_events_report_event_occurred_at" in audit_index_names

        report_artifact_columns = {column["name"] for column in inspector.get_columns("report_artifacts")}
        assert {"tenant_id", "project_id", "report_run_id", "artifact_type", "filename", "storage_uri"} <= report_artifact_columns
        report_artifact_indexes = {index["name"] for index in inspector.get_indexes("report_artifacts")}
        assert "ix_report_artifacts_report_run_id" in report_artifact_indexes
        report_artifact_unique_sets = {
            tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("report_artifacts")
        }
        assert ("report_run_id", "artifact_type") in report_artifact_unique_sets

        unique_sets = {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("verification_results")}
        assert ("claim_id", "run_execution_id") in unique_sets

        with Session(engine) as session:
            migrated_row = session.get(VerificationResult, "ver_1")
            assert migrated_row is not None
            assert migrated_row.report_run_id == "run_1"
            assert migrated_row.run_execution_id == "legacy_ver_1"
            assert migrated_row.run_attempt == 1

            duplicate = VerificationResult(
                id="ver_2",
                report_run_id="run_1",
                claim_id="clm_1",
                run_execution_id="legacy_ver_1",
                run_attempt=1,
                verifier_version="v2",
                status="PASS",
                reason="duplicate check",
                severity="normal",
                confidence=0.5,
                checked_at=_utc_now(),
            )
            session.add(duplicate)
            with pytest.raises(sa.exc.IntegrityError):
                session.commit()
            session.rollback()

        command.downgrade(config, "20260305_0003")
        downgraded_artifact_tables = sa.inspect(engine).get_table_names()
        assert "report_artifacts" not in downgraded_artifact_tables

        command.downgrade(config, "20260305_0002")
        downgraded_once = sa.inspect(engine)
        downgraded_once_indexes = {index["name"] for index in downgraded_once.get_indexes("verification_results")}
        assert "ix_verification_results_report_attempt_status_checked_at" not in downgraded_once_indexes
        downgraded_once_audit_indexes = {index["name"] for index in downgraded_once.get_indexes("audit_events")}
        assert "ix_audit_events_report_event_occurred_at" not in downgraded_once_audit_indexes

        command.downgrade(config, "20260305_0001")
        downgraded_columns = {column["name"] for column in sa.inspect(engine).get_columns("verification_results")}
        assert "report_run_id" not in downgraded_columns
        assert "run_execution_id" not in downgraded_columns
        assert "run_attempt" not in downgraded_columns
    finally:
        settings.database_url = original_database_url
