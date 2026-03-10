from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class RunCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    framework_target: list[str] = Field(min_length=1)
    active_reg_pack_version: str | None = None
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
