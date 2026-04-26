# Bu sema dosyasi, runs icin API veri sozlesmelerini tanimlar.

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RunCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    framework_target: list[str] = Field(min_length=1)
    active_reg_pack_version: str | None = None
    report_blueprint_version: str | None = None
    company_profile_ref: str | None = None
    brand_kit_ref: str | None = None
    connector_scope: list[str] = Field(default_factory=list)
    scope_decision: dict[str, Any] = Field(default_factory=dict)


class RunAdvanceRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    success: bool = True
    failure_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_failure_reason(self) -> "RunAdvanceRequest":
        if not self.success and not (self.failure_reason and self.failure_reason.strip()):
            raise ValueError("failure_reason is required when success is false.")
        return self


class RunStatusResponse(BaseModel):
    run_id: str
    report_run_id: str
    report_run_status: str
    active_node: str
    completed_nodes: list[str]
    failed_nodes: list[str]
    retry_count_by_node: dict[str, int]
    publish_ready: bool
    human_approval: str
    triage_required: bool
    last_checkpoint_status: str
    last_checkpoint_at_utc: str
    package_status: str
    report_quality_score: float | None = None
    latest_sync_at_utc: str | None = None
    visual_generation_status: str
    report_pdf: "ReportArtifactResponse | None" = None


class RunListItem(BaseModel):
    run_id: str
    report_run_status: str
    publish_ready: bool
    started_at_utc: str | None
    completed_at_utc: str | None
    active_node: str
    human_approval: str
    triage_required: bool
    last_checkpoint_status: str
    last_checkpoint_at_utc: str | None
    package_status: str
    report_quality_score: float | None = None
    latest_sync_at_utc: str | None = None
    visual_generation_status: str
    approval_sla_deadline_utc: str | None = None
    approval_sla_status: Literal["healthy", "risk", "breached", "complete", "unknown"] = "unknown"
    artifact_completion_ratio: float = Field(default=0.0, ge=0, le=1)
    artifact_badges: list[str] = Field(default_factory=list)
    report_pdf: ReportArtifactResponse | None = None


class RunListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[RunListItem]


class RunExecuteRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    max_steps: int | None = Field(default=None, ge=1, le=256)
    retry_budget_by_node: dict[str, int] = Field(default_factory=dict)
    human_approval_override: Literal["pending", "approved", "rejected"] | None = None

    @model_validator(mode="after")
    def validate_retry_budget_values(self) -> "RunExecuteRequest":
        for node, value in self.retry_budget_by_node.items():
            if value < 0:
                raise ValueError(f"Retry budget for node {node} must be >= 0.")
        return self


class RunExecuteResponse(RunStatusResponse):
    executed_steps: int
    stop_reason: str
    compensation_applied: bool
    invalidated_fields: list[str]
    escalation_required: bool


class RunPublishRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)


class ReportArtifactResponse(BaseModel):
    artifact_id: str
    artifact_type: str
    filename: str
    content_type: str
    size_bytes: int
    checksum: str
    created_at_utc: str
    download_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportPackageStageResponse(BaseModel):
    stage: str
    status: str
    at_utc: str
    detail: str | None = None


class RunPackageStatusResponse(BaseModel):
    run_id: str
    package_job_id: str | None = None
    package_status: str
    current_stage: str | None = None
    report_quality_score: float | None = None
    visual_generation_status: str
    artifacts: list[ReportArtifactResponse] = Field(default_factory=list)
    stage_history: list[ReportPackageStageResponse] = Field(default_factory=list)
    generated_at_utc: str


class RunPublishBlocker(BaseModel):
    code: str
    message: str
    count: int | None = None
    sample_claim_ids: list[str] = Field(default_factory=list)


class RunPublishResponse(BaseModel):
    schema_version: str
    run_id: str
    run_attempt: int | None = None
    run_execution_id: str | None = None
    report_run_status: str
    publish_ready: bool
    published: bool
    blocked: bool
    blockers: list[RunPublishBlocker] = Field(default_factory=list)
    package_job_id: str | None = None
    package_status: str
    estimated_stage: str | None = None
    artifacts: list[ReportArtifactResponse] = Field(default_factory=list)
    report_pdf: ReportArtifactResponse | None = None
    generated_at_utc: str


class RunTriageItem(BaseModel):
    section_code: str
    claim_id: str
    status: Literal["FAIL", "UNSURE"]
    severity: str
    reason: str
    confidence: float | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class RunTriageReportResponse(BaseModel):
    schema_version: str
    run_id: str
    run_attempt: int | None = None
    run_execution_id: str | None = None
    report_run_status: str
    triage_required: bool
    fail_count: int
    unsure_count: int
    critical_fail_count: int
    total_items: int
    page: int
    size: int
    status_filter: Literal["FAIL", "UNSURE"] | None = None
    section_code_filter: str | None = None
    items: list[RunTriageItem]
    generated_at_utc: str


RunStatusResponse.model_rebuild()
RunListItem.model_rebuild()
RunPublishResponse.model_rebuild()
