from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import CanonicalFact, ConnectorSyncJob, IntegrationConfig


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


CONNECTOR_TYPE_ALIASES = {
    "sap": "sap_odata",
    "sap_odata": "sap_odata",
    "logo": "logo_tiger_sql_view",
    "logo_tiger": "logo_tiger_sql_view",
    "logo_tiger_sql_view": "logo_tiger_sql_view",
    "netsis": "netsis_rest",
    "netsis_rest": "netsis_rest",
}


DEFAULT_CONNECTOR_FACTS: dict[str, list[dict[str, Any]]] = {
    "sap_odata": [
        {
            "metric_code": "E_SCOPE2_TCO2E",
            "metric_name": "Scope 2 Emissions",
            "period_key": "2025",
            "unit": "tCO2e",
            "value_numeric": 12450.0,
            "owner": "energy@company.local",
            "source_record_id": "sap-scope2-2025",
            "trace_ref": "sap://scope2/2025",
        },
        {
            "metric_code": "E_SCOPE2_TCO2E_PREV",
            "metric_name": "Scope 2 Emissions Previous Year",
            "period_key": "2024",
            "unit": "tCO2e",
            "value_numeric": 14670.0,
            "owner": "energy@company.local",
            "source_record_id": "sap-scope2-2024",
            "trace_ref": "sap://scope2/2024",
        },
        {
            "metric_code": "RENEWABLE_ELECTRICITY_SHARE",
            "metric_name": "Renewable Electricity Share",
            "period_key": "2025",
            "unit": "%",
            "value_numeric": 42.0,
            "owner": "energy@company.local",
            "source_record_id": "sap-renewable-share-2025",
            "trace_ref": "sap://renewable-share/2025",
        },
        {
            "metric_code": "ENERGY_INTENSITY_REDUCTION",
            "metric_name": "Energy Intensity Reduction",
            "period_key": "2025",
            "unit": "%",
            "value_numeric": 8.4,
            "owner": "energy@company.local",
            "source_record_id": "sap-energy-reduction-2025",
            "trace_ref": "sap://energy-reduction/2025",
        },
        {
            "metric_code": "BOARD_OVERSIGHT_COVERAGE",
            "metric_name": "Board Oversight Coverage",
            "period_key": "2025",
            "unit": "%",
            "value_numeric": 100.0,
            "owner": "governance@company.local",
            "source_record_id": "sap-board-oversight-2025",
            "trace_ref": "sap://board-oversight/2025",
        },
    ],
    "logo_tiger_sql_view": [
        {
            "metric_code": "WORKFORCE_HEADCOUNT",
            "metric_name": "Workforce Headcount",
            "period_key": "2025",
            "unit": "employee",
            "value_numeric": 1850.0,
            "owner": "hr@company.local",
            "source_record_id": "logo-headcount-2025",
            "trace_ref": "logo://headcount/2025",
        },
        {
            "metric_code": "LTIFR",
            "metric_name": "Lost Time Injury Frequency Rate",
            "period_key": "2025",
            "unit": "rate",
            "value_numeric": 0.48,
            "owner": "ehs@company.local",
            "source_record_id": "logo-ltifr-2025",
            "trace_ref": "logo://ltifr/2025",
        },
        {
            "metric_code": "LTIFR_PREV",
            "metric_name": "Lost Time Injury Frequency Rate Previous Year",
            "period_key": "2024",
            "unit": "rate",
            "value_numeric": 0.62,
            "owner": "ehs@company.local",
            "source_record_id": "logo-ltifr-2024",
            "trace_ref": "logo://ltifr/2024",
        },
        {
            "metric_code": "SUSTAINABILITY_COMMITTEE_MEETINGS",
            "metric_name": "Sustainability Committee Meetings",
            "period_key": "2025",
            "unit": "count",
            "value_numeric": 12.0,
            "owner": "governance@company.local",
            "source_record_id": "logo-committee-meetings-2025",
            "trace_ref": "logo://committee/2025",
        },
    ],
    "netsis_rest": [
        {
            "metric_code": "SUPPLIER_COVERAGE",
            "metric_name": "Supplier Code of Conduct Coverage",
            "period_key": "2025",
            "unit": "%",
            "value_numeric": 96.0,
            "owner": "procurement@company.local",
            "source_record_id": "netsis-supplier-coverage-2025",
            "trace_ref": "netsis://supplier-coverage/2025",
        },
        {
            "metric_code": "HIGH_RISK_SUPPLIER_SCREENING",
            "metric_name": "High Risk Supplier Screening Completion",
            "period_key": "2025",
            "unit": "%",
            "value_numeric": 93.0,
            "owner": "procurement@company.local",
            "source_record_id": "netsis-high-risk-screening-2025",
            "trace_ref": "netsis://high-risk-screening/2025",
        },
        {
            "metric_code": "MATERIAL_TOPIC_COUNT",
            "metric_name": "Material Topic Count",
            "period_key": "2025",
            "unit": "count",
            "value_numeric": 9.0,
            "owner": "sustainability@company.local",
            "source_record_id": "netsis-material-topic-count-2025",
            "trace_ref": "netsis://materiality/topics/2025",
        },
        {
            "metric_code": "STAKEHOLDER_ENGAGEMENT_TOUCHPOINTS",
            "metric_name": "Stakeholder Engagement Touchpoints",
            "period_key": "2025",
            "unit": "count",
            "value_numeric": 37.0,
            "owner": "sustainability@company.local",
            "source_record_id": "netsis-touchpoints-2025",
            "trace_ref": "netsis://materiality/touchpoints/2025",
        },
    ],
}


@dataclass(frozen=True)
class NormalizedFactInput:
    metric_code: str
    metric_name: str
    period_key: str
    unit: str | None
    value_numeric: float | None
    value_text: str | None
    source_system: str
    source_record_id: str
    owner: str | None
    freshness_at: datetime
    confidence_score: float
    trace_ref: str
    metadata_json: dict[str, Any]


def normalize_connector_type(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return CONNECTOR_TYPE_ALIASES.get(normalized, normalized)


def _coerce_records(config: IntegrationConfig) -> list[dict[str, Any]]:
    payload = config.sample_payload or {}
    for key in ("records", "value", "rows", "items", "results"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    default_rows = DEFAULT_CONNECTOR_FACTS.get(config.connector_type, [])
    return [dict(row) for row in default_rows]


def _normalize_row(config: IntegrationConfig, row: dict[str, Any], row_index: int) -> NormalizedFactInput:
    metric_code = str(row.get("metric_code") or row.get("metricCode") or "").strip().upper()
    metric_name = str(row.get("metric_name") or row.get("metricName") or metric_code).strip() or metric_code
    period_key = str(row.get("period_key") or row.get("period") or row.get("year") or "2025").strip()
    unit_raw = row.get("unit")
    unit = str(unit_raw).strip() if unit_raw is not None and str(unit_raw).strip() else None
    numeric_raw = row.get("value_numeric", row.get("valueNumeric", row.get("value")))
    value_numeric = float(numeric_raw) if isinstance(numeric_raw, (int, float)) else None
    if value_numeric is None:
        try:
            value_numeric = float(str(numeric_raw))
        except (TypeError, ValueError):
            value_numeric = None
    value_text_raw = row.get("value_text", row.get("valueText"))
    value_text = str(value_text_raw).strip() if value_text_raw is not None else None
    source_record_id = (
        str(row.get("source_record_id") or row.get("sourceRecordId") or row.get("id") or "").strip()
        or f"{config.connector_type}-{metric_code}-{period_key}-{row_index}"
    )
    owner = str(row.get("owner") or "").strip() or None
    trace_ref = (
        str(row.get("trace_ref") or row.get("traceRef") or "").strip()
        or f"{config.connector_type}://{source_record_id}"
    )
    freshness_raw = row.get("freshness_at") or row.get("freshnessAt")
    freshness_at = _utcnow()
    if isinstance(freshness_raw, str) and freshness_raw.strip():
        try:
            freshness_at = datetime.fromisoformat(freshness_raw.replace("Z", "+00:00"))
        except ValueError:
            freshness_at = _utcnow()
    confidence_raw = row.get("confidence_score", row.get("confidenceScore", 0.95))
    confidence_score = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.95

    metadata = {
        key: value
        for key, value in row.items()
        if key
        not in {
            "metric_code",
            "metricCode",
            "metric_name",
            "metricName",
            "period_key",
            "period",
            "year",
            "unit",
            "value_numeric",
            "valueNumeric",
            "value",
            "value_text",
            "valueText",
            "source_record_id",
            "sourceRecordId",
            "id",
            "owner",
            "trace_ref",
            "traceRef",
            "freshness_at",
            "freshnessAt",
            "confidence_score",
            "confidenceScore",
        }
    }

    if not metric_code:
        raise ValueError(f"Connector row is missing metric_code for {config.connector_type}.")

    return NormalizedFactInput(
        metric_code=metric_code,
        metric_name=metric_name,
        period_key=period_key,
        unit=unit,
        value_numeric=value_numeric,
        value_text=value_text,
        source_system=config.connector_type,
        source_record_id=source_record_id,
        owner=owner,
        freshness_at=freshness_at,
        confidence_score=confidence_score,
        trace_ref=trace_ref,
        metadata_json=metadata,
    )


def upsert_integration_config(
    *,
    db: Session,
    tenant_id: str,
    project_id: str,
    connector_type: str,
    display_name: str,
    auth_mode: str,
    base_url: str | None,
    resource_path: str | None,
    mapping_version: str,
    connection_payload: dict[str, Any],
    sample_payload: dict[str, Any],
) -> IntegrationConfig:
    normalized_type = normalize_connector_type(connector_type)
    integration = db.scalar(
        select(IntegrationConfig).where(
            IntegrationConfig.project_id == project_id,
            IntegrationConfig.connector_type == normalized_type,
        )
    )
    if integration is None:
        integration = IntegrationConfig(
            tenant_id=tenant_id,
            project_id=project_id,
            connector_type=normalized_type,
            display_name=display_name,
            auth_mode=auth_mode,
            base_url=base_url,
            resource_path=resource_path,
            status="active",
            mapping_version=mapping_version,
            connection_payload=connection_payload,
            sample_payload=sample_payload,
        )
        db.add(integration)
        db.flush()
        return integration

    integration.display_name = display_name
    integration.auth_mode = auth_mode
    integration.base_url = base_url
    integration.resource_path = resource_path
    integration.mapping_version = mapping_version
    integration.connection_payload = connection_payload
    integration.sample_payload = sample_payload
    integration.status = "active"
    db.flush()
    return integration


def run_connector_sync(*, db: Session, integration: IntegrationConfig) -> ConnectorSyncJob:
    started_at = _utcnow()
    job = ConnectorSyncJob(
        integration_config_id=integration.id,
        tenant_id=integration.tenant_id,
        project_id=integration.project_id,
        status="running",
        current_stage="normalize",
        cursor_before=integration.last_cursor,
        started_at=started_at,
        diagnostics_json={},
    )
    db.add(job)
    db.flush()

    normalized_rows = [
        _normalize_row(integration, row, row_index)
        for row_index, row in enumerate(_coerce_records(integration), start=1)
    ]

    inserted_count = 0
    updated_count = 0
    for normalized in normalized_rows:
        existing = db.scalar(
            select(CanonicalFact).where(
                CanonicalFact.integration_config_id == integration.id,
                CanonicalFact.metric_code == normalized.metric_code,
                CanonicalFact.period_key == normalized.period_key,
                CanonicalFact.source_record_id == normalized.source_record_id,
            )
        )
        if existing is None:
            db.add(
                CanonicalFact(
                    tenant_id=integration.tenant_id,
                    project_id=integration.project_id,
                    integration_config_id=integration.id,
                    sync_job_id=job.id,
                    metric_code=normalized.metric_code,
                    metric_name=normalized.metric_name,
                    period_key=normalized.period_key,
                    unit=normalized.unit,
                    value_numeric=normalized.value_numeric,
                    value_text=normalized.value_text,
                    source_system=normalized.source_system,
                    source_record_id=normalized.source_record_id,
                    owner=normalized.owner,
                    freshness_at=normalized.freshness_at,
                    confidence_score=normalized.confidence_score,
                    trace_ref=normalized.trace_ref,
                    metadata_json=normalized.metadata_json,
                )
            )
            inserted_count += 1
            continue

        existing.sync_job_id = job.id
        existing.metric_name = normalized.metric_name
        existing.unit = normalized.unit
        existing.value_numeric = normalized.value_numeric
        existing.value_text = normalized.value_text
        existing.owner = normalized.owner
        existing.freshness_at = normalized.freshness_at
        existing.confidence_score = normalized.confidence_score
        existing.trace_ref = normalized.trace_ref
        existing.metadata_json = normalized.metadata_json
        updated_count += 1

    completed_at = _utcnow()
    integration.last_cursor = completed_at.isoformat()
    integration.last_synced_at = completed_at

    job.status = "completed"
    job.current_stage = "completed"
    job.record_count = len(normalized_rows)
    job.inserted_count = inserted_count
    job.updated_count = updated_count
    job.cursor_after = integration.last_cursor
    job.completed_at = completed_at
    job.diagnostics_json = {
        "connector_type": integration.connector_type,
        "normalized_metrics": sorted({row.metric_code for row in normalized_rows}),
    }
    db.flush()
    return job
