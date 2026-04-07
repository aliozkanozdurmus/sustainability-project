# Bu sema dosyasi, integrations icin API veri sozlesmelerini tanimlar.

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IntegrationConfigCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    connector_type: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=2, max_length=200)
    auth_mode: str = Field(default="configured", min_length=2, max_length=64)
    base_url: str | None = None
    resource_path: str | None = None
    mapping_version: str = Field(default="v1", min_length=1, max_length=64)
    connection_payload: dict[str, Any] = Field(default_factory=dict)
    sample_payload: dict[str, Any] = Field(default_factory=dict)


class IntegrationConfigResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    connector_type: str
    display_name: str
    auth_mode: str
    base_url: str | None = None
    resource_path: str | None = None
    status: str
    mapping_version: str
    last_cursor: str | None = None
    last_synced_at_utc: str | None = None


class IntegrationSyncRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    connector_ids: list[str] = Field(default_factory=list)


class ConnectorSyncJobResponse(BaseModel):
    job_id: str
    integration_config_id: str
    tenant_id: str
    project_id: str
    connector_type: str
    status: str
    current_stage: str
    record_count: int
    inserted_count: int
    updated_count: int
    cursor_before: str | None = None
    cursor_after: str | None = None
    error_message: str | None = None
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class IntegrationSyncResponse(BaseModel):
    jobs: list[ConnectorSyncJobResponse]
    synced_connector_count: int


class ProjectFactResponse(BaseModel):
    fact_id: str
    metric_code: str
    metric_name: str
    period_key: str
    unit: str | None = None
    value_numeric: float | None = None
    value_text: str | None = None
    source_system: str
    source_record_id: str
    owner: str | None = None
    freshness_at_utc: str | None = None
    confidence_score: float | None = None
    trace_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectFactsResponse(BaseModel):
    items: list[ProjectFactResponse]
    total: int
