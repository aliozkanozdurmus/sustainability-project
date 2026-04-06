from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.core import (
    Claim,
    ExtractionRecord,
    Project,
    ReportArtifact,
    ReportPackage,
    ReportRun,
    ReportSection,
    SourceDocument,
    Tenant,
    VerificationResult,
)
from app.services.integrations import run_connector_sync
from app.services.report_context import apply_report_factory_configuration, ensure_project_report_context


def _seed_tenant_and_project(db: Session) -> tuple[Tenant, Project]:
    tenant = Tenant(name="Dashboard Tenant", slug="dashboard-tenant")
    db.add(tenant)
    db.flush()

    project = Project(
        tenant_id=tenant.id,
        name="Dashboard Project",
        code="DASH-1",
        reporting_currency="TRY",
    )
    db.add(project)
    db.flush()
    return tenant, project


def _seed_report_factory_context(db: Session, *, tenant: Tenant, project: Project) -> None:
    company_profile, brand_kit, _blueprint, integrations = ensure_project_report_context(
        db=db,
        tenant=tenant,
        project=project,
    )
    apply_report_factory_configuration(
        db=db,
        company_profile=company_profile,
        brand_kit=brand_kit,
        company_profile_payload={
            "legal_name": "Dashboard Holding",
            "sector": "Industrial Manufacturing",
            "headquarters": "Istanbul",
            "description": "Live dashboard context for report factory coverage.",
            "ceo_name": "Taylor Quinn",
            "ceo_message": "We track ESG performance through auditable systems.",
            "sustainability_approach": "Evidence first, package later.",
        },
        brand_kit_payload={
            "brand_name": "Dashboard Holding",
            "logo_uri": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='80'><rect width='240' height='80' rx='18' fill='%23262421'/><text x='120' y='50' text-anchor='middle' fill='white' font-size='24'>DH</text></svg>",
            "primary_color": "#e4c764",
            "secondary_color": "#262421",
            "accent_color": "#d2b24a",
            "font_family_headings": "Inter",
            "font_family_body": "Inter",
            "tone_name": "editorial-corporate",
        },
    )
    for integration in integrations:
        run_connector_sync(db=db, integration=integration)
    db.flush()


def test_dashboard_overview_returns_live_aggregate_payload(tmp_path: Path) -> None:
    db_file = tmp_path / "test_dashboard_overview.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant, project = _seed_tenant_and_project(session)
            _seed_report_factory_context(session, tenant=tenant, project=project)

            published_run = ReportRun(
                tenant_id=tenant.id,
                project_id=project.id,
                status="published",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                publish_ready=True,
                package_status="completed",
                report_quality_score=91.4,
                latest_sync_at=datetime.now(timezone.utc),
                visual_generation_status="completed",
                report_blueprint_version="factory-v1",
            )
            running_run = ReportRun(
                tenant_id=tenant.id,
                project_id=project.id,
                status="running",
                started_at=datetime.now(timezone.utc),
                publish_ready=False,
                package_status="running",
                report_quality_score=78.2,
                latest_sync_at=datetime.now(timezone.utc),
                visual_generation_status="running",
                report_blueprint_version="factory-v1",
            )
            session.add_all([published_run, running_run])
            session.flush()

            session.add(
                ReportPackage(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    report_run_id=running_run.id,
                    status="running",
                    current_stage="compose",
                    stage_history_json=[],
                    started_at=datetime.now(timezone.utc),
                )
            )
            session.add_all(
                [
                    ReportArtifact(
                        tenant_id=tenant.id,
                        project_id=project.id,
                        report_run_id=published_run.id,
                        artifact_type="report_pdf",
                        filename="report.pdf",
                        content_type="application/pdf",
                        storage_uri="obj://report.pdf",
                        size_bytes=2048,
                        checksum="sha256:pdf",
                    ),
                    ReportArtifact(
                        tenant_id=tenant.id,
                        project_id=project.id,
                        report_run_id=published_run.id,
                        artifact_type="citation_index",
                        filename="citation-index.json",
                        content_type="application/json",
                        storage_uri="obj://citation-index.json",
                        size_bytes=512,
                        checksum="sha256:citation",
                    ),
                ]
            )

            document = SourceDocument(
                tenant_id=tenant.id,
                project_id=project.id,
                document_type="energy_invoice",
                filename="energy-2025.pdf",
                storage_uri="obj://energy-2025.pdf",
                checksum="sha256:doc",
                status="uploaded",
            )
            session.add(document)
            session.flush()
            session.add(
                ExtractionRecord(
                    source_document_id=document.id,
                    provider="azure-document-intelligence",
                    extraction_mode="ocr",
                    status="completed",
                    quality_score=96.0,
                )
            )
            section = ReportSection(
                report_run_id=running_run.id,
                section_code="ENVIRONMENT",
                title="Environmental Performance",
                status="draft",
                ordinal=1,
            )
            session.add(section)
            session.flush()
            claim = Claim(
                report_section_id=section.id,
                statement="Scope 2 emissions decreased year over year.",
                confidence=0.92,
                status="draft",
            )
            session.add(claim)
            session.flush()
            session.add(
                VerificationResult(
                    report_run_id=running_run.id,
                    claim_id=claim.id,
                    run_execution_id="exec-dashboard-1",
                    run_attempt=1,
                    status="FAIL",
                    reason="Missing citation evidence",
                    severity="critical",
                )
            )
            session.commit()

            tenant_id = tenant.id
            project_id = project.id

        response = client.get(
            f"/dashboard/overview?tenant_id={tenant_id}&project_id={project_id}",
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["hero"]["company_name"] == "Dashboard Holding"
        assert payload["hero"]["readiness_label"] == "Factory ready"
        assert len(payload["metrics"]) >= 4
        assert len(payload["connector_health"]) == 3
        assert any(item["artifact_type"] == "report_pdf" and item["available"] == 1 for item in payload["artifact_health"])
        assert any(item["title"] == "Verifier triage pressure" for item in payload["risks"])
        assert len(payload["run_queue"]) == 2
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
