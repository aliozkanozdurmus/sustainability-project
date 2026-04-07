# Bu servis, report_context akisindaki uygulama mantigini tek yerde toplar.

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import BrandKit, CompanyProfile, IntegrationConfig, Project, ReportBlueprint, Tenant


DEFAULT_BLUEPRINT_TEMPLATE = {
    "locale": "tr-TR",
    "page_archetypes": [
        "cover",
        "contents",
        "ceo_message",
        "company_about",
        "governance",
        "double_materiality",
        "environment",
        "social",
        "appendix_index",
    ],
    "sections": [
        {
            "section_code": "CEO_MESSAGE",
            "title": "Yönetimden Mesaj",
            "purpose": "Kurumsal sürdürülebilirlik vizyonunu ve raporun tonunu açmak.",
            "required_metrics": [],
            "required_evidence": ["governance_pack"],
            "allowed_claim_types": ["narrative", "governance"],
            "visual_slots": ["cover_hero"],
            "appendix_refs": ["assumption_register"],
        },
        {
            "section_code": "COMPANY_PROFILE",
            "title": "Şirket Profili",
            "purpose": "Şirketin ölçeğini, ayak izini ve operasyonel bağlamını açıklamak.",
            "required_metrics": ["WORKFORCE_HEADCOUNT", "SUPPLIER_COVERAGE"],
            "required_evidence": ["company_profile"],
            "allowed_claim_types": ["profile", "operational"],
            "visual_slots": ["company_profile_photo"],
            "appendix_refs": ["citation_index"],
        },
        {
            "section_code": "GOVERNANCE",
            "title": "Yönetişim ve Risk",
            "purpose": "Komite yapısı, yönetim rolü ve risk gözetimini açıklamak.",
            "required_metrics": ["BOARD_OVERSIGHT_COVERAGE", "SUSTAINABILITY_COMMITTEE_MEETINGS"],
            "required_evidence": ["governance_pack"],
            "allowed_claim_types": ["governance", "qualitative"],
            "visual_slots": ["governance_grid"],
            "appendix_refs": ["coverage_matrix"],
        },
        {
            "section_code": "DOUBLE_MATERIALITY",
            "title": "Çifte Önemlilik Görünümü",
            "purpose": "Finansal ve etki önemliliğini aynı yüzeyde sunmak.",
            "required_metrics": ["MATERIAL_TOPIC_COUNT", "STAKEHOLDER_ENGAGEMENT_TOUCHPOINTS"],
            "required_evidence": ["materiality_summary"],
            "allowed_claim_types": ["matrix", "narrative"],
            "visual_slots": ["double_materiality_matrix"],
            "appendix_refs": ["assumption_register"],
        },
        {
            "section_code": "ENVIRONMENT",
            "title": "Çevresel Performans",
            "purpose": "Emisyon, enerji ve verimlilik hikayesini ölçülebilir şekilde sunmak.",
            "required_metrics": [
                "E_SCOPE2_TCO2E",
                "E_SCOPE2_TCO2E_PREV",
                "RENEWABLE_ELECTRICITY_SHARE",
                "ENERGY_INTENSITY_REDUCTION",
            ],
            "required_evidence": ["energy_report"],
            "allowed_claim_types": ["numeric", "trend", "target"],
            "visual_slots": ["environment_hero", "scope2_trend_chart"],
            "appendix_refs": ["calculation_appendix", "citation_index"],
        },
        {
            "section_code": "SOCIAL",
            "title": "Sosyal Performans",
            "purpose": "İSG, çalışan ve tedarik zinciri performansını özetlemek.",
            "required_metrics": [
                "LTIFR",
                "LTIFR_PREV",
                "SUPPLIER_COVERAGE",
                "HIGH_RISK_SUPPLIER_SCREENING",
                "WORKFORCE_HEADCOUNT",
            ],
            "required_evidence": ["social_report"],
            "allowed_claim_types": ["numeric", "operational"],
            "visual_slots": ["social_hero", "supplier_coverage_chart"],
            "appendix_refs": ["citation_index"],
        },
    ],
}

DEFAULT_CONNECTORS = (
    {
        "connector_type": "sap_odata",
        "display_name": "SAP Sustainability Feed",
        "auth_mode": "odata",
        "base_url": "https://sap.example.local",
        "resource_path": "/sap/opu/odata/sustainability",
    },
    {
        "connector_type": "logo_tiger_sql_view",
        "display_name": "Logo Tiger SQL View",
        "auth_mode": "sql_view",
        "base_url": "sql://logo-tiger",
        "resource_path": "vw_sustainability_metrics",
    },
    {
        "connector_type": "netsis_rest",
        "display_name": "Netsis Sustainability REST",
        "auth_mode": "rest",
        "base_url": "https://netsis.example.local",
        "resource_path": "/api/v1/sustainability-metrics",
    },
)

REQUIRED_COMPANY_PROFILE_FIELDS = (
    ("legal_name", "Kurumsal unvan"),
    ("sector", "Sektör"),
    ("headquarters", "Genel merkez"),
    ("description", "Kurum profili"),
    ("ceo_name", "Yönetici adı"),
    ("ceo_message", "Yönetici mesajı"),
    ("sustainability_approach", "Sürdürülebilirlik yaklaşımı"),
)

REQUIRED_BRAND_KIT_FIELDS = (
    ("brand_name", "Marka adı"),
    ("logo_uri", "Logo"),
    ("primary_color", "Ana renk"),
    ("secondary_color", "Yardımcı renk"),
    ("accent_color", "Vurgu rengi"),
    ("font_family_headings", "Başlık fontu"),
    ("font_family_body", "Gövde fontu"),
    ("tone_name", "Yönetici mesajı tonu"),
)


def _default_company_profile(*, tenant: Tenant, project: Project) -> CompanyProfile:
    return CompanyProfile(
        tenant_id=tenant.id,
        project_id=project.id,
        legal_name=project.name,
        sector="Ambalaj ve endüstriyel üretim",
        headquarters="İstanbul, Türkiye",
        description=(
            f"{project.name}, {tenant.name} çatısı altında sürdürülebilirlik dönüşümünü "
            "operasyonel veriler ve denetlenebilir kanıtlarla yöneten kurumsal bir üretim organizasyonudur."
        ),
        founded_year=2004,
        employee_count=1850,
        ceo_name="Kurumsal Liderlik Ekibi",
        ceo_message=(
            "Bu rapor, şirketimizin çevresel ve sosyal etkilerini ölçülebilir hedefler, "
            "güçlü yönetişim yapıları ve kanıt temelli performans çıktılarıyla bütünleşik şekilde sunar."
        ),
        sustainability_approach=(
            "Veri bütünlüğü, operasyonel verimlilik ve paydaş güvenini aynı anda yükselten, "
            "ölçülebilir ve doğrulanabilir bir sürdürülebilirlik yönetim modeli uygulanmaktadır."
        ),
        metadata_json={"auto_provisioned": True},
    )


def _default_brand_kit(*, tenant: Tenant, project: Project) -> BrandKit:
    return BrandKit(
        tenant_id=tenant.id,
        project_id=project.id,
        brand_name=tenant.name,
        primary_color="#f07f13",
        secondary_color="#0c4a6e",
        accent_color="#7ab648",
        font_family_headings="Segoe UI Semibold",
        font_family_body="Segoe UI",
        tone_name="kurumsal-guvenilir",
        metadata_json={
            "project_code": project.code,
            "auto_provisioned": True,
        },
    )


def _default_blueprint(*, tenant: Tenant, project: Project) -> ReportBlueprint:
    payload = deepcopy(DEFAULT_BLUEPRINT_TEMPLATE)
    payload["brand_name"] = tenant.name
    payload["project_name"] = project.name
    return ReportBlueprint(
        tenant_id=tenant.id,
        project_id=project.id,
        version=settings.report_factory_default_blueprint_version,
        locale=settings.report_factory_default_locale,
        status="active",
        blueprint_json=payload,
    )


def _default_connector(*, tenant: Tenant, project: Project, definition: dict[str, str]) -> IntegrationConfig:
    return IntegrationConfig(
        tenant_id=tenant.id,
        project_id=project.id,
        connector_type=definition["connector_type"],
        display_name=definition["display_name"],
        auth_mode=definition["auth_mode"],
        base_url=definition["base_url"],
        resource_path=definition["resource_path"],
        status="active",
        mapping_version="v1",
        connection_payload={"auto_provisioned": True},
        sample_payload={},
    )


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _metadata_flag(metadata: dict[str, Any] | None, key: str) -> bool:
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get(key))


def _profile_blockers(company_profile: CompanyProfile) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if _metadata_flag(company_profile.metadata_json, "auto_provisioned"):
        blockers.append(
            {
                "code": "COMPANY_PROFILE_NOT_CONFIRMED",
                "message": "Company profile varsayilan bootstrap verisi ile duruyor; run oncesi onayli kurumsal profil girilmeli.",
            }
        )
    for field_name, label in REQUIRED_COMPANY_PROFILE_FIELDS:
        if _clean_optional_text(getattr(company_profile, field_name, None)) is None:
            blockers.append(
                {
                    "code": "COMPANY_PROFILE_FIELD_MISSING",
                    "message": f"{label} eksik. Report factory anlatisi bu bilgi olmadan uretilmez.",
                }
            )
    return blockers


def _brand_blockers(brand_kit: BrandKit) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    if _metadata_flag(brand_kit.metadata_json, "auto_provisioned"):
        blockers.append(
            {
                "code": "BRAND_KIT_NOT_CONFIRMED",
                "message": "Brand kit varsayilan bootstrap degerleri ile duruyor; controlled publish oncesi tenant brand kit tanimi gerekli.",
            }
        )
    for field_name, label in REQUIRED_BRAND_KIT_FIELDS:
        if _clean_optional_text(getattr(brand_kit, field_name, None)) is None:
            blockers.append(
                {
                    "code": "BRAND_KIT_FIELD_MISSING",
                    "message": f"{label} eksik. Profesyonel PDF kompozisyonu bu alan olmadan calistirilmaz.",
                }
            )
    return blockers


def is_company_profile_configured(company_profile: CompanyProfile) -> bool:
    return len(_profile_blockers(company_profile)) == 0


def is_brand_kit_configured(brand_kit: BrandKit) -> bool:
    return len(_brand_blockers(brand_kit)) == 0


def build_report_factory_readiness(
    *,
    company_profile: CompanyProfile,
    brand_kit: BrandKit,
) -> dict[str, Any]:
    company_blockers = _profile_blockers(company_profile)
    brand_blockers = _brand_blockers(brand_kit)
    blockers = [*company_blockers, *brand_blockers]
    return {
        "is_ready": len(blockers) == 0,
        "company_profile_ready": len(company_blockers) == 0,
        "brand_kit_ready": len(brand_blockers) == 0,
        "blockers": blockers,
    }


def apply_report_factory_configuration(
    *,
    db: Session,
    company_profile: CompanyProfile,
    brand_kit: BrandKit,
    company_profile_payload: dict[str, Any] | None = None,
    brand_kit_payload: dict[str, Any] | None = None,
) -> tuple[CompanyProfile, BrandKit]:
    if isinstance(company_profile_payload, dict):
        for field_name in (
            "legal_name",
            "sector",
            "headquarters",
            "description",
            "ceo_name",
            "ceo_message",
            "sustainability_approach",
        ):
            if field_name not in company_profile_payload:
                continue
            next_value = _clean_optional_text(company_profile_payload.get(field_name))
            if next_value is None:
                continue
            setattr(company_profile, field_name, next_value)
        metadata = dict(company_profile.metadata_json or {})
        metadata["auto_provisioned"] = False
        metadata["configuration_source"] = "workspace_bootstrap"
        company_profile.metadata_json = metadata

    if isinstance(brand_kit_payload, dict):
        for field_name in (
            "brand_name",
            "logo_uri",
            "primary_color",
            "secondary_color",
            "accent_color",
            "font_family_headings",
            "font_family_body",
            "tone_name",
        ):
            if field_name not in brand_kit_payload:
                continue
            next_value = _clean_optional_text(brand_kit_payload.get(field_name))
            if next_value is None:
                continue
            setattr(brand_kit, field_name, next_value)
        metadata = dict(brand_kit.metadata_json or {})
        metadata["auto_provisioned"] = False
        metadata["configuration_source"] = "workspace_bootstrap"
        brand_kit.metadata_json = metadata

    db.flush()
    return company_profile, brand_kit


def ensure_project_report_context(
    *,
    db: Session,
    tenant: Tenant,
    project: Project,
) -> tuple[CompanyProfile, BrandKit, ReportBlueprint, list[IntegrationConfig]]:
    company_profile = db.scalar(
        select(CompanyProfile).where(
            CompanyProfile.project_id == project.id,
            CompanyProfile.tenant_id == tenant.id,
        )
    )
    if company_profile is None:
        company_profile = _default_company_profile(tenant=tenant, project=project)
        db.add(company_profile)
        db.flush()

    brand_kit = db.scalar(
        select(BrandKit).where(
            BrandKit.project_id == project.id,
            BrandKit.tenant_id == tenant.id,
        )
    )
    if brand_kit is None:
        brand_kit = _default_brand_kit(tenant=tenant, project=project)
        db.add(brand_kit)
        db.flush()

    blueprint = db.scalar(
        select(ReportBlueprint).where(
            ReportBlueprint.project_id == project.id,
            ReportBlueprint.version == settings.report_factory_default_blueprint_version,
        )
    )
    if blueprint is None:
        blueprint = _default_blueprint(tenant=tenant, project=project)
        db.add(blueprint)
        db.flush()

    integrations: list[IntegrationConfig] = []
    for definition in DEFAULT_CONNECTORS:
        integration = db.scalar(
            select(IntegrationConfig).where(
                IntegrationConfig.project_id == project.id,
                IntegrationConfig.connector_type == definition["connector_type"],
            )
        )
        if integration is None:
            integration = _default_connector(tenant=tenant, project=project, definition=definition)
            db.add(integration)
            db.flush()
        integrations.append(integration)

    return company_profile, brand_kit, blueprint, integrations
