from __future__ import annotations

from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=120)


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    status: str


class ProjectCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=2, max_length=64)
    reporting_currency: str = Field(default="TRY", min_length=1, max_length=8)


class ProjectResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    code: str
    reporting_currency: str
    status: str


class CompanyProfileResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    legal_name: str
    sector: str | None = None
    headquarters: str | None = None
    ceo_name: str | None = None


class BrandKitResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    brand_name: str
    primary_color: str
    secondary_color: str
    accent_color: str
    font_family_headings: str
    font_family_body: str


class IntegrationConfigSummaryResponse(BaseModel):
    id: str
    connector_type: str
    display_name: str
    status: str
    last_synced_at: str | None = None


class TenantListResponse(BaseModel):
    items: list[TenantResponse]
    total: int


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int


class WorkspaceBootstrapRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=200)
    tenant_slug: str = Field(min_length=2, max_length=120)
    project_name: str = Field(min_length=2, max_length=200)
    project_code: str = Field(min_length=2, max_length=64)
    reporting_currency: str = Field(default="TRY", min_length=1, max_length=8)


class WorkspaceContextResponse(BaseModel):
    tenant: TenantResponse
    project: ProjectResponse
    company_profile: CompanyProfileResponse
    brand_kit: BrandKitResponse
    integrations: list[IntegrationConfigSummaryResponse]
    blueprint_version: str


class WorkspaceBootstrapResponse(WorkspaceContextResponse):
    tenant_created: bool
    project_created: bool
