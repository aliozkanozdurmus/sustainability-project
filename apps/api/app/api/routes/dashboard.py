# Bu route, dashboard uc noktasinin HTTP giris katmanini tanimlar.

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.db.session import get_db
from app.models.core import (
    BrandKit,
    CanonicalFact,
    CompanyProfile,
    ConnectorSyncJob,
    ExtractionRecord,
    IntegrationConfig,
    Project,
    ReportArtifact,
    ReportPackage,
    ReportRun,
    ReportVisualAsset,
    SourceDocument,
    Tenant,
    VerificationResult,
)
from app.schemas.auth import CurrentUser
from app.schemas.dashboard import (
    ActivityItem,
    ArtifactHealthSummary,
    ConnectorHealthItem,
    DashboardHero,
    DashboardMetric,
    DashboardOverviewResponse,
    KpiTrendPoint,
    PipelineLane,
    RiskItem,
    RunQueueItem,
    ScheduleItem,
)
from app.services.report_context import build_report_factory_readiness, resolve_brand_logo_uri
from app.services.integrations import connector_ready_for_launch, get_assigned_agent_status


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DASHBOARD_READ_ROLES = (
    "admin",
    "compliance_manager",
    "analyst",
    "auditor_readonly",
    "board_member",
)

SPOTLIGHT_METRICS = (
    "E_SCOPE2_TCO2E",
    "RENEWABLE_ELECTRICITY_SHARE",
    "LTIFR",
    "SUPPLIER_COVERAGE",
    "WORKFORCE_HEADCOUNT",
)

ARTIFACT_LABELS = {
    "report_pdf": "Report PDF",
    "visual_manifest": "Visual Manifest",
    "citation_index": "Citation Index",
    "calculation_appendix": "Calculation Appendix",
    "coverage_matrix": "Coverage Matrix",
    "assumption_register": "Assumption Register",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _hours_since(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return round(max(0.0, (_utcnow() - value).total_seconds() / 3600), 2)


def _format_compact_number(value: float | int | None, unit: str | None = None) -> str:
    if value is None:
        return "-"
    number = float(value)
    abs_value = abs(number)
    suffix = ""
    scaled = number
    if abs_value >= 1_000_000:
        scaled = number / 1_000_000
        suffix = "M"
    elif abs_value >= 1_000:
        scaled = number / 1_000
        suffix = "K"

    if unit == "%":
        rendered = f"{number:.0f}%"
    elif abs(number - round(number)) < 1e-9:
        rendered = f"{int(round(scaled))}{suffix}"
    else:
        rendered = f"{scaled:.1f}{suffix}"
    return rendered


def _metric_status(key: str, current: float | None, previous: float | None = None) -> str:
    if current is None:
        return "neutral"
    if key == "RENEWABLE_ELECTRICITY_SHARE":
        if current >= 40:
            return "good"
        if current >= 25:
            return "attention"
        return "critical"
    if key == "SUPPLIER_COVERAGE":
        if current >= 95:
            return "good"
        if current >= 85:
            return "attention"
        return "critical"
    if key == "LTIFR":
        if current <= 0.5:
            return "good"
        if current <= 0.8:
            return "attention"
        return "critical"
    if key == "E_SCOPE2_TCO2E" and previous is not None:
        return "good" if current <= previous else "attention"
    return "neutral"


def _delta_text(current: float | None, previous: float | None, unit: str | None) -> str | None:
    if current is None or previous is None:
        return None
    delta = current - previous
    if abs(delta) < 1e-9:
        return "Flat versus prior period"
    if unit == "%":
        prefix = "+" if delta > 0 else ""
        return f"{prefix}{delta:.1f} pts versus prior period"
    ratio = (delta / previous) * 100 if previous else 0
    prefix = "+" if ratio > 0 else ""
    return f"{prefix}{ratio:.1f}% versus prior period"


def _readiness_payload(
    company_profile: CompanyProfile | None,
    brand_kit: BrandKit | None,
) -> tuple[str, int]:
    if company_profile is None or brand_kit is None:
        return ("Needs setup", 32)
    readiness = build_report_factory_readiness(
        company_profile=company_profile,
        brand_kit=brand_kit,
    )
    blocker_count = len(readiness["blockers"])
    if blocker_count == 0:
        return ("Factory ready", 100)
    if blocker_count <= 2:
        return ("Needs review", 74)
    return ("Blocked", 42)


def _slot_label(run: ReportRun) -> str:
    reference = run.latest_sync_at or run.completed_at or run.started_at or run.created_at
    if reference is None:
        return "Awaiting schedule"
    return reference.astimezone(timezone.utc).strftime("%d %b • %H:%M UTC")


@router.get("/overview", response_model=DashboardOverviewResponse, status_code=status.HTTP_200_OK)
async def get_dashboard_overview(
    tenant_id: str = Query(min_length=1),
    project_id: str = Query(min_length=1),
    user: CurrentUser = Depends(require_roles(*DASHBOARD_READ_ROLES)),
    db: Session = Depends(get_db),
) -> DashboardOverviewResponse:
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

    company_profile = db.scalar(
        select(CompanyProfile)
        .where(CompanyProfile.project_id == project_id, CompanyProfile.tenant_id == tenant_id)
        .order_by(CompanyProfile.created_at.desc())
    )
    brand_kit = db.scalar(
        select(BrandKit)
        .where(BrandKit.project_id == project_id, BrandKit.tenant_id == tenant_id)
        .order_by(BrandKit.created_at.desc())
    )
    integrations = db.scalars(
        select(IntegrationConfig)
        .where(IntegrationConfig.project_id == project_id, IntegrationConfig.tenant_id == tenant_id)
        .order_by(IntegrationConfig.connector_type.asc())
    ).all()
    runs = db.scalars(
        select(ReportRun)
        .where(ReportRun.project_id == project_id, ReportRun.tenant_id == tenant_id)
        .order_by(ReportRun.created_at.desc())
        .limit(12)
    ).all()
    run_ids = [run.id for run in runs]

    packages = (
        db.scalars(select(ReportPackage).where(ReportPackage.report_run_id.in_(run_ids))).all()
        if run_ids
        else []
    )
    artifacts = (
        db.scalars(select(ReportArtifact).where(ReportArtifact.report_run_id.in_(run_ids))).all()
        if run_ids
        else []
    )
    verification_results = (
        db.scalars(select(VerificationResult).where(VerificationResult.report_run_id.in_(run_ids))).all()
        if run_ids
        else []
    )
    sync_jobs = db.scalars(
        select(ConnectorSyncJob)
        .where(ConnectorSyncJob.project_id == project_id, ConnectorSyncJob.tenant_id == tenant_id)
        .order_by(ConnectorSyncJob.created_at.desc())
    ).all()
    facts = db.scalars(
        select(CanonicalFact)
        .where(
            CanonicalFact.project_id == project_id,
            CanonicalFact.tenant_id == tenant_id,
            CanonicalFact.metric_code.in_(SPOTLIGHT_METRICS),
        )
        .order_by(CanonicalFact.metric_code.asc(), CanonicalFact.created_at.desc())
    ).all()
    documents = db.scalars(
        select(SourceDocument)
        .where(SourceDocument.project_id == project_id, SourceDocument.tenant_id == tenant_id)
        .order_by(SourceDocument.ingested_at.desc())
        .limit(6)
    ).all()
    document_count = db.query(SourceDocument).filter(
        SourceDocument.project_id == project_id,
        SourceDocument.tenant_id == tenant_id,
    ).count()
    extraction_count = db.query(ExtractionRecord).join(
        SourceDocument,
        SourceDocument.id == ExtractionRecord.source_document_id,
    ).filter(
        SourceDocument.project_id == project_id,
        SourceDocument.tenant_id == tenant_id,
    ).count()
    visual_count = db.query(ReportVisualAsset).filter(
        ReportVisualAsset.project_id == project_id,
        ReportVisualAsset.tenant_id == tenant_id,
    ).count()

    latest_job_by_connector: dict[str, ConnectorSyncJob] = {}
    for job in sync_jobs:
        if job.integration_config_id not in latest_job_by_connector:
            latest_job_by_connector[job.integration_config_id] = job

    package_by_run = {package.report_run_id: package for package in packages}

    metric_groups: dict[str, list[CanonicalFact]] = defaultdict(list)
    for fact in facts:
        metric_groups[fact.metric_code].append(fact)

    readiness_label, readiness_score = _readiness_payload(company_profile, brand_kit)
    hero = DashboardHero(
        tenant_name=tenant.name,
        company_name=company_profile.legal_name if company_profile is not None else project.name,
        project_name=project.name,
        project_code=project.code,
        sector=company_profile.sector if company_profile is not None else None,
        headquarters=company_profile.headquarters if company_profile is not None else None,
        reporting_currency=project.reporting_currency,
        blueprint_version=runs[0].report_blueprint_version if runs else None,
        readiness_label=readiness_label,
        readiness_score=readiness_score,
        summary=(
            "Live Report Factory performance across connector sync, verification pressure, "
            "package progress, and artifact readiness."
        ),
        logo_uri=resolve_brand_logo_uri(brand_kit),
        primary_color=brand_kit.primary_color if brand_kit is not None else None,
        accent_color=brand_kit.accent_color if brand_kit is not None else None,
    )

    completed_runs = [run for run in runs if run.status in {"completed", "published"}]
    average_quality = round(
        mean([run.report_quality_score for run in completed_runs if run.report_quality_score is not None]),
        1,
    ) if any(run.report_quality_score is not None for run in completed_runs) else None

    metrics: list[DashboardMetric] = [
        DashboardMetric(
            key="run-throughput",
            label="Run throughput",
            display_value=str(len(runs)),
            detail=f"{len([run for run in runs if run.status == 'published'])} published in recent cycle",
            status="good" if any(run.status == "published" for run in runs) else "attention",
            trend=[
                KpiTrendPoint(label=run.created_at.strftime("%d %b"), value=float(index + 1))
                for index, run in enumerate(reversed(runs[:6]))
            ],
        ),
        DashboardMetric(
            key="publish-ready",
            label="Publish ready",
            display_value=str(len([run for run in runs if run.publish_ready])),
            detail="Runs cleared for controlled publish",
            status="good" if any(run.publish_ready for run in runs) else "attention",
        ),
        DashboardMetric(
            key="report-quality",
            label="Report quality",
            display_value=f"{average_quality:.1f}" if average_quality is not None else "-",
            detail="Average package quality score",
            status="good" if (average_quality or 0) >= 84 else "attention",
            trend=[
                KpiTrendPoint(
                    label=run.created_at.strftime("%d %b"),
                    value=run.report_quality_score or 0,
                )
                for run in reversed(runs[:6])
                if run.report_quality_score is not None
            ],
        ),
        DashboardMetric(
            key="evidence-assets",
            label="Evidence assets",
            display_value=str(document_count),
            detail=f"{extraction_count} extraction records • {visual_count} visuals",
            status="good" if document_count >= 3 else "attention",
        ),
    ]

    for metric_code in SPOTLIGHT_METRICS:
        group = metric_groups.get(metric_code, [])
        if not group:
            continue
        current = group[0]
        previous = group[1] if len(group) > 1 else None
        metrics.append(
            DashboardMetric(
                key=metric_code.lower(),
                label=current.metric_name,
                display_value=_format_compact_number(current.value_numeric, current.unit),
                detail=f"{current.period_key} • {current.owner or current.source_system}",
                delta_text=_delta_text(
                    current.value_numeric,
                    previous.value_numeric if previous else None,
                    current.unit,
                ),
                status=_metric_status(
                    metric_code,
                    current.value_numeric,
                    previous.value_numeric if previous else None,
                ),
                trend=[
                    KpiTrendPoint(label=item.period_key, value=item.value_numeric or 0)
                    for item in reversed(group[:4])
                    if item.value_numeric is not None
                ],
            )
        )

    triage_run_ids = {
        item.report_run_id
        for item in verification_results
        if item.status in {"FAIL", "UNSURE"}
    }

    total_integrations = max(1, len(integrations))
    completed_sync_count = len(
        [
            integration
            for integration in integrations
            if (latest_job_by_connector.get(integration.id) and latest_job_by_connector[integration.id].status == "completed")
        ]
    )
    review_count = len(
        [
            run
            for run in runs
            if run.id in triage_run_ids or (run.status not in {"completed", "published"} and not run.publish_ready)
        ]
    )
    package_active_count = len([run for run in runs if run.package_status in {"queued", "running"}])
    published_count = len([run for run in runs if run.status == "published"])
    total_runs = max(1, len(runs))
    pipeline = [
        PipelineLane(
            lane_id="sync",
            label="Sync",
            count=completed_sync_count,
            total=total_integrations,
            ratio=completed_sync_count / total_integrations,
            status="good" if completed_sync_count == len(integrations) and integrations else "attention",
            description="Connectors with a completed latest sync job.",
        ),
        PipelineLane(
            lane_id="generate",
            label="Generate",
            count=len([run for run in runs if run.status in {"running", "completed", "published"}]),
            total=total_runs,
            ratio=len([run for run in runs if run.status in {"running", "completed", "published"}]) / total_runs,
            status="good" if runs else "neutral",
            description="Runs that have moved past initial orchestration bootstrap.",
        ),
        PipelineLane(
            lane_id="review",
            label="Review",
            count=review_count,
            total=total_runs,
            ratio=review_count / total_runs,
            status="attention" if review_count else "good",
            description="Triage and human approval workload waiting for action.",
        ),
        PipelineLane(
            lane_id="package",
            label="Package",
            count=package_active_count,
            total=total_runs,
            ratio=package_active_count / total_runs,
            status="attention" if package_active_count else "neutral",
            description="Runs currently in queued or running package generation.",
        ),
        PipelineLane(
            lane_id="publish",
            label="Publish",
            count=published_count,
            total=total_runs,
            ratio=published_count / total_runs,
            status="good" if published_count else "neutral",
            description="Runs with final package completed and published.",
        ),
    ]

    connector_health = [
        ConnectorHealthItem(
            connector_id=integration.id,
            connector_type=integration.connector_type,
            display_name=integration.display_name,
            status=integration.status,
            auth_mode=integration.auth_mode,
            support_tier=integration.support_tier,
            certified_variant=integration.certified_variant,
            health_band=integration.health_band,
            last_preflight_at_utc=_as_iso(integration.last_preflight_at),
            last_preview_sync_at_utc=_as_iso(integration.last_preview_sync_at),
            assigned_agent_status=get_assigned_agent_status(db=db, integration=integration),
            last_synced_at_utc=_as_iso(integration.last_synced_at),
            job_status=latest_job_by_connector.get(integration.id).status if latest_job_by_connector.get(integration.id) else None,
            current_stage=latest_job_by_connector.get(integration.id).current_stage if latest_job_by_connector.get(integration.id) else None,
            record_count=latest_job_by_connector.get(integration.id).record_count if latest_job_by_connector.get(integration.id) else 0,
            inserted_count=latest_job_by_connector.get(integration.id).inserted_count if latest_job_by_connector.get(integration.id) else 0,
            updated_count=latest_job_by_connector.get(integration.id).updated_count if latest_job_by_connector.get(integration.id) else 0,
            freshness_hours=_hours_since(integration.last_synced_at),
            status_tone=(
                "good"
                if connector_ready_for_launch(integration)
                else "attention"
                if integration.health_band == "amber"
                else "critical"
            ),
        )
        for integration in integrations
    ]

    risks = [
        RiskItem(
            risk_id="triage",
            title="Verifier triage pressure",
            severity="critical" if review_count >= 2 else "attention" if review_count else "good",
            count=review_count,
            detail="Runs blocked by FAIL / UNSURE verification or pending human approval.",
        ),
        RiskItem(
            risk_id="connectors",
            title="Connector freshness",
            severity=(
                "attention"
                if any(item.freshness_hours is None or item.freshness_hours > 24 for item in connector_health)
                else "good"
            ),
            count=len(
                [item for item in connector_health if item.freshness_hours is None or item.freshness_hours > 24]
            ),
            detail="Connectors without a recent sync need operator attention before packaging.",
        ),
        RiskItem(
            risk_id="verification",
            title="Verification blockers",
            severity=(
                "critical"
                if any(item.status == "FAIL" and item.severity == "critical" for item in verification_results)
                else "attention"
                if any(item.status == "FAIL" for item in verification_results)
                else "good"
            ),
            count=len([item for item in verification_results if item.status == "FAIL"]),
            detail="Claim-level FAIL results across recent run attempts.",
        ),
    ]

    schedule: list[ScheduleItem] = []
    for run in runs[:4]:
        if run.status == "published":
            title = "Published package ready"
            subtitle = "Artifacts available for download and audit trace."
            status_tone = "good"
        elif run.package_status in {"queued", "running"}:
            title = "Package generation in progress"
            subtitle = f"Current stage: {package_by_run.get(run.id).current_stage if package_by_run.get(run.id) else run.package_status}."
            status_tone = "attention"
        elif run.id in triage_run_ids:
            title = "Verifier triage required"
            subtitle = "Review FAIL / UNSURE claim cluster before publish."
            status_tone = "critical"
        elif run.status not in {"completed", "published"} and not run.publish_ready:
            title = "Execution or approval still open"
            subtitle = "The run has not cleared all workflow gates yet."
            status_tone = "attention"
        else:
            title = "Execution cycle active"
            subtitle = f"Run status is currently {run.status}."
            status_tone = "neutral"
        schedule.append(
            ScheduleItem(
                item_id=f"run-{run.id}",
                title=title,
                subtitle=subtitle,
                slot_label=_slot_label(run),
                status=status_tone,
                run_id=run.id,
            )
        )
    if not schedule:
        schedule.append(
            ScheduleItem(
                item_id="workspace-setup",
                title="Bootstrap the first report run",
                subtitle="Create a workspace, sync connectors, and launch a controlled publish cycle.",
                slot_label="Ready now",
                status="neutral",
            )
        )

    artifact_counts: dict[str, int] = defaultdict(int)
    for artifact in artifacts:
        artifact_counts[artifact.artifact_type] += 1
    artifact_health = [
        ArtifactHealthSummary(
            artifact_type=artifact_type,
            label=label,
            available=artifact_counts.get(artifact_type, 0),
            total_runs=len(runs),
            completion_ratio=(artifact_counts.get(artifact_type, 0) / max(1, len(runs))),
        )
        for artifact_type, label in ARTIFACT_LABELS.items()
    ]

    activity_feed: list[ActivityItem] = []
    for job in sync_jobs[:3]:
        activity_feed.append(
            ActivityItem(
                activity_id=f"sync-{job.id}",
                title="Connector sync updated",
                detail=f"{job.status} • {job.record_count} records • {job.current_stage}",
                category="connector_sync",
                status="good" if job.status == "completed" else "attention",
                occurred_at_utc=_as_iso(job.completed_at or job.started_at),
            )
        )
    for document in documents[:3]:
        activity_feed.append(
            ActivityItem(
                activity_id=f"doc-{document.id}",
                title="Evidence ingested",
                detail=f"{document.filename} • {document.document_type}",
                category="evidence",
                status="good",
                occurred_at_utc=_as_iso(document.ingested_at),
            )
        )
    if not activity_feed:
        activity_feed.append(
            ActivityItem(
                activity_id="empty",
                title="No activity yet",
                detail="Start with workspace bootstrap and connector sync to populate the board.",
                category="system",
                status="neutral",
            )
        )

    run_queue = [
        RunQueueItem(
            run_id=run.id,
            report_run_status=run.status,
            active_node=run.active_node if hasattr(run, "active_node") else "INIT_REQUEST",
            publish_ready=run.publish_ready,
            human_approval=run.human_approval if hasattr(run, "human_approval") else "pending",
            package_status=run.package_status,
            report_quality_score=run.report_quality_score,
            latest_sync_at_utc=_as_iso(run.latest_sync_at),
            visual_generation_status=run.visual_generation_status,
        )
        for run in runs[:6]
    ]

    return DashboardOverviewResponse(
        hero=hero,
        metrics=metrics,
        pipeline=pipeline,
        connector_health=connector_health,
        risks=risks,
        schedule=schedule,
        artifact_health=artifact_health,
        activity_feed=activity_feed[:6],
        run_queue=run_queue,
        generated_at_utc=_utcnow().isoformat(),
    )
