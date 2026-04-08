# Bu test dosyasi, runs davranisini dogrular.

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pdfplumber
from pypdf import PdfReader
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.core import (
    AuditEvent,
    CalculationRun,
    Claim,
    ClaimCitation,
    Chunk,
    IntegrationConfig,
    Project,
    ReportArtifact,
    ReportRun,
    ReportSection,
    SourceDocument,
    Tenant,
    VerificationResult,
)
from app.api.routes.runs import VERIFIER_VERSION, _persist_verification_artifacts
from app.orchestration.checkpoint_store import LocalJsonlCheckpointStore
from app.services.job_queue import get_job_queue_service
from app.services.integrations import run_connector_sync
from app.services.report_context import apply_report_factory_configuration, ensure_project_report_context
from app.services.report_factory import REPORT_PDF_ARTIFACT_TYPE


def _seed_tenant_and_project(db: Session) -> tuple[str, str]:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()

    project = Project(
        tenant_id=tenant.id,
        name="Project A",
        code="PRJ-A",
        reporting_currency="TRY",
    )
    db.add(project)
    db.commit()
    return tenant.id, project.id


def _seed_report_factory_context(
    db: Session,
    *,
    tenant_id: str,
    project_id: str,
    connector_types: set[str] | None = None,
) -> tuple[list[str], str, str, str]:
    tenant = db.get(Tenant, tenant_id)
    project = db.get(Project, project_id)
    assert tenant is not None
    assert project is not None

    company_profile, brand_kit, blueprint, integrations = ensure_project_report_context(
        db=db,
        tenant=tenant,
        project=project,
    )
    apply_report_factory_configuration(
        db=db,
        company_profile=company_profile,
        brand_kit=brand_kit,
        company_profile_payload={
            "legal_name": project.name,
            "sector": "Ambalaj ve endustriyel uretim",
            "headquarters": "Istanbul, Turkiye",
            "description": "Denetlenebilir ESG veri katmanini kurumsal rapora donusturen test sirketi.",
            "ceo_name": "Test CEO",
            "ceo_message": "Surdurulebilirlik performansi veri ve yonetisim disipliniyle yonetilir.",
            "sustainability_approach": "Olculebilir ve izlenebilir raporlama modeli uygulanir.",
        },
        brand_kit_payload={
            "brand_name": tenant.name,
            "logo_uri": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='80'><rect width='240' height='80' rx='16' fill='%230c4a6e'/><text x='120' y='50' font-size='28' text-anchor='middle' fill='white'>TEST</text></svg>",
            "primary_color": "#f07f13",
            "secondary_color": "#0c4a6e",
            "accent_color": "#7ab648",
            "font_family_headings": "Segoe UI Semibold",
            "font_family_body": "Segoe UI",
            "tone_name": "kurumsal-guvenilir",
        },
    )
    selected_connector_types: list[str] = []
    for integration in integrations:
        if connector_types and integration.connector_type not in connector_types:
            continue
        run_connector_sync(db=db, integration=integration)
        selected_connector_types.append(integration.connector_type)

    db.flush()
    return (
        selected_connector_types,
        company_profile.id,
        brand_kit.id,
        blueprint.version,
    )


def _write_local_index(root: Path, index_name: str, rows: dict[str, dict[str, object]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{index_name}.json"
    target.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")


def _collect_outline_titles(items: list[object]) -> list[str]:
    titles: list[str] = []
    for item in items:
        if isinstance(item, list):
            titles.extend(_collect_outline_titles(item))
            continue
        title = getattr(item, "title", None)
        if isinstance(title, str) and title:
            titles.append(title)
    return titles


class _StubQueueService:
    def __init__(self) -> None:
        self.enqueued_packages: list[tuple[str, str | None]] = []

    async def enqueue_extraction(self, extraction_id: str) -> str:
        return f"queue-extract-{extraction_id}"

    async def enqueue_report_package(self, report_run_id: str, *, package_job_id: str | None = None) -> str:
        self.enqueued_packages.append((report_run_id, package_job_id))
        return package_job_id or f"pkg-{report_run_id}"


def _finalize_package_as_worker(db: Session, run_id: str) -> None:
    from app.services.report_factory import ensure_report_package as generate_report_package

    report_run = db.get(ReportRun, run_id)
    assert report_run is not None
    package_result = generate_report_package(db=db, report_run=report_run)
    report_run.status = "published"
    report_run.publish_ready = True
    if report_run.completed_at is None:
        report_run.completed_at = datetime.now(timezone.utc)
    report_pdf = next(
        (
            artifact
            for artifact in package_result.artifacts
            if artifact.artifact_type == REPORT_PDF_ARTIFACT_TYPE
        ),
        None,
    )
    db.add(
        AuditEvent(
            tenant_id=report_run.tenant_id,
            project_id=report_run.project_id,
            report_run_id=report_run.id,
            event_type="publish",
            event_name="publish_completed",
            event_payload={
                "schema_version": "publish_gate_v1",
                "run_id": run_id,
                "blocked": False,
                "published": True,
                "package_job_id": package_result.package.id,
                "package_status": package_result.package.status,
                "report_pdf": {
                    "artifact_id": report_pdf.id,
                    "artifact_type": report_pdf.artifact_type,
                    "filename": report_pdf.filename,
                }
                if report_pdf is not None
                else None,
            },
        )
    )
    db.commit()


def test_create_run_initializes_report_run_and_checkpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_create.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2", "CSRD"],
                "active_reg_pack_version": "v2026.1",
                "scope_decision": {"mode": "one_click"},
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["run_id"]
        assert body["report_run_status"] == "running"
        assert body["active_node"] == "INIT_REQUEST"
        assert body["last_checkpoint_status"] == "completed"
        assert body["triage_required"] is False

        run_id = body["run_id"]
        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            assert report_run.status == "running"
            assert report_run.tenant_id == tenant_id
            assert report_run.project_id == project_id

        checkpoint_store = LocalJsonlCheckpointStore(root_path=checkpoint_root)
        latest = checkpoint_store.load_latest_checkpoint(run_id=run_id)
        assert latest is not None
        assert latest["node"] == "INIT_REQUEST"
        assert latest["state"]["framework_target"] == ["TSRS2", "CSRD"]
        assert latest["state"]["scope_decision"] == {"mode": "one_click"}
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_create_run_blocks_factory_mode_when_brand_or_profile_is_incomplete(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_factory_context_block.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)
            tenant = session.get(Tenant, tenant_id)
            project = session.get(Project, project_id)
            assert tenant is not None
            assert project is not None
            company_profile, brand_kit, blueprint, _integrations = ensure_project_report_context(
                db=session,
                tenant=tenant,
                project=project,
            )
            company_profile_id = company_profile.id
            brand_kit_id = brand_kit.id
            blueprint_version = blueprint.version
            session.commit()

        response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2", "CSRD"],
                "report_blueprint_version": blueprint_version,
                "company_profile_ref": company_profile_id,
                "brand_kit_ref": brand_kit_id,
                "connector_scope": ["sap_odata"],
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error_code"] == "REPORT_FACTORY_CONTEXT_INCOMPLETE"
        assert detail["is_ready"] is False
        assert detail["blockers"]
        assert any(blocker["code"] == "BRAND_KIT_NOT_CONFIRMED" for blocker in detail["blockers"])
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_create_run_blocks_when_selected_connector_is_not_green_and_certified(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_connector_gate.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)
    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)
            _connector_scope, company_profile_id, brand_kit_id, blueprint_version = _seed_report_factory_context(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            blocked_connector = session.scalar(
                select(IntegrationConfig).where(
                    IntegrationConfig.tenant_id == tenant_id,
                    IntegrationConfig.project_id == project_id,
                    IntegrationConfig.connector_type == "sap_odata",
                )
            )
            assert blocked_connector is not None
            blocked_connector.status = "configured"
            blocked_connector.health_band = "red"
            blocked_connector.health_status_json = {
                "operator_message": "Connector setup is incomplete.",
                "recommended_action": "Run preview sync again.",
            }
            session.commit()

        response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS1", "TSRS2"],
                "report_blueprint_version": blueprint_version,
                "company_profile_ref": company_profile_id,
                "brand_kit_ref": brand_kit_id,
                "connector_scope": ["sap_odata"],
                "scope_decision": {"mode": "one_click"},
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["error_code"] == "CONNECTOR_ONBOARDING_INCOMPLETE"
        assert detail["blocked_connectors"][0]["connector_type"] == "sap_odata"
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_advance_run_success_updates_node_and_checkpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_advance_success.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        create_response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2"],
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run_id"]

        advance_response = client.post(
            f"/runs/{run_id}/advance",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "success": True,
                "metadata": {"step": "manual_advance"},
            },
            headers={"x-user-role": "analyst"},
        )
        assert advance_response.status_code == 200
        body = advance_response.json()
        assert body["active_node"] == "RESOLVE_APPLICABILITY"
        assert "INIT_REQUEST" in body["completed_nodes"]
        assert body["report_run_status"] == "running"
        assert body["triage_required"] is False
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_auditor_readonly_cannot_mutate_runs(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_authz_auditor_readonly.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        create_as_auditor = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2"],
            },
            headers={"x-user-role": "auditor_readonly"},
        )
        assert create_as_auditor.status_code == 403

        create_as_analyst = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2"],
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_as_analyst.status_code == 201
        run_id = create_as_analyst.json()["run_id"]

        advance_as_auditor = client.post(
            f"/runs/{run_id}/advance",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "success": True,
            },
            headers={"x-user-role": "auditor_readonly"},
        )
        assert advance_as_auditor.status_code == 403

        execute_as_auditor = client.post(
            f"/runs/{run_id}/execute",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
            },
            headers={"x-user-role": "auditor_readonly"},
        )
        assert execute_as_auditor.status_code == 403
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_advance_run_failure_sets_failed_and_increments_retry(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_advance_failure.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        create_response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["CSRD"],
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run_id"]

        failure_response = client.post(
            f"/runs/{run_id}/advance",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "success": False,
                "failure_reason": "retrieval timeout",
            },
            headers={"x-user-role": "analyst"},
        )
        assert failure_response.status_code == 200
        body = failure_response.json()
        assert body["report_run_status"] == "failed"
        assert body["active_node"] == "INIT_REQUEST"
        assert "INIT_REQUEST" in body["failed_nodes"]
        assert body["retry_count_by_node"]["INIT_REQUEST"] == 1
        assert body["triage_required"] is False

        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            assert report_run.status == "failed"
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_advance_run_returns_404_for_wrong_tenant_project(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_advance_404.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        create_response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2"],
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run_id"]

        missing_response = client.post(
            f"/runs/{run_id}/advance",
            json={
                "tenant_id": "wrong-tenant",
                "project_id": project_id,
                "success": True,
            },
            headers={"x-user-role": "analyst"},
        )
        assert missing_response.status_code == 404
        assert missing_response.json()["detail"] == "Run not found for tenant/project."
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_execute_run_stops_at_human_approval(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_execute_human.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    original_use_local = settings.azure_ai_search_use_local
    original_search_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.local_checkpoint_root = str(checkpoint_root)
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(tmp_path / "search-index")
    settings.azure_ai_search_index_name = "runs-exec-index-1"

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        _write_local_index(
            Path(settings.local_search_index_root),
            settings.azure_ai_search_index_name,
            {
                "chk-run-1": {
                    "id": "chk-run-1",
                    "chunk_id": "chk-run-1",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_document_id": "doc-run-1",
                    "chunk_index": 0,
                    "page": 1,
                    "section_label": "TSRS2",
                    "token_count": 10,
                    "content": "TSRS2 sustainability disclosures scope 2 emissions 120 and governance process.",
                }
            },
        )

        create_response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2"],
                "scope_decision": {
                    "retrieval_tasks": [
                        {
                            "task_id": "t-tsrs2",
                            "framework": "TSRS2",
                            "query_text": "TSRS2 sustainability disclosures scope 2 emissions",
                            "top_k": 2,
                            "retrieval_mode": "hybrid",
                        }
                    ]
                },
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run_id"]

        execute_response = client.post(
            f"/runs/{run_id}/execute",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "max_steps": 64,
            },
            headers={"x-user-role": "analyst"},
        )
        assert execute_response.status_code == 200
        body = execute_response.json()
        assert body["stop_reason"] == "awaiting_human_approval"
        assert body["executed_steps"] == 13
        assert body["active_node"] == "HUMAN_APPROVAL"
        assert body["report_run_status"] == "awaiting_human_approval"
        assert body["triage_required"] is False
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_search_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_execute_run_completes_when_human_approval_overridden(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_execute_complete.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    original_use_local = settings.azure_ai_search_use_local
    original_search_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.local_checkpoint_root = str(checkpoint_root)
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(tmp_path / "search-index")
    settings.azure_ai_search_index_name = "runs-exec-index-2"

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        _write_local_index(
            Path(settings.local_search_index_root),
            settings.azure_ai_search_index_name,
            {
                "chk-run-2": {
                    "id": "chk-run-2",
                    "chunk_id": "chk-run-2",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_document_id": "doc-run-2",
                    "chunk_index": 0,
                    "page": 2,
                    "section_label": "CSRD",
                    "token_count": 9,
                    "content": "CSRD sustainability disclosures include target progress 88 and risk policy.",
                }
            },
        )

        create_response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["CSRD"],
                "scope_decision": {
                    "retrieval_tasks": [
                        {
                            "task_id": "t-csrd",
                            "framework": "CSRD",
                            "query_text": "CSRD sustainability disclosures target progress",
                            "top_k": 2,
                            "retrieval_mode": "hybrid",
                        }
                    ]
                },
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run_id"]

        execute_response = client.post(
            f"/runs/{run_id}/execute",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "max_steps": 64,
                "human_approval_override": "approved",
            },
            headers={"x-user-role": "analyst"},
        )
        assert execute_response.status_code == 200
        body = execute_response.json()
        assert body["stop_reason"] == "completed"
        assert body["active_node"] == "CLOSE_RUN"
        assert body["publish_ready"] is True
        assert body["report_run_status"] == "completed"
        assert body["compensation_applied"] is False
        assert body["triage_required"] is False

        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            assert report_run.status == "completed"
            assert report_run.publish_ready is True
            assert report_run.completed_at is not None

            sections = session.query(ReportSection).filter(ReportSection.report_run_id == run_id).all()
            assert len(sections) >= 1

            claims = (
                session.query(Claim)
                .join(ReportSection, Claim.report_section_id == ReportSection.id)
                .filter(ReportSection.report_run_id == run_id)
                .all()
            )
            assert len(claims) >= 1

            verification_rows = (
                session.query(VerificationResult)
                .join(Claim, VerificationResult.claim_id == Claim.id)
                .join(ReportSection, Claim.report_section_id == ReportSection.id)
                .filter(ReportSection.report_run_id == run_id)
                .all()
            )
            assert len(verification_rows) >= 1
            assert all(row.status in {"PASS", "FAIL", "UNSURE"} for row in verification_rows)
            assert all(row.report_run_id == run_id for row in verification_rows)
            assert all(row.run_attempt >= 1 for row in verification_rows)
            assert all(bool(row.run_execution_id) for row in verification_rows)

            calculation_rows = (
                session.query(CalculationRun)
                .filter(CalculationRun.report_run_id == run_id)
                .all()
            )
            assert len(calculation_rows) >= 1
            assert any(row.claim_id for row in calculation_rows)
            assert all(bool(row.code_hash) for row in calculation_rows)
            assert all(bool(row.inputs_ref) for row in calculation_rows)

            audit_events = (
                session.query(AuditEvent)
                .filter(
                    AuditEvent.report_run_id == run_id,
                    AuditEvent.event_type == "verification",
                    AuditEvent.event_name == "verification_results_persisted",
                )
                .all()
            )
            assert len(audit_events) >= 1
            payload = audit_events[-1].event_payload or {}
            assert payload["schema_version"] == "verification_audit_v1"
            assert payload["run_id"] == run_id
            assert payload["run_execution_id"]
            assert payload["run_attempt"] >= 1
            assert payload["summary"]["total_claims"] >= 1

        checkpoint_store = LocalJsonlCheckpointStore(root_path=checkpoint_root)
        latest = checkpoint_store.load_latest_checkpoint(run_id=run_id)
        assert latest is not None

        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            before_count = (
                session.query(VerificationResult)
                .filter(VerificationResult.report_run_id == run_id)
                .count()
            )
            before_calc_count = (
                session.query(CalculationRun)
                .filter(CalculationRun.report_run_id == run_id)
                .count()
            )
            stats = _persist_verification_artifacts(
                db=session,
                report_run=report_run,
                state=latest["state"],
                run_execution_id=str(latest["checkpoint_id"]),
                run_attempt=1,
                verifier_version=VERIFIER_VERSION,
            )
            session.commit()
            after_count = (
                session.query(VerificationResult)
                .filter(VerificationResult.report_run_id == run_id)
                .count()
            )
            after_calc_count = (
                session.query(CalculationRun)
                .filter(CalculationRun.report_run_id == run_id)
                .count()
            )
            assert stats["persisted_claims"] >= 1
            assert stats["persisted_calculations"] >= 1
            assert after_count == before_count
            assert after_calc_count == before_calc_count
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_search_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_execute_run_retry_exhaustion_marks_failed_and_compensates(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_execute_retry_exhaustion.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    settings.local_checkpoint_root = str(checkpoint_root)

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        create_response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2"],
                "scope_decision": {
                    "simulate_failures": {
                        "RETRIEVE_EVIDENCE": 3,
                    }
                },
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run_id"]

        execute_response = client.post(
            f"/runs/{run_id}/execute",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "max_steps": 64,
                "retry_budget_by_node": {
                    "RETRIEVE_EVIDENCE": 1,
                },
            },
            headers={"x-user-role": "analyst"},
        )
        assert execute_response.status_code == 200
        body = execute_response.json()
        assert body["stop_reason"] == "failed_retry_exhausted"
        assert body["report_run_status"] == "failed"
        assert body["compensation_applied"] is True
        assert body["escalation_required"] is True
        assert "evidence_pool" in body["invalidated_fields"]
        assert "draft_pool" in body["invalidated_fields"]
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_execute_run_routes_to_triage_when_verifier_unsure(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_execute_triage.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    checkpoint_root = tmp_path / "checkpoints"

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_checkpoint_root = settings.local_checkpoint_root
    original_use_local = settings.azure_ai_search_use_local
    original_search_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.local_checkpoint_root = str(checkpoint_root)
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(tmp_path / "search-index")
    settings.azure_ai_search_index_name = "runs-exec-index-triage"

    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        _write_local_index(
            Path(settings.local_search_index_root),
            settings.azure_ai_search_index_name,
            {
                "chk-run-triage-1": {
                    "id": "chk-run-triage-1",
                    "chunk_id": "chk-run-triage-1",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "source_document_id": "doc-run-triage-1",
                    "chunk_index": 0,
                    "page": 1,
                    "section_label": "TSRS2",
                    "token_count": 8,
                    "content": "Limited supplier statement with partial wording only.",
                }
            },
        )

        create_response = client.post(
            "/runs",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "framework_target": ["TSRS2"],
                "scope_decision": {
                    "retrieval_tasks": [
                        {
                            "task_id": "t-triage",
                            "framework": "TSRS2",
                            "query_text": "supplier engagement improvements",
                            "top_k": 1,
                            "retrieval_mode": "hybrid",
                        }
                    ],
                    "verifier_policy": {
                        "pass_threshold": 0.95,
                        "unsure_threshold": 0.15,
                        "min_citations": 2,
                    },
                },
            },
            headers={"x-user-role": "analyst"},
        )
        assert create_response.status_code == 201
        run_id = create_response.json()["run_id"]

        execute_response = client.post(
            f"/runs/{run_id}/execute",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "max_steps": 64,
                "human_approval_override": "approved",
            },
            headers={"x-user-role": "analyst"},
        )
        assert execute_response.status_code == 200
        body = execute_response.json()
        assert body["stop_reason"] == "awaiting_human_approval"
        assert body["report_run_status"] == "triage_required"
        assert body["triage_required"] is True
        assert body["active_node"] == "HUMAN_APPROVAL"

        checkpoint_file = checkpoint_root / f"{run_id}.jsonl"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

        triage_response = client.get(
            f"/runs/{run_id}/triage-report",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert triage_response.status_code == 200
        triage_body = triage_response.json()
        assert triage_body["schema_version"] == "verification_audit_v1"
        assert triage_body["run_id"] == run_id
        assert triage_body["run_attempt"] >= 1
        assert triage_body["run_execution_id"]
        assert triage_body["triage_required"] is True
        assert triage_body["unsure_count"] >= 1
        assert triage_body["total_items"] >= 1
        assert triage_body["page"] == 1
        assert triage_body["size"] == 50
        assert triage_body["status_filter"] is None
        assert triage_body["section_code_filter"] is None
        assert len(triage_body["items"]) >= 1
        assert all(item["status"] in {"FAIL", "UNSURE"} for item in triage_body["items"])

        triage_filtered = client.get(
            f"/runs/{run_id}/triage-report",
            params={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "status_filter": "UNSURE",
                "page": 1,
                "size": 1,
            },
            headers={"x-user-role": "analyst"},
        )
        assert triage_filtered.status_code == 200
        filtered_body = triage_filtered.json()
        assert filtered_body["status_filter"] == "UNSURE"
        assert filtered_body["size"] == 1
        assert len(filtered_body["items"]) <= 1
        assert all(item["status"] == "UNSURE" for item in filtered_body["items"])

        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            assert report_run.status == "triage_required"
            assert report_run.publish_ready is False

            triage_events = (
                session.query(AuditEvent)
                .filter(
                    AuditEvent.report_run_id == run_id,
                    AuditEvent.event_type == "verification",
                    AuditEvent.event_name == "verification_triage_required",
                )
                .all()
            )
            assert len(triage_events) >= 1
            triage_payload = triage_events[-1].event_payload or {}
            assert triage_payload["schema_version"] == "verification_audit_v1"
            assert triage_payload["triage"]["required"] is True
            assert triage_payload["triage"]["unsure_count"] >= 1
    finally:
        settings.local_checkpoint_root = original_checkpoint_root
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_search_root
        settings.azure_ai_search_index_name = original_index_name
        app.dependency_overrides.clear()
        engine.dispose()


def test_triage_report_reads_latest_attempt_from_db(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_triage_db_source.db"
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
            tenant_id, project_id = _seed_tenant_and_project(session)

            report_run = ReportRun(
                tenant_id=tenant_id,
                project_id=project_id,
                status="triage_required",
                publish_ready=False,
            )
            session.add(report_run)
            session.flush()

            legacy_section = ReportSection(
                report_run_id=report_run.id,
                section_code="TSRS2-LEGACY",
                title="Legacy",
                status="draft",
                ordinal=1,
            )
            latest_section = ReportSection(
                report_run_id=report_run.id,
                section_code="TSRS2-LATEST",
                title="Latest",
                status="draft",
                ordinal=2,
            )
            session.add_all([legacy_section, latest_section])
            session.flush()

            legacy_claim = Claim(
                report_section_id=legacy_section.id,
                statement="Legacy verification claim.",
                status="fail",
            )
            latest_fail_claim = Claim(
                report_section_id=latest_section.id,
                statement="Latest fail claim.",
                status="fail",
            )
            latest_unsure_claim = Claim(
                report_section_id=latest_section.id,
                statement="Latest unsure claim.",
                status="unsure",
            )
            session.add_all([legacy_claim, latest_fail_claim, latest_unsure_claim])
            session.flush()

            session.add(
                VerificationResult(
                    report_run_id=report_run.id,
                    claim_id=legacy_claim.id,
                    run_execution_id="exec_1",
                    run_attempt=1,
                    verifier_version=VERIFIER_VERSION,
                    status="FAIL",
                    reason="legacy mismatch",
                    severity="critical",
                    confidence=0.2,
                )
            )
            session.add_all(
                [
                    VerificationResult(
                        report_run_id=report_run.id,
                        claim_id=latest_fail_claim.id,
                        run_execution_id="exec_2",
                        run_attempt=2,
                        verifier_version=VERIFIER_VERSION,
                        status="FAIL",
                        reason="latest mismatch",
                        severity="critical",
                        confidence=0.25,
                    ),
                    VerificationResult(
                        report_run_id=report_run.id,
                        claim_id=latest_unsure_claim.id,
                        run_execution_id="exec_2",
                        run_attempt=2,
                        verifier_version=VERIFIER_VERSION,
                        status="UNSURE",
                        reason="needs human review",
                        severity="normal",
                        confidence=0.45,
                    ),
                ]
            )
            legacy_claim_id = legacy_claim.id
            session.commit()
            run_id = report_run.id

        triage_response = client.get(
            f"/runs/{run_id}/triage-report",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert triage_response.status_code == 200
        body = triage_response.json()
        assert body["triage_required"] is True
        assert body["run_attempt"] == 2
        assert body["run_execution_id"] == "exec_2"
        assert body["total_items"] == 2
        assert body["fail_count"] == 1
        assert body["unsure_count"] == 1
        assert body["critical_fail_count"] == 1
        returned_claim_ids = {item["claim_id"] for item in body["items"]}
        assert legacy_claim_id not in returned_claim_ids

        filtered_response = client.get(
            f"/runs/{run_id}/triage-report",
            params={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "status_filter": "FAIL",
                "section_code": "TSRS2-LATEST",
            },
            headers={"x-user-role": "analyst"},
        )
        assert filtered_response.status_code == 200
        filtered_body = filtered_response.json()
        assert filtered_body["status_filter"] == "FAIL"
        assert filtered_body["section_code_filter"] == "TSRS2-LATEST"
        assert filtered_body["total_items"] == 1
        assert filtered_body["fail_count"] == 1
        assert filtered_body["unsure_count"] == 0
        assert filtered_body["critical_fail_count"] == 1
        assert len(filtered_body["items"]) == 1
        assert filtered_body["items"][0]["status"] == "FAIL"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_publish_run_blocks_on_missing_citation_and_numeric_artifact(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_publish_blockers.db"
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
    original_local_blob_root = settings.local_blob_root
    settings.local_blob_root = str(tmp_path / "storage")

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

            report_run = ReportRun(
                tenant_id=tenant_id,
                project_id=project_id,
                status="completed",
                publish_ready=True,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(report_run)
            session.flush()

            section = ReportSection(
                report_run_id=report_run.id,
                section_code="TSRS2-PUBLISH",
                title="Publish Gate",
                status="verified",
                ordinal=1,
            )
            session.add(section)
            session.flush()

            claim = Claim(
                report_section_id=section.id,
                statement="Scope 2 emissions decreased by 11.0 percent.",
                status="pass",
                confidence=0.9,
            )
            session.add(claim)
            session.flush()

            session.add(
                VerificationResult(
                    report_run_id=report_run.id,
                    claim_id=claim.id,
                    run_execution_id="exec_publish_1",
                    run_attempt=1,
                    verifier_version=VERIFIER_VERSION,
                    status="PASS",
                    reason="entailment_threshold_passed",
                    severity="normal",
                    confidence=0.95,
                )
            )
            session.commit()
            run_id = report_run.id

        response = client.post(
            f"/runs/{run_id}/publish",
            json={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "compliance_manager"},
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["schema_version"] == "publish_gate_v1"
        assert detail["run_id"] == run_id
        assert detail["blocked"] is True
        blocker_codes = {item["code"] for item in detail["blockers"]}
        assert "MISSING_CITATIONS_FOR_CLAIMS" in blocker_codes
        assert "MISSING_CALCULATOR_ARTIFACTS" in blocker_codes
        assert detail["report_pdf"] is None

        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            assert report_run.status == "completed"
            assert session.query(ReportArtifact).filter(ReportArtifact.report_run_id == run_id).count() == 0
            blocked_events = (
                session.query(AuditEvent)
                .filter(
                    AuditEvent.report_run_id == run_id,
                    AuditEvent.event_type == "publish",
                    AuditEvent.event_name == "publish_blocked",
                )
                .all()
            )
            assert len(blocked_events) >= 1
    finally:
        settings.local_blob_root = original_local_blob_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_publish_run_succeeds_when_all_gate_checks_pass(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_publish_success.db"
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
    original_local_blob_root = settings.local_blob_root
    settings.local_blob_root = str(tmp_path / "storage")
    stub_queue = _StubQueueService()
    app.dependency_overrides[get_job_queue_service] = lambda: stub_queue

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)
            connector_scope, company_profile_id, brand_kit_id, blueprint_version = _seed_report_factory_context(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
            )

            report_run = ReportRun(
                tenant_id=tenant_id,
                project_id=project_id,
                company_profile_id=company_profile_id,
                brand_kit_id=brand_kit_id,
                status="completed",
                publish_ready=True,
                completed_at=datetime.now(timezone.utc),
                report_blueprint_version=blueprint_version,
                connector_scope=connector_scope,
            )
            session.add(report_run)
            session.flush()

            section = ReportSection(
                report_run_id=report_run.id,
                section_code="TSRS2-PUBLISH-SUCCESS",
                title="Publish Gate Success",
                status="verified",
                ordinal=1,
            )
            session.add(section)
            session.flush()

            source_document = SourceDocument(
                tenant_id=tenant_id,
                project_id=project_id,
                document_type="invoice",
                filename="energy-2025.pdf",
                storage_uri="obj://raw/energy-2025.pdf",
                ingested_at=datetime.now(timezone.utc),
                status="indexed",
            )
            session.add(source_document)
            session.flush()

            chunk = Chunk(
                source_document_id=source_document.id,
                chunk_index=0,
                text="Scope 2 emissions decreased by 11.0 percent year-over-year.",
                page=1,
                section_label="TSRS2",
                token_count=12,
            )
            session.add(chunk)
            session.flush()

            claim = Claim(
                report_section_id=section.id,
                statement="Scope 2 emissions decreased by 11.0 percent.",
                status="pass",
                confidence=0.96,
            )
            session.add(claim)
            session.flush()

            session.add(
                ClaimCitation(
                    claim_id=claim.id,
                    source_document_id=source_document.id,
                    chunk_id=chunk.id,
                    span_start=0,
                    span_end=20,
                )
            )
            session.add(
                CalculationRun(
                    report_run_id=report_run.id,
                    claim_id=claim.id,
                    formula_name="ghg_scope2_market_based",
                    code_hash="sha256:test-calc",
                    inputs_ref="obj://calc-inputs/test-calc.json",
                    output_value=110.0,
                    output_unit="tCO2e",
                    trace_log_ref="obj://calc-logs/test-calc.log",
                    status="completed",
                )
            )
            session.add(
                VerificationResult(
                    report_run_id=report_run.id,
                    claim_id=claim.id,
                    run_execution_id="exec_publish_2",
                    run_attempt=2,
                    verifier_version=VERIFIER_VERSION,
                    status="PASS",
                    reason="entailment_threshold_passed",
                    severity="normal",
                    confidence=0.97,
                )
            )
            session.commit()
            run_id = report_run.id

        response = client.post(
            f"/runs/{run_id}/publish",
            json={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "board_member"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "publish_gate_v1"
        assert body["run_id"] == run_id
        assert body["published"] is False
        assert body["blocked"] is False
        assert body["report_run_status"] == "completed"
        assert body["publish_ready"] is True
        assert body["blockers"] == []
        assert body["run_attempt"] == 2
        assert body["run_execution_id"] == "exec_publish_2"
        assert body["package_status"] == "queued"
        assert body["package_job_id"]
        assert body["artifacts"] == []
        assert body["report_pdf"] is None
        assert stub_queue.enqueued_packages == [(run_id, body["package_job_id"])]

        with TestingSessionLocal() as session:
            _finalize_package_as_worker(session, run_id)

        package_status_response = client.get(
            f"/runs/{run_id}/package-status",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert package_status_response.status_code == 200
        package_status = package_status_response.json()
        assert package_status["package_status"] == "completed"
        assert package_status["artifacts"]
        assert package_status["report_quality_score"] is not None
        report_pdf_artifact_payload = next(
            artifact
            for artifact in package_status["artifacts"]
            if artifact["artifact_type"] == "report_pdf"
        )
        visual_manifest_artifact_payload = next(
            artifact
            for artifact in package_status["artifacts"]
            if artifact["artifact_type"] == "visual_manifest"
        )

        download_response = client.get(
            f"/runs/{run_id}/report-pdf",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert download_response.status_code == 200
        assert download_response.headers["content-type"] == "application/pdf"
        assert download_response.content.startswith(b"%PDF")
        pdf_reader = PdfReader(BytesIO(download_response.content))
        with pdfplumber.open(BytesIO(download_response.content)) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            full_text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        assert "SÜRDÜRÜLEBİLİRLİK" in first_page_text.upper()
        assert "İçindekiler" in full_text
        assert "Çevresel Performans" in full_text
        assert "Atıf Dizini" in full_text
        assert len(pdf_reader.pages) >= 15
        metadata_title = str(pdf_reader.metadata.get("/Title", ""))
        assert "Sürdürülebilirlik Raporu" in metadata_title
        outline_titles = _collect_outline_titles(pdf_reader.outline)
        assert "Kapak" in outline_titles
        assert "İçindekiler" in outline_titles
        assert "Çevresel Performans" in outline_titles
        first_page_resources = pdf_reader.pages[0].get("/Resources")
        assert first_page_resources is not None
        assert first_page_resources.get("/XObject") is not None
        if report_pdf_artifact_payload.get("metadata", {}).get("renderer") == "weasyprint":
            toc_annots = pdf_reader.pages[1].get("/Annots")
            assert toc_annots is not None
            assert len(toc_annots) >= 3

        visual_manifest_download = client.get(
            visual_manifest_artifact_payload["download_path"],
            headers={"x-user-role": "analyst"},
        )
        assert visual_manifest_download.status_code == 200
        visual_manifest = json.loads(visual_manifest_download.content.decode("utf-8"))
        assert visual_manifest
        assert any(item["metadata"]["image_policy"] == "decorative_only_no_claims" for item in visual_manifest if item["content_type"] == "image/png")
        assert all("metadata" in item for item in visual_manifest)

        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            assert report_run.status == "published"
            assert report_run.package_status == "completed"
            artifacts = session.query(ReportArtifact).filter(ReportArtifact.report_run_id == run_id).all()
            assert len(artifacts) >= 6
            assert any(artifact.artifact_type == "report_pdf" for artifact in artifacts)
            events = (
                session.query(AuditEvent)
                .filter(
                    AuditEvent.report_run_id == run_id,
                    AuditEvent.event_type == "publish",
                    AuditEvent.event_name == "publish_completed",
                )
                .all()
            )
            assert len(events) >= 1
            event_payload = events[-1].event_payload or {}
            assert event_payload["report_pdf"]["artifact_type"] == "report_pdf"
    finally:
        settings.local_blob_root = original_local_blob_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_publish_run_records_failure_when_report_pdf_generation_fails(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_publish_failure.db"
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
    original_local_blob_root = settings.local_blob_root
    settings.local_blob_root = str(tmp_path / "storage")
    original_local_blob_root = settings.local_blob_root
    settings.local_blob_root = str(tmp_path / "storage")
    class _FailingQueueService(_StubQueueService):
        async def enqueue_report_package(self, report_run_id: str, *, package_job_id: str | None = None) -> str:
            raise RuntimeError("queue dispatch exploded")

    app.dependency_overrides[get_job_queue_service] = lambda: _FailingQueueService()

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

            report_run = ReportRun(
                tenant_id=tenant_id,
                project_id=project_id,
                status="completed",
                publish_ready=True,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(report_run)
            session.flush()

            section = ReportSection(
                report_run_id=report_run.id,
                section_code="FAIL-PDF",
                title="Fail PDF",
                status="verified",
                ordinal=1,
            )
            session.add(section)
            session.flush()

            source_document = SourceDocument(
                tenant_id=tenant_id,
                project_id=project_id,
                document_type="invoice",
                filename="energy-2025.pdf",
                storage_uri="obj://raw/energy-2025.pdf",
                ingested_at=datetime.now(timezone.utc),
                status="indexed",
            )
            session.add(source_document)
            session.flush()

            chunk = Chunk(
                source_document_id=source_document.id,
                chunk_index=0,
                text="Scope 2 emissions decreased by 11.0 percent year-over-year.",
                page=1,
                section_label="TSRS2",
                token_count=12,
            )
            session.add(chunk)
            session.flush()

            claim = Claim(
                report_section_id=section.id,
                statement="Scope 2 emissions decreased by 11.0 percent.",
                status="pass",
                confidence=0.96,
            )
            session.add(claim)
            session.flush()

            session.add(
                ClaimCitation(
                    claim_id=claim.id,
                    source_document_id=source_document.id,
                    chunk_id=chunk.id,
                    span_start=0,
                    span_end=20,
                )
            )
            session.add(
                CalculationRun(
                    report_run_id=report_run.id,
                    claim_id=claim.id,
                    formula_name="ghg_scope2_market_based",
                    code_hash="sha256:test-calc",
                    inputs_ref="obj://calc-inputs/test-calc.json",
                    output_value=110.0,
                    output_unit="tCO2e",
                    trace_log_ref="obj://calc-logs/test-calc.log",
                    status="completed",
                )
            )
            session.add(
                VerificationResult(
                    report_run_id=report_run.id,
                    claim_id=claim.id,
                    run_execution_id="exec_publish_3",
                    run_attempt=3,
                    verifier_version=VERIFIER_VERSION,
                    status="PASS",
                    reason="entailment_threshold_passed",
                    severity="normal",
                    confidence=0.97,
                )
            )
            session.commit()
            run_id = report_run.id

        response = client.post(
            f"/runs/{run_id}/publish",
            json={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "board_member"},
        )
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["error_code"] == "REPORT_PACKAGE_GENERATION_FAILED"
        assert "queue dispatch exploded" in detail["reason"]

        with TestingSessionLocal() as session:
            report_run = session.get(ReportRun, run_id)
            assert report_run is not None
            assert report_run.status == "completed"
            assert report_run.publish_ready is True
            assert report_run.package_status == "failed"
            assert session.query(ReportArtifact).filter(ReportArtifact.report_run_id == run_id).count() == 0
            failed_events = (
                session.query(AuditEvent)
                .filter(
                    AuditEvent.report_run_id == run_id,
                    AuditEvent.event_type == "publish",
                    AuditEvent.event_name == "publish_failed",
                )
                .all()
            )
            assert len(failed_events) >= 1
    finally:
        settings.local_blob_root = original_local_blob_root
        app.dependency_overrides.clear()
        engine.dispose()


def test_download_report_pdf_requires_read_access_and_existing_artifact(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_download_report_pdf.db"
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
    original_local_blob_root = settings.local_blob_root
    settings.local_blob_root = str(tmp_path / "storage")

    try:
        storage_root = tmp_path / "storage" / "report-artifacts" / "ten" / "prj" / "runs"
        storage_root.mkdir(parents=True, exist_ok=True)
        pdf_path = storage_root / "manual-report.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\nmanual pdf bytes\n")

        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

            missing_artifact_run = ReportRun(
                tenant_id=tenant_id,
                project_id=project_id,
                status="completed",
                publish_ready=True,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(missing_artifact_run)

            downloadable_run = ReportRun(
                tenant_id=tenant_id,
                project_id=project_id,
                status="published",
                publish_ready=True,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(downloadable_run)
            session.flush()

            session.add(
                ReportArtifact(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    report_run_id=downloadable_run.id,
                    artifact_type="report_pdf",
                    filename="manual-report.pdf",
                    content_type="application/pdf",
                    storage_uri=f"file://{pdf_path.as_posix()}",
                    size_bytes=pdf_path.stat().st_size,
                    checksum="sha256:test",
                )
            )
            session.commit()
            missing_run_id = missing_artifact_run.id
            downloadable_run_id = downloadable_run.id

        missing_response = client.get(
            f"/runs/{missing_run_id}/report-pdf",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert missing_response.status_code == 404

        allowed_response = client.get(
            f"/runs/{downloadable_run_id}/report-pdf",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert allowed_response.status_code == 200
        assert allowed_response.content.startswith(b"%PDF")

        denied_response = client.get(
            f"/runs/{downloadable_run_id}/report-pdf",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "board_member"},
        )
        assert denied_response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_publish_run_is_idempotent_when_already_published(tmp_path: Path) -> None:
    db_file = tmp_path / "test_runs_publish_idempotent.db"
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
    original_local_blob_root = settings.local_blob_root
    settings.local_blob_root = str(tmp_path / "storage")
    stub_queue = _StubQueueService()
    app.dependency_overrides[get_job_queue_service] = lambda: stub_queue

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)
            connector_scope, company_profile_id, brand_kit_id, blueprint_version = _seed_report_factory_context(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            report_run = ReportRun(
                tenant_id=tenant_id,
                project_id=project_id,
                company_profile_id=company_profile_id,
                brand_kit_id=brand_kit_id,
                status="published",
                publish_ready=True,
                completed_at=datetime.now(timezone.utc),
                report_blueprint_version=blueprint_version,
                connector_scope=connector_scope,
            )
            session.add(report_run)
            session.commit()
            run_id = report_run.id

        first_response = client.post(
            f"/runs/{run_id}/publish",
            json={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "admin"},
        )
        assert first_response.status_code == 200
        first_body = first_response.json()
        assert first_body["published"] is False
        assert first_body["blocked"] is False
        assert first_body["report_run_status"] == "published"
        assert first_body["report_pdf"] is None

        with TestingSessionLocal() as session:
            _finalize_package_as_worker(session, run_id)

        second_response = client.post(
            f"/runs/{run_id}/publish",
            json={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "admin"},
        )
        assert second_response.status_code == 200
        second_body = second_response.json()
        assert second_body["report_pdf"] is not None
        assert second_body["published"] is True
        assert second_body["package_job_id"] == first_body["package_job_id"]

        with TestingSessionLocal() as session:
            assert session.query(ReportArtifact).filter(ReportArtifact.report_run_id == run_id).count() >= 6
    finally:
        settings.local_blob_root = original_local_blob_root
        app.dependency_overrides.clear()
        engine.dispose()
