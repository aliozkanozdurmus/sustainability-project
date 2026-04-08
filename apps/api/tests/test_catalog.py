# Bu test dosyasi, catalog davranisini dogrular.

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.core import Project, Tenant


def test_bootstrap_workspace_returns_ready_factory_context_when_profile_and_brand_are_supplied(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "test_catalog_bootstrap.db"
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
        response = client.post(
            "/catalog/bootstrap-workspace",
            json={
                "tenant_name": "Factory Ready Tenant",
                "tenant_slug": "factory-ready-tenant",
                "project_name": "Factory Ready Project",
                "project_code": "FRP",
                "reporting_currency": "TRY",
                "company_profile": {
                    "legal_name": "Factory Ready Project",
                    "sector": "Ambalaj ve endustriyel uretim",
                    "headquarters": "Istanbul, Turkiye",
                    "description": "Kurumsal profile sahip, ERP ve evidence ile rapor ureten test workspace.",
                    "ceo_name": "Factory Ready CEO",
                    "ceo_message": "Surdurulebilirlik stratejisini olculebilir performansla yonetiyoruz.",
                    "sustainability_approach": "Izlenebilir, marka uyumlu ve kontrollu publish odakli model.",
                },
                "brand_kit": {
                    "brand_name": "Factory Ready Brand",
                    "logo_uri": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='64'><rect width='180' height='64' rx='14' fill='%230c4a6e'/><text x='90' y='40' font-size='26' text-anchor='middle' fill='white'>FR</text></svg>",
                    "primary_color": "#f07f13",
                    "secondary_color": "#0c4a6e",
                    "accent_color": "#7ab648",
                    "font_family_headings": "Segoe UI Semibold",
                    "font_family_body": "Segoe UI",
                    "tone_name": "kurumsal-guvenilir",
                },
            },
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["factory_readiness"]["is_ready"] is True
        assert body["factory_readiness"]["company_profile_ready"] is True
        assert body["factory_readiness"]["brand_kit_ready"] is True
        assert body["factory_readiness"]["blockers"] == []
        assert body["company_profile"]["is_configured"] is True
        assert body["brand_kit"]["is_configured"] is True
        assert body["brand_kit"]["logo_uri"].startswith("data:image/svg+xml")
        assert len(body["integrations"]) == 3
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_workspace_context_surfaces_default_brand_logo_without_missing_logo_blocker(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "test_catalog_workspace_context.db"
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
            tenant = Tenant(name="Default Brand Tenant", slug="default-brand-tenant", status="active")
            session.add(tenant)
            session.flush()
            project = Project(
                tenant_id=tenant.id,
                name="Default Brand Project",
                code="DBP",
                reporting_currency="TRY",
                status="active",
            )
            session.add(project)
            session.commit()
            tenant_id = tenant.id
            project_id = project.id

        response = client.get(
            f"/catalog/workspace-context?tenant_id={tenant_id}&project_id={project_id}",
            headers={"x-user-role": "analyst"},
        )
        assert response.status_code == 200
        body = response.json()
        blocker_codes = {item["code"] for item in body["factory_readiness"]["blockers"]}
        assert body["brand_kit"]["logo_uri"] == "/brand/veni-logo-clean-orbit-emblem.png"
        assert body["factory_readiness"]["brand_kit_ready"] is False
        assert "BRAND_KIT_NOT_CONFIRMED" in blocker_codes
        assert "BRAND_KIT_FIELD_MISSING" not in blocker_codes
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
