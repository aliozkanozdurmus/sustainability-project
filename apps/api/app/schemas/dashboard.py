from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DashboardStatus = Literal["good", "attention", "critical", "neutral"]


class KpiTrendPoint(BaseModel):
    label: str
    value: float


class DashboardHero(BaseModel):
    tenant_name: str
    company_name: str
    project_name: str
    project_code: str
    sector: str | None = None
    headquarters: str | None = None
    reporting_currency: str
    blueprint_version: str | None = None
    readiness_label: str
    readiness_score: int = Field(ge=0, le=100)
    summary: str
    logo_uri: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None


class DashboardMetric(BaseModel):
    key: str
    label: str
    display_value: str
    detail: str | None = None
    delta_text: str | None = None
    status: DashboardStatus = "neutral"
    trend: list[KpiTrendPoint] = Field(default_factory=list)


class PipelineLane(BaseModel):
    lane_id: str
    label: str
    count: int = Field(ge=0)
    total: int = Field(ge=0)
    ratio: float = Field(ge=0, le=1)
    status: DashboardStatus = "neutral"
    description: str


class ConnectorHealthItem(BaseModel):
    connector_id: str
    connector_type: str
    display_name: str
    status: str
    auth_mode: str
    last_synced_at_utc: str | None = None
    job_status: str | None = None
    current_stage: str | None = None
    record_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    freshness_hours: float | None = None
    status_tone: DashboardStatus = "neutral"


class RiskItem(BaseModel):
    risk_id: str
    title: str
    severity: DashboardStatus
    count: int = Field(ge=0)
    detail: str


class ScheduleItem(BaseModel):
    item_id: str
    title: str
    subtitle: str
    slot_label: str
    status: DashboardStatus
    run_id: str | None = None


class ArtifactHealthSummary(BaseModel):
    artifact_type: str
    label: str
    available: int = Field(ge=0)
    total_runs: int = Field(ge=0)
    completion_ratio: float = Field(ge=0, le=1)


class ActivityItem(BaseModel):
    activity_id: str
    title: str
    detail: str
    category: str
    status: DashboardStatus = "neutral"
    occurred_at_utc: str | None = None


class RunQueueItem(BaseModel):
    run_id: str
    report_run_status: str
    active_node: str
    publish_ready: bool
    human_approval: str
    package_status: str
    report_quality_score: float | None = None
    latest_sync_at_utc: str | None = None
    visual_generation_status: str


class DashboardOverviewResponse(BaseModel):
    hero: DashboardHero
    metrics: list[DashboardMetric] = Field(default_factory=list)
    pipeline: list[PipelineLane] = Field(default_factory=list)
    connector_health: list[ConnectorHealthItem] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    schedule: list[ScheduleItem] = Field(default_factory=list)
    artifact_health: list[ArtifactHealthSummary] = Field(default_factory=list)
    activity_feed: list[ActivityItem] = Field(default_factory=list)
    run_queue: list[RunQueueItem] = Field(default_factory=list)
    generated_at_utc: str
