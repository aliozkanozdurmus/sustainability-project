from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.core import CanonicalFact, IntegrationConfig, Project, Tenant
from app.services.integrations import run_connector_sync


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
