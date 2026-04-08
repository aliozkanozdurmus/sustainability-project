# Bu test dosyasi, integrations davranisini dogrular.

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.core import CanonicalFact, ConnectorArtifact, IntegrationConfig, Project, Tenant
from app.services.integrations import run_connector_sync
from app.services.report_context import ensure_project_report_context


def _seed_tenant_and_project(db: Session) -> tuple[str, str]:
    tenant = Tenant(name="Tenant Integrations", slug="tenant-integrations")
    db.add(tenant)
    db.flush()

    project = Project(
        tenant_id=tenant.id,
        name="Integration Project",
        code="INT-PRJ",
        reporting_currency="TRY",
    )
    db.add(project)
    db.commit()
    return tenant.id, project.id


def _seed_workspace_with_default_connectors(db: Session) -> tuple[str, str, dict[str, str]]:
    tenant_id, project_id = _seed_tenant_and_project(db)
    tenant = db.get(Tenant, tenant_id)
    project = db.get(Project, project_id)
    assert tenant is not None
    assert project is not None
    _company_profile, _brand_kit, _blueprint, integrations = ensure_project_report_context(
        db=db,
        tenant=tenant,
        project=project,
    )
    db.commit()
    return tenant_id, project_id, {item.connector_type: item.id for item in integrations}


def test_run_connector_sync_normalizes_sap_odata_payload_and_delta_token(tmp_path) -> None:
    db_file = tmp_path / "integrations_sap.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)
            integration = IntegrationConfig(
                tenant_id=tenant_id,
                project_id=project_id,
                connector_type="sap_odata",
                display_name="SAP OData",
                auth_mode="odata",
                base_url="https://sap.example.local",
                resource_path="/sap/opu/odata/sustainability",
                status="active",
                mapping_version="v1",
                sample_payload={
                    "@odata.deltaLink": "sap-delta-token-2025",
                    "value": [
                        {
                            "MetricCode": "e_scope2_tco2e",
                            "MetricName": "Scope 2 Emissions",
                            "FiscalYear": "2025",
                            "Unit": "tco2e",
                            "Value": "12450",
                            "RecordId": "sap-scope2-2025",
                            "OwnerEmail": "energy@example.com",
                            "TraceRef": "sap://scope2/2025",
                        }
                    ],
                },
            )
            session.add(integration)
            session.commit()

            job = run_connector_sync(db=session, integration=integration)
            session.commit()

            fact = session.query(CanonicalFact).filter(CanonicalFact.integration_config_id == integration.id).one()
            assert job.cursor_after == "sap-delta-token-2025"
            assert integration.last_cursor == "sap-delta-token-2025"
            assert fact.metric_code == "E_SCOPE2_TCO2E"
            assert fact.metric_name == "Scope 2 Emissions"
            assert fact.unit == "tCO2e"
            assert fact.value_numeric == 12450.0
            assert fact.trace_ref == "sap://scope2/2025"
            assert fact.source_system == "sap_odata"
    finally:
        engine.dispose()


def test_run_connector_sync_logo_snapshot_is_idempotent(tmp_path) -> None:
    db_file = tmp_path / "integrations_logo.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)
            integration = IntegrationConfig(
                tenant_id=tenant_id,
                project_id=project_id,
                connector_type="logo_tiger_sql_view",
                display_name="Logo Tiger SQL View",
                auth_mode="sql_view",
                base_url="sql://logo",
                resource_path="vw_sustainability_metrics",
                status="active",
                mapping_version="v1",
                sample_payload={
                    "snapshot_watermark": "2026-04-01T09:00:00Z",
                    "rows": [
                        {
                            "METRIC_KODU": "workforce_headcount",
                            "METRIC_ADI": "Workforce Headcount",
                            "DONEM": "2025",
                            "BIRIM": "employees",
                            "DEGER": 1850,
                            "ROW_ID": "logo-headcount-2025",
                            "updated_at": "2026-04-01T09:00:00Z",
                        }
                    ],
                },
            )
            session.add(integration)
            session.commit()

            first_job = run_connector_sync(db=session, integration=integration)
            session.commit()
            second_job = run_connector_sync(db=session, integration=integration)
            session.commit()

            facts = session.query(CanonicalFact).filter(CanonicalFact.integration_config_id == integration.id).all()
            assert len(facts) == 1
            assert facts[0].metric_code == "WORKFORCE_HEADCOUNT"
            assert facts[0].unit == "employee"
            assert first_job.inserted_count == 1
            assert second_job.inserted_count == 0
            assert second_job.updated_count == 1
            assert integration.last_cursor == "2026-04-01T09:00:00Z"
    finally:
        engine.dispose()


def test_run_connector_sync_normalizes_netsis_rest_cursor_payload(tmp_path) -> None:
    db_file = tmp_path / "integrations_netsis.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)
            integration = IntegrationConfig(
                tenant_id=tenant_id,
                project_id=project_id,
                connector_type="netsis_rest",
                display_name="Netsis REST",
                auth_mode="rest",
                base_url="https://netsis.example.local",
                resource_path="/api/v1/sustainability",
                status="active",
                mapping_version="v1",
                sample_payload={
                    "next_cursor": "netsis-cursor-2",
                    "items": [
                        {
                            "metric": {
                                "code": "supplier_coverage",
                                "name": "Supplier Coverage",
                            },
                            "periodKey": "2025",
                            "unit": "percentage",
                            "value": "96",
                            "id": "netsis-supplier-2025",
                            "updatedAt": "2026-03-31T10:00:00Z",
                            "traceRef": "netsis://supplier-coverage/2025",
                        }
                    ],
                },
            )
            session.add(integration)
            session.commit()

            job = run_connector_sync(db=session, integration=integration)
            session.commit()

            fact = session.query(CanonicalFact).filter(CanonicalFact.integration_config_id == integration.id).one()
            assert job.cursor_after == "netsis-cursor-2"
            assert integration.last_cursor == "netsis-cursor-2"
            assert fact.metric_code == "SUPPLIER_COVERAGE"
            assert fact.metric_name == "Supplier Coverage"
            assert fact.unit == "%"
            assert fact.value_numeric == 96.0
            assert fact.trace_ref == "netsis://supplier-coverage/2025"
            assert fact.source_system == "netsis_rest"
    finally:
        engine.dispose()


def test_preflight_endpoint_returns_connector_specific_auth_error_when_credential_ref_is_missing(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "test_integrations_preflight_route.db"
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
            tenant_id, project_id, connector_ids = _seed_workspace_with_default_connectors(session)
            integration = session.get(IntegrationConfig, connector_ids["sap_odata"])
            assert integration is not None
            integration.credential_ref = None
            session.commit()

        response = client.post(
            f"/integrations/connectors/{connector_ids['sap_odata']}/preflight",
            json={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "SAP_AUTH_PREFLIGHT_FAILED"
        assert body["health_band"] == "red"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_preview_sync_endpoint_keeps_production_facts_empty_and_support_bundle_creates_artifact(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "test_integrations_preview_bundle.db"
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
            tenant_id, project_id, connector_ids = _seed_workspace_with_default_connectors(session)
            sap_connector_id = connector_ids["sap_odata"]
            assert session.query(CanonicalFact).count() == 0

        preview_response = client.post(
            f"/integrations/connectors/{sap_connector_id}/preview-sync",
            json={"tenant_id": tenant_id, "project_id": project_id, "limit": 20},
            headers={"x-user-role": "analyst"},
        )
        assert preview_response.status_code == 200
        preview_body = preview_response.json()
        assert preview_body["status"] == "completed"
        assert preview_body["result"]["writes_production_facts"] is False
        assert preview_body["result"]["preview_row_count"] >= 1

        support_bundle_response = client.post(
            f"/integrations/connectors/{sap_connector_id}/support-bundle",
            json={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert support_bundle_response.status_code == 200
        support_bundle_body = support_bundle_response.json()
        assert support_bundle_body["artifact"] is not None

        download_response = client.get(
            support_bundle_body["artifact"]["download_path"],
            headers={"x-user-role": "analyst"},
        )
        assert download_response.status_code == 200
        assert len(download_response.content) > 0

        with TestingSessionLocal() as session:
            assert session.query(CanonicalFact).count() == 0
            assert session.query(ConnectorArtifact).count() == 1
            integration = session.get(IntegrationConfig, sap_connector_id)
            assert integration is not None
            assert integration.last_preview_sync_at is not None
            assert integration.status == "active"
    finally:
        settings.local_blob_root = original_local_blob_root
        app.dependency_overrides.clear()
        engine.dispose()
