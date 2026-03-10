from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.db.session import get_db
from app.models.core import Project, Tenant
from app.schemas.auth import CurrentUser
from app.schemas.catalog import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    TenantCreateRequest,
    TenantListResponse,
    TenantResponse,
    WorkspaceBootstrapRequest,
    WorkspaceBootstrapResponse,
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

    db.commit()
    db.refresh(tenant)
    db.refresh(project)

    return WorkspaceBootstrapResponse(
        tenant=_to_tenant_response(tenant),
        project=_to_project_response(project),
        tenant_created=tenant_created,
        project_created=project_created,
    )
