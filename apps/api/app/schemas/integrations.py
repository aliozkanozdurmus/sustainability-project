# Bu sema dosyasi, integrations icin API veri sozlesmelerini tanimlar.

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ConnectorHealthBand = Literal["green", "amber", "red"]
ConnectorSupportTier = Literal["certified", "beta", "unsupported"]
ConnectorOperationType = Literal["discover", "preflight", "preview_sync", "replay", "support_bundle"]
ConnectorReplayMode = Literal["resume", "reset_cursor", "backfill_window"]
ConnectorAgentKind = Literal["docker", "windows_service"]


class ConnectorConnectionProfileRequest(BaseModel):
    host: str | None = None
    port: int | None = None
    service_url: str | None = None
    resource_path: str | None = None
    company_code: str | None = None
    firm_code: str | None = None
    database_name: str | None = None
    sql_view_name: str | None = None
    view_schema: str | None = None
    auth_method: str | None = None
    username: str | None = None
    instance_name: str | None = None


class ConnectorHealthMetricResponse(BaseModel):
    key: str
    label: str
    score: int
    status: str
    detail: str


class ConnectorHealthStatusResponse(BaseModel):
    score: int
    band: ConnectorHealthBand
    metrics: list[ConnectorHealthMetricResponse] = Field(default_factory=list)
    operator_message: str
    support_hint: str
    recommended_action: str
    retryable: bool
    support_matrix_version: str


class IntegrationConfigCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    connector_type: str = Field(min_length=2, max_length=64)
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    auth_mode: str | None = Field(default=None, min_length=2, max_length=64)
    base_url: str | None = None
    resource_path: str | None = None
    mapping_version: str = Field(default="v1", min_length=1, max_length=64)
    certified_variant: str | None = Field(default=None, min_length=2, max_length=128)
    product_version: str | None = Field(default=None, min_length=1, max_length=64)
    connectivity_mode: str | None = Field(default=None, min_length=2, max_length=64)
    credential_ref: str | None = Field(default=None, min_length=2, max_length=255)
    assigned_agent_id: str | None = None
    connection_profile: ConnectorConnectionProfileRequest = Field(default_factory=ConnectorConnectionProfileRequest)
    normalization_policy: dict[str, Any] = Field(default_factory=dict)
    sample_payload: dict[str, Any] = Field(default_factory=dict)
    connection_payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ensure_profile_payload(self) -> "IntegrationConfigCreateRequest":
        if self.connection_payload and self.connection_profile.model_dump(exclude_none=True):
            raise ValueError("Use typed connection_profile instead of connection_payload.")
        return self


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
    certified_variant: str | None = None
    product_version: str | None = None
    support_tier: ConnectorSupportTier
    connectivity_mode: str
    credential_ref: str | None = None
    health_band: ConnectorHealthBand
    health_status: ConnectorHealthStatusResponse | None = None
    assigned_agent_id: str | None = None
    normalization_policy: dict[str, Any] = Field(default_factory=dict)
    connection_profile: dict[str, Any] = Field(default_factory=dict)
    last_cursor: str | None = None
    last_discovered_at_utc: str | None = None
    last_preflight_at_utc: str | None = None
    last_preview_sync_at_utc: str | None = None
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


class ConnectorAgentRegisterRequest(BaseModel):
    tenant_id: str | None = None
    project_id: str | None = None
    agent_key: str = Field(min_length=3, max_length=128)
    display_name: str = Field(min_length=2, max_length=200)
    agent_kind: ConnectorAgentKind
    version: str | None = Field(default=None, min_length=1, max_length=64)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    supported_connectors: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorAgentHeartbeatRequest(BaseModel):
    status: str = Field(min_length=2, max_length=32)
    version: str | None = Field(default=None, min_length=1, max_length=64)
    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    active_operation_id: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class ConnectorAgentResponse(BaseModel):
    agent_id: str
    tenant_id: str | None = None
    project_id: str | None = None
    agent_key: str
    display_name: str
    agent_kind: ConnectorAgentKind
    status: str
    version: str | None = None
    hostname: str | None = None
    supported_connectors: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_heartbeat_at_utc: str | None = None


class ConnectorOperationRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)


class ConnectorPreviewSyncRequest(ConnectorOperationRequest):
    limit: int = Field(default=20, ge=1, le=20)


class ConnectorReplayRequest(ConnectorOperationRequest):
    mode: ConnectorReplayMode
    backfill_window_days: int | None = Field(default=None, ge=1, le=90)

    @model_validator(mode="after")
    def validate_backfill_window(self) -> "ConnectorReplayRequest":
        if self.mode == "backfill_window" and self.backfill_window_days is None:
            raise ValueError("backfill_window_days is required when mode=backfill_window.")
        return self


class ConnectorArtifactResponse(BaseModel):
    artifact_id: str
    integration_config_id: str
    connector_operation_run_id: str | None = None
    artifact_type: str
    filename: str
    content_type: str
    size_bytes: int
    checksum: str | None = None
    created_at_utc: str
    download_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorOperationResponse(BaseModel):
    operation_id: str
    integration_config_id: str
    tenant_id: str
    project_id: str
    connector_type: str
    operation_type: ConnectorOperationType
    status: str
    current_stage: str
    replay_mode: ConnectorReplayMode | None = None
    assigned_agent_id: str | None = None
    support_tier: ConnectorSupportTier
    health_band: ConnectorHealthBand
    operator_message: str | None = None
    support_hint: str | None = None
    recommended_action: str | None = None
    retryable: bool
    error_code: str | None = None
    error_message: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    artifact: ConnectorArtifactResponse | None = None


class ConnectorClaimNextOperationResponse(BaseModel):
    operation: ConnectorOperationResponse | None = None
