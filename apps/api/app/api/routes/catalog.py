from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.db.session import get_db
from app.models.core import BrandKit, CompanyProfile, IntegrationConfig, Project, Tenant
from app.schemas.auth import CurrentUser
from app.schemas.catalog import (
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
)

router = APIRouter(prefix="/catalog", tags=["catalog"])
CATALOG_MUTATION_ROLES = ("admin", "compliance_manager", "analyst")
CATALOG_READ_ROLES = (*CATALOG_MUTATION_ROLES, "auditor_readonly")


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
        logo_uri=brand_kit.logo_uri,
        primary_color=brand_kit.primary_color,
        secondary_color=brand_kit.secondary_color,
        accent_color=brand_kit.accent_color,
        font_family_headings=brand_kit.font_family_headings,
        font_family_body=brand_kit.font_family_body,
        tone_name=brand_kit.tone_name,
        is_configured=is_brand_kit_configured(brand_kit),
    )


def _to_integration_summary_response(integration: IntegrationConfig) -> IntegrationConfigSummaryResponse:
    return IntegrationConfigSummaryResponse(
        id=integration.id,
        connector_type=integration.connector_type,
        display_name=integration.display_name,
        status=integration.status,
        last_synced_at=integration.last_synced_at.isoformat() if integration.last_synced_at else None,
    )


def _build_workspace_context_response(
    *,
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
        integrations=[_to_integration_summary_response(item) for item in integrations],
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
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand_kit=brand_kit,
        integrations=integrations,
        blueprint_version=blueprint.version,
    )
