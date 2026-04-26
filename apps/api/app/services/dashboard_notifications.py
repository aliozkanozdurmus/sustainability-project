from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from app.models.core import AuditEvent, ConnectorSyncJob, IntegrationConfig, ReportRun, SourceDocument
from app.schemas.dashboard import NotificationItem, NotificationSourceRef


NOTIFICATION_STATUS_WEIGHT = {
    "critical": 0,
    "attention": 1,
    "good": 2,
    "neutral": 3,
}

NOTIFICATION_SURFACE_WEIGHT = {
    "publish_board": 0,
    "verifier_triage": 1,
    "connector_ops": 2,
    "evidence_center": 3,
    "run_monitor": 4,
    "dashboard": 5,
}

NOTIFICATION_PRIORITY_BY_STATUS = {
    "critical": "urgent",
    "attention": "high",
    "good": "medium",
    "neutral": "low",
}


def _notification_join_parts(*parts: object | None) -> str:
    return " • ".join(str(part) for part in parts if part not in {None, ""})


def _with_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _audit_event_category(event: AuditEvent) -> str:
    if event.event_type == "document_extraction_queue":
        return "document_extraction"
    if event.event_type in {"document_extraction", "document_indexing", "verification", "publish"}:
        return event.event_type
    return "system"


def _audit_event_status(event: AuditEvent) -> str:
    event_name = event.event_name
    if event_name in {"publish_failed", "publish_blocked", "verification_triage_required", "enqueue_failed"}:
        return "critical"
    if event_name.endswith("_failed") or event_name.endswith("_retry_exhausted"):
        return "critical"
    if event_name in {"publish_queued", "extraction_enqueued"}:
        return "attention"
    if event_name.endswith("_started") or event_name.endswith("_retry_scheduled"):
        return "attention"
    if event_name.endswith("_completed") or event_name == "verification_results_persisted":
        return "good"
    return "neutral"


def _audit_event_title(event: AuditEvent) -> str:
    mapping = {
        ("document_extraction_queue", "extraction_enqueued"): "Extraction queued",
        ("document_extraction_queue", "enqueue_failed"): "Extraction enqueue failed",
        ("document_extraction", "extraction_record_created"): "Extraction record created",
        ("document_extraction", "extraction_started"): "Extraction started",
        ("document_extraction", "extraction_completed"): "Extraction completed",
        ("document_extraction", "extraction_failed"): "Extraction failed",
        ("document_extraction", "extraction_retry_scheduled"): "Extraction retry scheduled",
        ("document_extraction", "extraction_retry_exhausted"): "Extraction retry exhausted",
        ("document_indexing", "indexing_started"): "Indexing started",
        ("document_indexing", "indexing_completed"): "Indexing completed",
        ("document_indexing", "indexing_failed"): "Indexing failed",
        ("document_indexing", "indexing_retry_scheduled"): "Indexing retry scheduled",
        ("document_indexing", "indexing_retry_exhausted"): "Indexing retry exhausted",
        ("verification", "verification_results_persisted"): "Verification updated",
        ("verification", "verification_triage_required"): "Verification triage required",
        ("publish", "publish_queued"): "Controlled publish queued",
        ("publish", "publish_blocked"): "Controlled publish blocked",
        ("publish", "publish_failed"): "Controlled publish failed",
        ("publish", "publish_completed"): "Controlled publish completed",
    }
    return mapping.get((event.event_type, event.event_name), event.event_name.replace("_", " ").title())


def _audit_event_detail(event: AuditEvent) -> str:
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    event_name = event.event_name

    if event_name == "extraction_enqueued":
        return _notification_join_parts("Awaiting OCR processing", payload.get("extraction_mode"))
    if event_name == "enqueue_failed":
        return "The extraction job could not be queued."
    if event_name == "extraction_record_created":
        return _notification_join_parts("Draft extraction record prepared", payload.get("mode"))
    if event_name == "extraction_started":
        return "OCR processing is now running."
    if event_name == "extraction_completed":
        return _notification_join_parts(
            f"{payload.get('chunk_count', 0)} chunks",
            f"Quality {payload.get('quality_score', '-')}",
        )
    if event_name == "extraction_failed":
        return str(payload.get("error") or "The extraction job failed.")
    if event_name == "extraction_retry_scheduled":
        return _notification_join_parts(
            f"Attempt {payload.get('attempt', '-')}",
            f"Retry in {payload.get('defer_seconds', '-')}s",
        )
    if event_name == "extraction_retry_exhausted":
        return str(payload.get("error") or "All extraction retries were exhausted.")
    if event_name == "indexing_started":
        return "Search indexing has started for the extracted evidence."
    if event_name == "indexing_completed":
        return _notification_join_parts(
            f"{payload.get('indexed_chunk_count', 0)} chunks",
            payload.get("index_name"),
        )
    if event_name == "indexing_failed":
        return str(payload.get("error") or "The indexing job failed.")
    if event_name == "indexing_retry_scheduled":
        return _notification_join_parts(
            f"Attempt {payload.get('attempt', '-')}",
            f"Retry in {payload.get('defer_seconds', '-')}s",
        )
    if event_name == "indexing_retry_exhausted":
        return str(payload.get("error") or "All indexing retries were exhausted.")
    if event_name == "verification_results_persisted":
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return _notification_join_parts(
            f"PASS {summary.get('pass_count', 0)}",
            f"FAIL {summary.get('fail_count', 0)}",
            f"UNSURE {summary.get('unsure_count', 0)}",
        )
    if event_name == "verification_triage_required":
        triage = payload.get("triage") if isinstance(payload.get("triage"), dict) else {}
        return _notification_join_parts(
            f"Critical FAIL {triage.get('critical_fail_count', 0)}",
            f"FAIL {triage.get('fail_count', 0)}",
            f"UNSURE {triage.get('unsure_count', 0)}",
        )
    if event_name == "publish_queued":
        return _notification_join_parts(payload.get("package_status"), payload.get("estimated_stage"))
    if event_name == "publish_blocked":
        blockers = payload.get("blockers")
        if isinstance(blockers, list):
            return f"{len(blockers)} publish blockers require operator review."
        return "The publish gate blocked this run."
    if event_name == "publish_failed":
        return str(payload.get("reason") or "The publish job failed.")
    if event_name == "publish_completed":
        artifacts = payload.get("artifacts")
        artifact_count = len(artifacts) if isinstance(artifacts, list) else 0
        report_pdf = payload.get("report_pdf") if isinstance(payload.get("report_pdf"), dict) else {}
        return _notification_join_parts(
            f"{artifact_count} artifacts ready",
            report_pdf.get("filename"),
        )

    return str(payload) if payload else "Operational activity recorded."


def _resolve_surface(category: str, title: str) -> str:
    if category == "publish":
        return "publish_board"
    if category == "verification":
        return "verifier_triage"
    if category == "connector_sync":
        return "connector_ops"
    if category in {"document_upload", "document_extraction", "document_indexing"}:
        return "evidence_center"
    if category == "report_run":
        return "run_monitor"
    if "triage" in title.lower():
        return "verifier_triage"
    return "dashboard"


def _resolve_action_path(
    *,
    category: str,
    source_ref: NotificationSourceRef | None,
) -> str | None:
    if source_ref is None:
        return "/dashboard"
    if category in {"publish", "verification", "report_run"} and source_ref.run_id:
        return f"/approval-center?runId={source_ref.run_id}"
    if category == "connector_sync" and source_ref.integration_id:
        return f"/integrations/setup?integrationId={source_ref.integration_id}"
    if category in {"document_upload", "document_extraction", "document_indexing"} and source_ref.document_id:
        return f"/evidence-center?documentId={source_ref.document_id}"
    return "/dashboard"


def _build_rank(status: str, surface: str) -> int:
    return (NOTIFICATION_STATUS_WEIGHT[status] * 100) + (NOTIFICATION_SURFACE_WEIGHT[surface] * 10)


def _decorate_notification(item: NotificationItem) -> NotificationItem:
    surface = _resolve_surface(item.category, item.title)
    source_ref = item.source_ref or None
    action_path = _resolve_action_path(category=item.category, source_ref=source_ref)
    sort_rank = _build_rank(item.status, surface)
    priority = NOTIFICATION_PRIORITY_BY_STATUS[item.status]
    return item.model_copy(
        update={
            "priority": priority,
            "surface": surface,
            "action_path": action_path,
            "sort_rank": sort_rank,
        }
    )


def _build_audit_notification(event: AuditEvent) -> tuple[datetime, NotificationItem]:
    occurred_at = _with_utc(event.occurred_at)
    payload = event.event_payload if isinstance(event.event_payload, dict) else {}
    document_id = payload.get("document_id") if isinstance(payload.get("document_id"), str) else None
    integration_id = payload.get("integration_id") if isinstance(payload.get("integration_id"), str) else None
    return (
        occurred_at,
        _decorate_notification(
            NotificationItem(
                notification_id=f"audit:{event.id}",
                title=_audit_event_title(event),
                detail=_audit_event_detail(event),
                category=_audit_event_category(event),  # type: ignore[arg-type]
                status=_audit_event_status(event),  # type: ignore[arg-type]
                occurred_at_utc=occurred_at.isoformat(),
                source_ref=NotificationSourceRef(
                    run_id=event.report_run_id,
                    document_id=document_id,
                    integration_id=integration_id,
                    audit_event_id=event.id,
                ),
            )
        ),
    )


def _build_connector_sync_notification(
    job: ConnectorSyncJob,
    integration: IntegrationConfig | None,
) -> tuple[datetime, NotificationItem]:
    occurred_at = _with_utc(job.completed_at or job.started_at or job.created_at)
    status = "good" if job.status == "completed" else "critical" if job.status == "failed" else "attention"
    title = (
        "Connector sync completed"
        if job.status == "completed"
        else "Connector sync failed"
        if job.status == "failed"
        else "Connector sync active"
    )
    connector_label = integration.display_name if integration is not None else "Connector"
    return (
        occurred_at,
        _decorate_notification(
            NotificationItem(
                notification_id=f"connector_sync:{job.id}:{job.status}",
                title=title,
                detail=_notification_join_parts(
                    connector_label,
                    job.current_stage,
                    f"{job.record_count} records",
                ),
                category="connector_sync",
                status=status,  # type: ignore[arg-type]
                occurred_at_utc=occurred_at.isoformat(),
                source_ref=NotificationSourceRef(integration_id=job.integration_config_id),
            )
        ),
    )


def _build_document_upload_notification(document: SourceDocument) -> tuple[datetime, NotificationItem]:
    occurred_at = _with_utc(document.ingested_at)
    return (
        occurred_at,
        _decorate_notification(
            NotificationItem(
                notification_id=f"document_upload:{document.id}:uploaded",
                title="Evidence uploaded",
                detail=_notification_join_parts(document.filename, document.document_type),
                category="document_upload",
                status="neutral",
                occurred_at_utc=occurred_at.isoformat(),
                source_ref=NotificationSourceRef(document_id=document.id),
            )
        ),
    )


def _build_run_notifications(run: ReportRun) -> list[tuple[datetime, NotificationItem]]:
    notifications: list[tuple[datetime, NotificationItem]] = []
    created_at = _with_utc(run.created_at)
    notifications.append(
        (
            created_at,
            _decorate_notification(
                NotificationItem(
                    notification_id=f"report_run:{run.id}:created",
                    title="Report run created",
                    detail=_notification_join_parts(run.report_blueprint_version or "Blueprint pending", run.status),
                    category="report_run",
                    status="neutral",
                    occurred_at_utc=created_at.isoformat(),
                    source_ref=NotificationSourceRef(run_id=run.id),
                )
            ),
        )
    )
    if run.completed_at is not None:
        completed_at = _with_utc(run.completed_at)
        completed_status = "good" if run.status in {"completed", "published"} else "critical"
        notifications.append(
            (
                completed_at,
                _decorate_notification(
                    NotificationItem(
                        notification_id=f"report_run:{run.id}:completed",
                        title="Report run completed",
                        detail=_notification_join_parts(
                            run.status,
                            f"Quality {run.report_quality_score:.1f}" if run.report_quality_score is not None else None,
                        ),
                        category="report_run",
                        status=completed_status,  # type: ignore[arg-type]
                        occurred_at_utc=completed_at.isoformat(),
                        source_ref=NotificationSourceRef(run_id=run.id),
                    )
                ),
            )
        )
    if run.status == "published" and run.completed_at is not None:
        published_at = _with_utc(run.completed_at)
        notifications.append(
            (
                published_at,
                _decorate_notification(
                    NotificationItem(
                        notification_id=f"report_run:{run.id}:published",
                        title="Report published",
                        detail=_notification_join_parts(run.package_status, "Artifacts available for review"),
                        category="report_run",
                        status="good",
                        occurred_at_utc=published_at.isoformat(),
                        source_ref=NotificationSourceRef(run_id=run.id),
                    )
                ),
            )
        )
    return notifications


def _sort_key(item: tuple[datetime, NotificationItem]) -> tuple[int, datetime, str]:
    occurred_at, notification = item
    return (
        notification.sort_rank,
        occurred_at,
        notification.notification_id,
    )


def build_dashboard_notifications(
    *,
    audit_events: Iterable[AuditEvent],
    sync_jobs: Iterable[ConnectorSyncJob],
    documents: Iterable[SourceDocument],
    runs: Iterable[ReportRun],
    integration_by_id: dict[str, IntegrationConfig],
    limit: int,
) -> list[NotificationItem]:
    notifications: list[tuple[datetime, NotificationItem]] = []
    notifications.extend(_build_audit_notification(event) for event in audit_events)
    notifications.extend(
        _build_connector_sync_notification(job, integration_by_id.get(job.integration_config_id))
        for job in sync_jobs
    )
    notifications.extend(_build_document_upload_notification(document) for document in documents)
    for run in runs:
        notifications.extend(_build_run_notifications(run))

    notifications.sort(
        key=lambda item: (
            item[1].sort_rank,
            -item[0].timestamp(),
            item[1].notification_id,
        )
    )
    return [item for _, item in notifications[:limit]]
