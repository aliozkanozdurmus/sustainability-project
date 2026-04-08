# Bu route, catalog uc noktasinin HTTP giris katmanini tanimlar.

from __future__ import annotations

from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.core.settings import settings
from app.db.session import get_db
from app.models.core import BrandKit, CompanyProfile, IntegrationConfig, Project, Tenant
from app.schemas.auth import CurrentUser
from app.schemas.catalog import (
    BrandKitLogoUploadResponse,
    BrandKitResponse,
    CompanyProfileResponse,
    FactoryReadinessResponse,
    IntegrationConfigSummaryResponse,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    TenantCreateRequest,
    TenantListResponse,
    TenantResponse,
    WorkspaceBootstrapRequest,
    WorkspaceBootstrapResponse,
    WorkspaceContextResponse,
)
from app.services.report_context import (
    apply_report_factory_configuration,
    build_report_factory_readiness,
    ensure_project_report_context,
    is_brand_kit_configured,
    is_company_profile_configured,
    resolve_brand_logo_uri,
)
from app.services.integrations import get_assigned_agent_status

router = APIRouter(prefix="/catalog", tags=["catalog"])
CATALOG_MUTATION_ROLES = ("admin", "compliance_manager", "analyst")
CATALOG_READ_ROLES = (*CATALOG_MUTATION_ROLES, "auditor_readonly")
BRAND_LOGO_MAX_SIZE_BYTES = 5 * 1024 * 1024
BRAND_LOGO_EXTENSION_TO_CONTENT_TYPE = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
BRAND_LOGO_CONTENT_TYPE_TO_EXTENSION = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


def _safe_upload_filename(name: str) -> str:
    return PurePath(name).name.replace("\\", "_").replace("/", "_")


def _safe_file_stem(name: str) -> str:
    stem = PurePath(name).stem
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in stem).strip("-")
    return cleaned or "brand-mark"


def _resolve_brand_logo_file_details(file: UploadFile, safe_name: str) -> tuple[str, str]:
    suffix = PurePath(safe_name).suffix.lower()
    content_type = (file.content_type or "").strip().lower()

    if suffix in BRAND_LOGO_EXTENSION_TO_CONTENT_TYPE:
        expected_content_type = BRAND_LOGO_EXTENSION_TO_CONTENT_TYPE[suffix]
        if content_type in {"", "application/octet-stream", "binary/octet-stream", expected_content_type}:
            return suffix, expected_content_type

    if content_type in BRAND_LOGO_CONTENT_TYPE_TO_EXTENSION:
        return BRAND_LOGO_CONTENT_TYPE_TO_EXTENSION[content_type], content_type

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Logo file must be PNG, JPG, WEBP, or SVG.",
    )


def _to_tenant_response(tenant: Tenant) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status,
    )


def _to_project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        tenant_id=project.tenant_id,
        name=project.name,
        code=project.code,
        reporting_currency=project.reporting_currency,
        status=project.status,
    )


def _to_company_profile_response(profile: CompanyProfile) -> CompanyProfileResponse:
    return CompanyProfileResponse(
        id=profile.id,
        tenant_id=profile.tenant_id,
        project_id=profile.project_id,
        legal_name=profile.legal_name,
        sector=profile.sector,
        headquarters=profile.headquarters,
        description=profile.description,
        ceo_name=profile.ceo_name,
        ceo_message=profile.ceo_message,
        sustainability_approach=profile.sustainability_approach,
        is_configured=is_company_profile_configured(profile),
    )


def _to_brand_kit_response(brand_kit: BrandKit) -> BrandKitResponse:
    return BrandKitResponse(
        id=brand_kit.id,
        tenant_id=brand_kit.tenant_id,
        project_id=brand_kit.project_id,
        brand_name=brand_kit.brand_name,
        logo_uri=resolve_brand_logo_uri(brand_kit),
        primary_color=brand_kit.primary_color,
        secondary_color=brand_kit.secondary_color,
        accent_color=brand_kit.accent_color,
        font_family_headings=brand_kit.font_family_headings,
        font_family_body=brand_kit.font_family_body,
        tone_name=brand_kit.tone_name,
        is_configured=is_brand_kit_configured(brand_kit),
    )


def _to_integration_summary_response(db: Session, integration: IntegrationConfig) -> IntegrationConfigSummaryResponse:
    return IntegrationConfigSummaryResponse(
        id=integration.id,
        connector_type=integration.connector_type,
        display_name=integration.display_name,
        status=integration.status,
        support_tier=integration.support_tier,
        certified_variant=integration.certified_variant,
        product_version=integration.product_version,
        health_band=integration.health_band,
        last_discovered_at=integration.last_discovered_at.isoformat() if integration.last_discovered_at else None,
        last_preflight_at=integration.last_preflight_at.isoformat() if integration.last_preflight_at else None,
        last_preview_sync_at=integration.last_preview_sync_at.isoformat() if integration.last_preview_sync_at else None,
        last_synced_at=integration.last_synced_at.isoformat() if integration.last_synced_at else None,
        assigned_agent_status=get_assigned_agent_status(db=db, integration=integration),
    )


def _build_workspace_context_response(
    *,
    db: Session,
    tenant: Tenant,
    project: Project,
    company_profile: CompanyProfile,
    brand_kit: BrandKit,
    integrations: list[IntegrationConfig],
    blueprint_version: str,
) -> WorkspaceContextResponse:
    readiness = build_report_factory_readiness(
        company_profile=company_profile,
        brand_kit=brand_kit,
    )
    return WorkspaceContextResponse(
        tenant=_to_tenant_response(tenant),
        project=_to_project_response(project),
        company_profile=_to_company_profile_response(company_profile),
        brand_kit=_to_brand_kit_response(brand_kit),
        integrations=[_to_integration_summary_response(db, item) for item in integrations],
        blueprint_version=blueprint_version,
        factory_readiness=FactoryReadinessResponse(**readiness),
    )


@router.get("/tenants", response_model=TenantListResponse, status_code=status.HTTP_200_OK)
async def list_tenants(
    slug: str | None = Query(default=None),
    user: CurrentUser = Depends(require_roles(*CATALOG_READ_ROLES)),
    db: Session = Depends(get_db),
) -> TenantListResponse:
    _ = user
    query = select(Tenant).order_by(Tenant.created_at.desc())
    if slug and slug.strip():
        query = query.where(Tenant.slug == slug.strip())
    tenants = db.scalars(query).all()
    return TenantListResponse(items=[_to_tenant_response(row) for row in tenants], total=len(tenants))


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreateRequest,
    user: CurrentUser = Depends(require_roles(*CATALOG_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> TenantResponse:
    _ = user
    slug = payload.slug.strip()
    existing = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Tenant slug already exists.")

    tenant = Tenant(name=payload.name.strip(), slug=slug, status="active")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return _to_tenant_response(tenant)


@router.get(
    "/tenants/{tenant_id}/projects",
    response_model=ProjectListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_projects(
    tenant_id: str,
    code: str | None = Query(default=None),
    user: CurrentUser = Depends(require_roles(*CATALOG_READ_ROLES)),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    _ = user
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    query = select(Project).where(Project.tenant_id == tenant_id).order_by(Project.created_at.desc())
    if code and code.strip():
        query = query.where(Project.code == code.strip())
    projects = db.scalars(query).all()
    return ProjectListResponse(items=[_to_project_response(row) for row in projects], total=len(projects))


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    user: CurrentUser = Depends(require_roles(*CATALOG_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    _ = user
    tenant = db.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    code = payload.code.strip()
    existing = db.scalar(
        select(Project).where(
            Project.tenant_id == payload.tenant_id,
            Project.code == code,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Project code already exists for tenant.")

    project = Project(
        tenant_id=payload.tenant_id,
        name=payload.name.strip(),
        code=code,
        reporting_currency=payload.reporting_currency.strip().upper(),
        status="active",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_project_response(project)


@router.post(
    "/bootstrap-workspace",
    response_model=WorkspaceBootstrapResponse,
    status_code=status.HTTP_200_OK,
)
async def bootstrap_workspace(
    payload: WorkspaceBootstrapRequest,
    user: CurrentUser = Depends(require_roles(*CATALOG_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> WorkspaceBootstrapResponse:
    _ = user
    tenant_slug = payload.tenant_slug.strip()
    project_code = payload.project_code.strip()

    tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant_created = False
    if tenant is None:
        tenant = Tenant(
            name=payload.tenant_name.strip(),
            slug=tenant_slug,
            status="active",
        )
        db.add(tenant)
        db.flush()
        tenant_created = True

    project = db.scalar(
        select(Project).where(
            Project.tenant_id == tenant.id,
            Project.code == project_code,
        )
    )
    project_created = False
    if project is None:
        project = Project(
            tenant_id=tenant.id,
            name=payload.project_name.strip(),
            code=project_code,
            reporting_currency=payload.reporting_currency.strip().upper(),
            status="active",
        )
        db.add(project)
        db.flush()
        project_created = True

    company_profile, brand_kit, blueprint, integrations = ensure_project_report_context(
        db=db,
        tenant=tenant,
        project=project,
    )
    company_profile, brand_kit = apply_report_factory_configuration(
        db=db,
        company_profile=company_profile,
        brand_kit=brand_kit,
        company_profile_payload=payload.company_profile,
        brand_kit_payload=payload.brand_kit,
    )

    db.commit()
    db.refresh(tenant)
    db.refresh(project)
    db.refresh(company_profile)
    db.refresh(brand_kit)

    workspace_context = _build_workspace_context_response(
        db=db,
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand_kit=brand_kit,
        integrations=integrations,
        blueprint_version=blueprint.version,
    )

    return WorkspaceBootstrapResponse(
        **workspace_context.model_dump(),
        tenant_created=tenant_created,
        project_created=project_created,
    )


@router.post(
    "/brand-kit-logo",
    response_model=BrandKitLogoUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_brand_kit_logo(
    tenant_id: str | None = Form(default=None),
    project_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_roles(*CATALOG_MUTATION_ROLES)),
    db: Session = Depends(get_db),
) -> BrandKitLogoUploadResponse:
    _ = user

    if bool(tenant_id) != bool(project_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id and project_id must be provided together.",
        )

    if tenant_id and project_id:
        tenant = db.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found.")

        project = db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
            )
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found for tenant.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded logo is empty.")
    if len(payload) > BRAND_LOGO_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Logo file must be 5 MB or smaller.",
        )

    safe_name = _safe_upload_filename(file.filename or "brand-logo")
    suffix, content_type = _resolve_brand_logo_file_details(file, safe_name)
    public_root = (settings.repo_root / "apps" / "web" / "public").resolve()
    destination_dir = (
        (public_root / "brand-uploads" / tenant_id / project_id).resolve()
        if tenant_id and project_id
        else (public_root / "brand-uploads" / "drafts").resolve()
    )

    try:
        destination_dir.relative_to(public_root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Computed brand asset path is invalid.") from exc

    destination_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex[:12]}-{_safe_file_stem(safe_name)}{suffix}"
    destination_path = (destination_dir / stored_name).resolve()
    try:
        destination_path.relative_to(public_root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Computed brand asset file is invalid.") from exc

    destination_path.write_bytes(payload)
    logo_uri = f"/{destination_path.relative_to(public_root).as_posix()}"

    if len(logo_uri) > 1024:
        raise HTTPException(status_code=500, detail="Stored logo path exceeded brand kit limits.")

    return BrandKitLogoUploadResponse(
        logo_uri=logo_uri,
        filename=stored_name,
        content_type=content_type,
        size_bytes=len(payload),
    )


@router.get(
    "/workspace-context",
    response_model=WorkspaceContextResponse,
    status_code=status.HTTP_200_OK,
)
async def get_workspace_context(
    tenant_id: str = Query(min_length=1),
    project_id: str = Query(min_length=1),
    user: CurrentUser = Depends(require_roles(*CATALOG_READ_ROLES)),
    db: Session = Depends(get_db),
) -> WorkspaceContextResponse:
    _ = user
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.tenant_id == tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")

    company_profile, brand_kit, blueprint, integrations = ensure_project_report_context(
        db=db,
        tenant=tenant,
        project=project,
    )
    db.commit()
    db.refresh(project)
    db.refresh(company_profile)
    db.refresh(brand_kit)
    return _build_workspace_context_response(
        db=db,
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand_kit=brand_kit,
        integrations=integrations,
        blueprint_version=blueprint.version,
    )
