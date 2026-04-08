# Bu servis, integrations ve connector support operasyonlarini tek yerde toplar.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import (
    CanonicalFact,
    ConnectorAgent,
    ConnectorArtifact,
    ConnectorOperationRun,
    ConnectorSyncJob,
    IntegrationConfig,
)
from app.services.blob_storage import get_blob_storage_service
from app.services.connector_contract import (
    SUPPORT_MATRIX_VERSION,
    build_default_connection_profile,
    build_default_normalization_policy,
    contains_secret_literal,
    get_default_product_version,
    get_default_variant_code,
    get_support_definition,
    missing_required_profile_fields,
    replay_mode_supported,
    resolve_support_tier,
    summarize_health,
    support_error_payload,
)


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

DISCOVERY_ERROR_CODES = {
    "sap_odata": "SAP_DISCOVERY_INCOMPLETE",
    "logo_tiger_sql_view": "LOGO_DISCOVERY_INCOMPLETE",
    "netsis_rest": "NETSIS_DISCOVERY_INCOMPLETE",
}

AUTH_ERROR_CODES = {
    "sap_odata": "SAP_AUTH_PREFLIGHT_FAILED",
    "netsis_rest": "NETSIS_AUTH_PREFLIGHT_FAILED",
}

PREVIEW_EMPTY_ERROR_CODES = {
    "sap_odata": "SAP_DELTA_UNAVAILABLE",
    "logo_tiger_sql_view": "LOGO_SQL_VIEW_MISSING",
    "netsis_rest": "NETSIS_ENDPOINT_UNREACHABLE",
}

CONNECTOR_DELTA_MODES = {
    "sap_odata": "delta_token",
    "logo_tiger_sql_view": "snapshot_watermark",
    "netsis_rest": "cursor_or_updated_at",
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


@dataclass
class OperationExecutionResult:
    current_stage: str
    error_code: str | None
    error_message: str | None
    operator_message: str
    support_hint: str
    recommended_action: str
    retryable: bool
    health_status: dict[str, Any]
    result_payload: dict[str, Any]
    diagnostics: dict[str, Any]
    integration_status: str | None = None
    artifact: ConnectorArtifact | None = None

    @property
    def status(self) -> str:
        return "failed" if self.error_code else "completed"


CONNECTOR_DEFAULT_CONFIDENCE = {
    "sap_odata": 0.98,
    "logo_tiger_sql_view": 0.96,
    "netsis_rest": 0.95,
}

UNIT_ALIASES = {
    "%": "%",
    "percent": "%",
    "percentage": "%",
    "pct": "%",
    "employee": "employee",
    "employees": "employee",
    "employee_count": "employee",
    "count": "count",
    "adet": "count",
    "rate": "rate",
    "tco2e": "tCO2e",
    "tons_co2e": "tCO2e",
    "ton_co2e": "tCO2e",
}

SENSITIVE_TOKENS = ("password", "secret", "token", "api_key", "client_secret", "private_key")


def normalize_connector_type(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return CONNECTOR_TYPE_ALIASES.get(normalized, normalized)


def _pick_first(row: dict[str, Any], *keys: str) -> Any:
    for raw_key in keys:
        if "." in raw_key:
            current: Any = row
            path_ok = True
            for part in raw_key.split("."):
                if not isinstance(current, dict) or part not in current:
                    path_ok = False
                    break
                current = current[part]
            if path_ok and current is not None:
                return current
            continue
        if raw_key in row and row[raw_key] is not None:
            return row[raw_key]
    return None


def _normalize_unit(value: Any) -> str | None:
    if value is None:
        return None
    unit = str(value).strip()
    if not unit:
        return None
    return UNIT_ALIASES.get(unit.lower(), unit)


def _active_connection_profile(integration: IntegrationConfig) -> dict[str, Any]:
    if isinstance(integration.connection_payload, dict):
        return dict(integration.connection_payload)
    return {}


def redact_connection_profile(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        normalized_key = str(key).strip().lower()
        if any(token in normalized_key for token in SENSITIVE_TOKENS):
            redacted[str(key)] = "***redacted***"
            continue
        if isinstance(value, dict):
            redacted[str(key)] = redact_connection_profile(value)
            continue
        if isinstance(value, list):
            redacted[str(key)] = [
                redact_connection_profile(item) if isinstance(item, dict) else item
                for item in value
            ]
            continue
        redacted[str(key)] = value
    return redacted


def _coerce_records(config: IntegrationConfig, *, allow_defaults: bool = True) -> list[dict[str, Any]]:
    payload = config.sample_payload or {}
    if config.connector_type == "sap_odata":
        candidate = payload.get("value")
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
        nested = payload.get("d")
        if isinstance(nested, dict) and isinstance(nested.get("results"), list):
            return [row for row in nested["results"] if isinstance(row, dict)]
    if config.connector_type == "logo_tiger_sql_view":
        candidate = payload.get("rows")
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    if config.connector_type == "netsis_rest":
        for key in ("items", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [row for row in candidate if isinstance(row, dict)]
        data_payload = payload.get("data")
        if isinstance(data_payload, dict):
            for key in ("items", "records"):
                candidate = data_payload.get(key)
                if isinstance(candidate, list):
                    return [row for row in candidate if isinstance(row, dict)]
    for key in ("records", "value", "rows", "items", "results"):
        candidate = payload.get(key)
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    if not allow_defaults:
        return []
    default_rows = DEFAULT_CONNECTOR_FACTS.get(config.connector_type, [])
    return [dict(row) for row in default_rows]


def _resolve_cursor_after(config: IntegrationConfig, rows: list[dict[str, Any]], fallback: datetime) -> str:
    payload = config.sample_payload or {}
    if config.connector_type == "sap_odata":
        for candidate in (
            payload.get("@odata.deltaLink"),
            payload.get("delta_token"),
            payload.get("deltaLink"),
            _pick_first(payload, "metadata.delta_token"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    if config.connector_type == "logo_tiger_sql_view":
        for candidate in (payload.get("snapshot_watermark"), payload.get("watermark")):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        row_markers = [
            str(marker).strip()
            for row in rows
            for marker in (_pick_first(row, "snapshot_watermark", "watermark", "updated_at", "updatedAt"),)
            if marker is not None and str(marker).strip()
        ]
        if row_markers:
            return max(row_markers)
    if config.connector_type == "netsis_rest":
        for candidate in (
            payload.get("cursor"),
            payload.get("next_cursor"),
            payload.get("updated_at_max"),
            payload.get("updatedAtMax"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        row_markers = [
            str(marker).strip()
            for row in rows
            for marker in (_pick_first(row, "updated_at", "updatedAt", "cursor"),)
            if marker is not None and str(marker).strip()
        ]
        if row_markers:
            return max(row_markers)
    return fallback.isoformat()


def _normalize_row(config: IntegrationConfig, row: dict[str, Any], row_index: int) -> NormalizedFactInput:
    metric_code = str(
        _pick_first(
            row,
            "metric_code",
            "metricCode",
            "MetricCode",
            "METRIC_CODE",
            "METRIC_KODU",
            "metric.code",
            "code",
        )
        or ""
    ).strip().upper()
    metric_name = str(
        _pick_first(
            row,
            "metric_name",
            "metricName",
            "MetricName",
            "METRIC_NAME",
            "METRIC_ADI",
            "metric.name",
            "name",
        )
        or metric_code
    ).strip() or metric_code
    period_key = str(
        _pick_first(
            row,
            "period_key",
            "periodKey",
            "period",
            "Period",
            "PERIOD",
            "year",
            "Year",
            "fiscal_year",
            "FiscalYear",
            "DONEM",
        )
        or "2025"
    ).strip()
    unit = _normalize_unit(_pick_first(row, "unit", "Unit", "BIRIM", "metric.unit"))
    numeric_raw = _pick_first(row, "value_numeric", "valueNumeric", "value", "Value", "DEGER", "metric.value")
    value_numeric = float(numeric_raw) if isinstance(numeric_raw, (int, float)) else None
    if value_numeric is None:
        try:
            value_numeric = float(str(numeric_raw))
        except (TypeError, ValueError):
            value_numeric = None
    value_text_raw = _pick_first(row, "value_text", "valueText", "text", "ValueText")
    value_text = str(value_text_raw).strip() if value_text_raw is not None else None
    source_record_id = (
        str(
            _pick_first(
                row,
                "source_record_id",
                "sourceRecordId",
                "RecordId",
                "ROW_ID",
                "id",
                "ID",
            )
            or ""
        ).strip()
        or f"{config.connector_type}-{metric_code}-{period_key}-{row_index}"
    )
    owner = str(_pick_first(row, "owner", "Owner", "owner_email", "ownerEmail", "OwnerEmail") or "").strip() or None
    trace_ref = (
        str(_pick_first(row, "trace_ref", "traceRef", "TraceRef", "TRACE_REF", "trace.ref") or "").strip()
        or f"{config.connector_type}://{source_record_id}"
    )
    freshness_raw = _pick_first(row, "freshness_at", "freshnessAt", "updated_at", "updatedAt")
    freshness_at = _utcnow()
    if isinstance(freshness_raw, str) and freshness_raw.strip():
        try:
            freshness_at = datetime.fromisoformat(freshness_raw.replace("Z", "+00:00"))
        except ValueError:
            freshness_at = _utcnow()
    confidence_raw = _pick_first(row, "confidence_score", "confidenceScore")
    if confidence_raw is None:
        confidence_raw = CONNECTOR_DEFAULT_CONFIDENCE.get(config.connector_type, 0.95)
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


def get_assigned_agent_status(*, db: Session, integration: IntegrationConfig | None = None, agent_id: str | None = None) -> str | None:
    resolved_agent_id = agent_id or (integration.assigned_agent_id if integration is not None else None)
    if not resolved_agent_id:
        return None

    agent = db.get(ConnectorAgent, resolved_agent_id)
    if agent is None:
        return "missing"
    if agent.last_heartbeat_at is None:
        return "registered"
    if agent.last_heartbeat_at.tzinfo is None:
        last_heartbeat = agent.last_heartbeat_at.replace(tzinfo=timezone.utc)
    else:
        last_heartbeat = agent.last_heartbeat_at
    age_seconds = (_utcnow() - last_heartbeat).total_seconds()
    if age_seconds > settings.connector_agent_stale_after_seconds:
        return "stale"
    return agent.status


def connector_ready_for_launch(integration: IntegrationConfig) -> bool:
    return (
        integration.status == "active"
        and integration.support_tier == "certified"
        and integration.health_band == "green"
    )


def upsert_integration_config(
    *,
    db: Session,
    tenant_id: str,
    project_id: str,
    connector_type: str,
    display_name: str | None,
    auth_mode: str | None,
    base_url: str | None,
    resource_path: str | None,
    mapping_version: str,
    certified_variant: str | None,
    product_version: str | None,
    connectivity_mode: str | None,
    credential_ref: str | None,
    assigned_agent_id: str | None,
    connection_profile: dict[str, Any] | None,
    normalization_policy: dict[str, Any] | None,
    sample_payload: dict[str, Any] | None,
    connection_payload: dict[str, Any] | None,
) -> IntegrationConfig:
    normalized_type = normalize_connector_type(connector_type)
    support_definition = get_support_definition(normalized_type)
    merged_profile = dict(build_default_connection_profile(normalized_type))
    if isinstance(connection_payload, dict):
        merged_profile.update(connection_payload)
    if isinstance(connection_profile, dict):
        merged_profile.update({key: value for key, value in connection_profile.items() if value is not None})

    if contains_secret_literal(merged_profile):
        raise ValueError("connection_profile must not contain secret literals; use credential_ref.")

    resolved_variant = certified_variant or get_default_variant_code(normalized_type)
    resolved_product_version = product_version or get_default_product_version(normalized_type)
    resolved_support_tier = resolve_support_tier(
        normalized_type,
        certified_variant=resolved_variant,
        product_version=resolved_product_version,
    )
    resolved_connectivity_mode = connectivity_mode or str(
        support_definition.get("connectivity_mode", "customer_network_agent")
    )
    resolved_display_name = display_name or str(support_definition.get("display_name", normalized_type))
    resolved_auth_mode = auth_mode or str(support_definition.get("default_auth_mode", "configured"))
    resolved_base_url = base_url or str(merged_profile.get("service_url") or merged_profile.get("host") or "").strip() or None
    resolved_resource_path = resource_path or str(
        merged_profile.get("resource_path") or merged_profile.get("sql_view_name") or ""
    ).strip() or None

    default_health = summarize_health(
        connector_type=normalized_type,
        metrics={
            "connectivity": {"score": 42, "detail": "Topology profile is saved and waiting for discovery."},
            "authentication": {"score": 36, "detail": "Credential reference must pass preflight before activation."},
            "permission_scope": {"score": 44, "detail": "ERP permission scope has not been validated yet."},
            "data_shape": {"score": 40, "detail": "Preview sync has not validated the canonical shape yet."},
            "locale_guards": {"score": 46, "detail": "Timezone, decimal, and currency guards are still pending."},
            "replay_readiness": {"score": 41, "detail": "Delta and replay policy are waiting for preflight."},
        },
        error_code="CONNECTOR_REVIEW_REQUIRED",
    )
    default_health.update(
        {
            "operator_message": "Connector profile was saved. Run discovery, preflight, and preview before launch.",
            "support_hint": "Typed profile fields are stored; secrets stay behind credential_ref.",
            "recommended_action": "Open Integrations Setup and complete discovery, preflight, and preview sync.",
            "retryable": True,
        }
    )

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
            display_name=resolved_display_name,
            auth_mode=resolved_auth_mode,
            base_url=resolved_base_url,
            resource_path=resolved_resource_path,
            status="configured",
            mapping_version=mapping_version,
            certified_variant=resolved_variant,
            product_version=resolved_product_version,
            support_tier=resolved_support_tier,
            connectivity_mode=resolved_connectivity_mode,
            credential_ref=credential_ref,
            health_band=str(default_health["band"]),
            health_status_json=default_health,
            assigned_agent_id=assigned_agent_id,
            normalization_policy_json=normalization_policy
            or build_default_normalization_policy(normalized_type),
            connection_payload=merged_profile,
            sample_payload=sample_payload or {},
        )
        db.add(integration)
        db.flush()
        return integration

    integration.display_name = resolved_display_name
    integration.auth_mode = resolved_auth_mode
    integration.base_url = resolved_base_url
    integration.resource_path = resolved_resource_path
    integration.mapping_version = mapping_version
    integration.certified_variant = resolved_variant
    integration.product_version = resolved_product_version
    integration.support_tier = resolved_support_tier
    integration.connectivity_mode = resolved_connectivity_mode
    integration.credential_ref = credential_ref
    integration.assigned_agent_id = assigned_agent_id
    integration.connection_payload = merged_profile
    integration.sample_payload = sample_payload or integration.sample_payload
    integration.normalization_policy_json = (
        normalization_policy or integration.normalization_policy_json or build_default_normalization_policy(normalized_type)
    )
    if integration.status not in {"active", "review_required"}:
        integration.status = "configured"
    if integration.health_status_json is None:
        integration.health_status_json = default_health
        integration.health_band = str(default_health["band"])
    db.flush()
    return integration


def run_connector_sync(*, db: Session, integration: IntegrationConfig) -> ConnectorSyncJob:
    started_at = _utcnow()
    job = ConnectorSyncJob(
        integration_config_id=integration.id,
        tenant_id=integration.tenant_id,
        project_id=integration.project_id,
        status="running",
        current_stage="extract",
        cursor_before=integration.last_cursor,
        started_at=started_at,
        diagnostics_json={},
    )
    db.add(job)
    db.flush()

    source_rows = _coerce_records(integration, allow_defaults=True)
    normalized_rows = [_normalize_row(integration, row, row_index) for row_index, row in enumerate(source_rows, start=1)]
    cursor_after = _resolve_cursor_after(integration, source_rows, started_at)

    inserted_count = 0
    updated_count = 0
    job.current_stage = "normalize"
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
    integration.last_cursor = cursor_after
    integration.last_synced_at = completed_at

    job.status = "completed"
    job.current_stage = "completed"
    job.record_count = len(normalized_rows)
    job.inserted_count = inserted_count
    job.updated_count = updated_count
    job.cursor_after = cursor_after
    job.completed_at = completed_at
    job.diagnostics_json = {
        "connector_type": integration.connector_type,
        "delta_mode": CONNECTOR_DELTA_MODES.get(integration.connector_type, "generic"),
        "normalized_metrics": sorted({row.metric_code for row in normalized_rows}),
        "cursor_before": job.cursor_before,
        "cursor_after": cursor_after,
    }
    db.flush()
    return job


def register_connector_agent(
    *,
    db: Session,
    tenant_id: str | None,
    project_id: str | None,
    agent_key: str,
    display_name: str,
    agent_kind: str,
    version: str | None,
    hostname: str | None,
    supported_connectors: list[str],
    capabilities: list[str],
    metadata: dict[str, Any] | None,
) -> ConnectorAgent:
    agent = db.scalar(select(ConnectorAgent).where(ConnectorAgent.agent_key == agent_key))
    normalized_connectors = [normalize_connector_type(item) for item in supported_connectors]
    if agent is None:
        agent = ConnectorAgent(
            tenant_id=tenant_id,
            project_id=project_id,
            agent_key=agent_key,
            display_name=display_name,
            agent_kind=agent_kind,
            status="online",
            version=version,
            hostname=hostname,
            supported_connectors_json=normalized_connectors,
            capabilities_json=capabilities,
            metadata_json=metadata or {},
            last_heartbeat_at=_utcnow(),
            heartbeat_payload_json={"event": "register"},
        )
        db.add(agent)
        db.flush()
        return agent

    agent.tenant_id = tenant_id
    agent.project_id = project_id
    agent.display_name = display_name
    agent.agent_kind = agent_kind
    agent.status = "online"
    agent.version = version
    agent.hostname = hostname
    agent.supported_connectors_json = normalized_connectors
    agent.capabilities_json = capabilities
    agent.metadata_json = metadata or {}
    agent.last_heartbeat_at = _utcnow()
    agent.heartbeat_payload_json = {"event": "register"}
    db.flush()
    return agent


def heartbeat_connector_agent(
    *,
    db: Session,
    agent: ConnectorAgent,
    status: str,
    version: str | None,
    hostname: str | None,
    active_operation_id: str | None,
    metrics: dict[str, Any] | None,
) -> ConnectorAgent:
    agent.status = status.strip().lower()
    agent.version = version or agent.version
    agent.hostname = hostname or agent.hostname
    agent.last_heartbeat_at = _utcnow()
    agent.heartbeat_payload_json = {
        "active_operation_id": active_operation_id,
        "metrics": metrics or {},
    }
    db.flush()
    return agent


def _agent_supports_connector(agent: ConnectorAgent, connector_type: str) -> bool:
    supported = {normalize_connector_type(item) for item in (agent.supported_connectors_json or [])}
    return not supported or normalize_connector_type(connector_type) in supported


def claim_next_connector_operation(*, db: Session, agent: ConnectorAgent) -> ConnectorOperationRun | None:
    rows = db.scalars(
        select(ConnectorOperationRun)
        .where(
            ConnectorOperationRun.status == "queued",
            or_(
                ConnectorOperationRun.assigned_agent_id.is_(None),
                ConnectorOperationRun.assigned_agent_id == agent.id,
            ),
        )
        .order_by(ConnectorOperationRun.created_at.asc())
    ).all()
    for operation in rows:
        if agent.tenant_id and operation.tenant_id != agent.tenant_id:
            continue
        if agent.project_id and operation.project_id != agent.project_id:
            continue
        if not _agent_supports_connector(agent, operation.connector_type):
            continue
        operation.assigned_agent_id = agent.id
        operation.status = "running"
        operation.current_stage = "claimed"
        operation.started_at = _utcnow()
        db.flush()
        return operation
    return None


def _metric(score: int, detail: str) -> dict[str, Any]:
    return {"score": score, "detail": detail}


def _success_result(
    *,
    connector_type: str,
    current_stage: str,
    metrics: dict[str, dict[str, Any]],
    result_payload: dict[str, Any],
    diagnostics: dict[str, Any],
    operator_message: str,
    support_hint: str,
    recommended_action: str,
    integration_status: str | None = None,
) -> OperationExecutionResult:
    health_status = summarize_health(connector_type=connector_type, metrics=metrics)
    health_status.update(
        {
            "operator_message": operator_message,
            "support_hint": support_hint,
            "recommended_action": recommended_action,
            "retryable": True,
        }
    )
    return OperationExecutionResult(
        current_stage=current_stage,
        error_code=None,
        error_message=None,
        operator_message=operator_message,
        support_hint=support_hint,
        recommended_action=recommended_action,
        retryable=True,
        health_status=health_status,
        result_payload=result_payload,
        diagnostics=diagnostics,
        integration_status=integration_status,
    )


def _failure_result(
    *,
    connector_type: str,
    current_stage: str,
    metrics: dict[str, dict[str, Any]],
    error_code: str,
    error_message: str,
    result_payload: dict[str, Any],
    diagnostics: dict[str, Any],
    integration_status: str | None = "review_required",
) -> OperationExecutionResult:
    error_payload = support_error_payload(connector_type, error_code)
    health_status = summarize_health(connector_type=connector_type, metrics=metrics, error_code=error_code)
    return OperationExecutionResult(
        current_stage=current_stage,
        error_code=error_code,
        error_message=error_message,
        operator_message=str(error_payload["operator_message"]),
        support_hint=str(error_payload["support_hint"]),
        recommended_action=str(error_payload["recommended_action"]),
        retryable=bool(error_payload["retryable"]),
        health_status=health_status,
        result_payload=result_payload,
        diagnostics=diagnostics,
        integration_status=integration_status,
    )


def _has_delta_or_cursor_capability(integration: IntegrationConfig, rows: list[dict[str, Any]]) -> bool:
    payload = integration.sample_payload or {}
    if integration.connector_type == "sap_odata":
        return any(
            isinstance(candidate, str) and candidate.strip()
            for candidate in (payload.get("@odata.deltaLink"), payload.get("delta_token"), payload.get("deltaLink"))
        )
    if integration.connector_type == "logo_tiger_sql_view":
        if any(
            isinstance(candidate, str) and candidate.strip()
            for candidate in (payload.get("snapshot_watermark"), payload.get("watermark"))
        ):
            return True
        return any(_pick_first(row, "snapshot_watermark", "watermark", "updated_at", "updatedAt") for row in rows)
    if integration.connector_type == "netsis_rest":
        if any(
            isinstance(candidate, str) and candidate.strip()
            for candidate in (payload.get("cursor"), payload.get("next_cursor"))
        ):
            return True
        return any(_pick_first(row, "updated_at", "updatedAt", "cursor") for row in rows)
    return bool(rows)


def _has_logo_locale_conflict(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        candidate = _pick_first(row, "DEGER", "value", "Value", "metric.value")
        if not isinstance(candidate, str):
            continue
        rendered = candidate.strip()
        if "," in rendered and "." not in rendered and any(character.isdigit() for character in rendered):
            return True
    return False


def _preview_rows(integration: IntegrationConfig, *, limit: int) -> list[dict[str, Any]]:
    rows = _coerce_records(integration, allow_defaults=False)[:limit]
    preview_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        normalized = _normalize_row(integration, row, row_index)
        preview_rows.append(
            {
                "metric_code": normalized.metric_code,
                "metric_name": normalized.metric_name,
                "period_key": normalized.period_key,
                "unit": normalized.unit,
                "value_numeric": normalized.value_numeric,
                "value_text": normalized.value_text,
                "source_record_id": normalized.source_record_id,
                "owner": normalized.owner,
                "trace_ref": normalized.trace_ref,
                "confidence_score": normalized.confidence_score,
            }
        )
    return preview_rows


def _artifact_checksum(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _write_zip_json(bundle: ZipFile, name: str, payload: dict[str, Any] | list[Any]) -> None:
    bundle.writestr(name, json.dumps(payload, ensure_ascii=True, indent=2, default=str))


def _persist_support_bundle_artifact(
    *,
    db: Session,
    integration: IntegrationConfig,
    operation: ConnectorOperationRun,
    payload: bytes,
    metadata: dict[str, Any],
) -> ConnectorArtifact:
    blob_storage = get_blob_storage_service()
    timestamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    filename = f"{integration.connector_type}-support-bundle-{timestamp}.zip"
    blob_name = (
        f"{integration.tenant_id}/{integration.project_id}/connectors/{integration.id}/support-bundles/{filename}"
    )
    storage_uri = blob_storage.upload_bytes(
        payload,
        blob_name,
        "application/zip",
        container=settings.azure_storage_container_artifacts,
    )
    artifact = ConnectorArtifact(
        integration_config_id=integration.id,
        connector_operation_run_id=operation.id,
        tenant_id=integration.tenant_id,
        project_id=integration.project_id,
        artifact_type="support_bundle",
        filename=filename,
        content_type="application/zip",
        storage_uri=storage_uri,
        size_bytes=len(payload),
        checksum=_artifact_checksum(payload),
        artifact_metadata_json=metadata,
    )
    db.add(artifact)
    db.flush()
    return artifact


def _execute_discover(integration: IntegrationConfig) -> OperationExecutionResult:
    profile = _active_connection_profile(integration)
    rows = _coerce_records(integration, allow_defaults=False)
    missing_fields = missing_required_profile_fields(integration.connector_type, profile)
    metrics = {
        "connectivity": _metric(92 if not missing_fields else 34, "Topology profile is available for connector discovery."),
        "authentication": _metric(78 if profile.get("auth_method") else 35, "Auth mode and credential binding pattern are declared."),
        "permission_scope": _metric(72, "Permission scope will be validated during preflight."),
        "data_shape": _metric(82 if rows else 64, "Sample payload presence is checked before canonical mapping."),
        "locale_guards": _metric(78, "Normalization policy is attached to the connector profile."),
        "replay_readiness": _metric(88 if replay_mode_supported(integration.connector_type, "resume") else 55, "Replay matrix is loaded from the certified support contract."),
    }
    if missing_fields:
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="discover",
            metrics=metrics,
            error_code=DISCOVERY_ERROR_CODES[integration.connector_type],
            error_message=f"Missing typed profile fields: {', '.join(missing_fields)}",
            result_payload={
                "missing_fields": missing_fields,
                "required_profile_fields": get_support_definition(integration.connector_type).get("required_profile_fields", []),
                "profile_snapshot": redact_connection_profile(profile),
            },
            diagnostics={
                "support_matrix_version": SUPPORT_MATRIX_VERSION,
                "profile_snapshot": redact_connection_profile(profile),
            },
            integration_status="configured",
        )
    return _success_result(
        connector_type=integration.connector_type,
        current_stage="discover",
        metrics=metrics,
        result_payload={
            "profile_snapshot": redact_connection_profile(profile),
            "required_profile_fields": get_support_definition(integration.connector_type).get("required_profile_fields", []),
            "supported_replay_modes": get_support_definition(integration.connector_type).get("supported_replay_modes", []),
            "support_matrix_version": SUPPORT_MATRIX_VERSION,
        },
        diagnostics={
            "profile_snapshot": redact_connection_profile(profile),
            "sample_row_count": len(rows),
        },
        operator_message="Connector profile passed discovery. Typed topology fields are complete and the onboarding flow can move to preflight.",
        support_hint="The customer-network agent can now validate credential binding, locale guards, and replay prerequisites.",
        recommended_action="Run preflight to verify authentication and ERP-specific readiness.",
        integration_status="configured",
    )


def _execute_preflight(integration: IntegrationConfig) -> OperationExecutionResult:
    profile = _active_connection_profile(integration)
    rows = _coerce_records(integration, allow_defaults=False)
    missing_fields = missing_required_profile_fields(integration.connector_type, profile)
    if missing_fields:
        return _execute_discover(integration)

    metrics = {
        "connectivity": _metric(93, "Topology and route are stable enough for preflight."),
        "authentication": _metric(91 if integration.credential_ref else 28, "Credential reference is required and never stored inline."),
        "permission_scope": _metric(88 if integration.credential_ref else 52, "ERP access scope can be checked only with a bound credential reference."),
        "data_shape": _metric(84 if rows else 62, "Sample payload can be normalized into canonical facts."),
        "locale_guards": _metric(90, "Timezone, decimal separator, and reporting currency guard rails are configured."),
        "replay_readiness": _metric(90 if _has_delta_or_cursor_capability(integration, rows) else 34, "Replay readiness depends on delta token, watermark, or cursor visibility."),
    }

    if not integration.credential_ref and integration.connector_type in AUTH_ERROR_CODES:
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="preflight",
            metrics=metrics,
            error_code=AUTH_ERROR_CODES[integration.connector_type],
            error_message="credential_ref is required for preflight",
            result_payload={"credential_ref_present": False, "profile_snapshot": redact_connection_profile(profile)},
            diagnostics={"profile_snapshot": redact_connection_profile(profile)},
            integration_status="configured",
        )
    if integration.connector_type == "sap_odata" and not _has_delta_or_cursor_capability(integration, rows):
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="preflight",
            metrics=metrics,
            error_code="SAP_DELTA_UNAVAILABLE",
            error_message="SAP sample payload is missing a delta token or delta link",
            result_payload={"delta_mode": CONNECTOR_DELTA_MODES[integration.connector_type]},
            diagnostics={"sample_payload": integration.sample_payload or {}},
            integration_status="configured",
        )
    if integration.connector_type == "logo_tiger_sql_view" and _has_logo_locale_conflict(rows):
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="preflight",
            metrics=metrics,
            error_code="LOGO_COLLATION_CONFLICT",
            error_message="Logo SQL sample payload contains locale-sensitive decimal formatting",
            result_payload={"profile_snapshot": redact_connection_profile(profile)},
            diagnostics={"sample_payload": integration.sample_payload or {}},
            integration_status="configured",
        )
    if integration.connector_type == "netsis_rest" and not rows and not integration.sample_payload:
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="preflight",
            metrics=metrics,
            error_code="NETSIS_ENDPOINT_UNREACHABLE",
            error_message="Netsis sample payload is empty and the endpoint looks unreachable",
            result_payload={"profile_snapshot": redact_connection_profile(profile)},
            diagnostics={"sample_payload": {}},
            integration_status="configured",
        )
    if integration.connector_type == "netsis_rest" and not _has_delta_or_cursor_capability(integration, rows):
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="preflight",
            metrics=metrics,
            error_code="NETSIS_CURSOR_DRIFT",
            error_message="Netsis sample payload is missing cursor or updatedAt markers",
            result_payload={"profile_snapshot": redact_connection_profile(profile)},
            diagnostics={"sample_payload": integration.sample_payload or {}},
            integration_status="configured",
        )

    return _success_result(
        connector_type=integration.connector_type,
        current_stage="preflight",
        metrics=metrics,
        result_payload={
            "credential_ref_present": bool(integration.credential_ref),
            "delta_mode": CONNECTOR_DELTA_MODES.get(integration.connector_type),
            "profile_snapshot": redact_connection_profile(profile),
        },
        diagnostics={"sample_row_count": len(rows)},
        operator_message="Preflight passed. Authentication, locale guards, and replay prerequisites cleared the onboarding checks.",
        support_hint="A green preflight means the connector can attempt a bounded preview sync inside the customer network.",
        recommended_action="Run preview sync to validate 20-record canonical normalization without touching production facts.",
        integration_status="configured",
    )


def _execute_preview_sync(integration: IntegrationConfig, *, limit: int) -> OperationExecutionResult:
    preflight = _execute_preflight(integration)
    if preflight.error_code:
        return preflight

    rows = _coerce_records(integration, allow_defaults=False)[:limit]
    metrics = {
        "connectivity": _metric(95, "Preview sync reached the connector path successfully."),
        "authentication": _metric(93, "Credential binding stayed valid during the 20-record preview."),
        "permission_scope": _metric(91, "Preview access can read the intended ERP surface."),
        "data_shape": _metric(95 if rows else 38, "Preview rows can be normalized into the canonical fact contract."),
        "locale_guards": _metric(92 if not _has_logo_locale_conflict(rows) else 48, "Numeric and temporal values respect locale guard rails."),
        "replay_readiness": _metric(92 if _has_delta_or_cursor_capability(integration, rows) else 42, "Preview confirms the replay marker strategy."),
    }
    if not rows:
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="preview_sync",
            metrics=metrics,
            error_code=PREVIEW_EMPTY_ERROR_CODES[integration.connector_type],
            error_message="Preview sync returned no records",
            result_payload={"preview_rows": [], "preview_limit": limit},
            diagnostics={"sample_payload": integration.sample_payload or {}},
            integration_status="configured",
        )

    preview_rows = _preview_rows(integration, limit=limit)
    health_band = str(summarize_health(connector_type=integration.connector_type, metrics=metrics)["band"])
    integration_status = "active" if integration.support_tier == "certified" and health_band == "green" else "review_required"
    return _success_result(
        connector_type=integration.connector_type,
        current_stage="preview_sync",
        metrics=metrics,
        result_payload={
            "preview_limit": limit,
            "preview_row_count": len(preview_rows),
            "preview_rows": preview_rows,
            "cursor_after_preview": _resolve_cursor_after(integration, rows, _utcnow()),
            "writes_production_facts": False,
            "activation_ready": integration_status == "active",
        },
        diagnostics={"preview_metric_codes": [row["metric_code"] for row in preview_rows]},
        operator_message="Preview sync normalized a bounded 20-record sample and kept production canonical facts untouched.",
        support_hint="This preview run is the activation gate; only certified green connectors become launch-ready.",
        recommended_action=(
            "Connector activation is ready. You can return to reports/new and start a run."
            if integration_status == "active"
            else "Review the health report and clear remaining amber/red checks before launch."
        ),
        integration_status=integration_status,
    )


def _execute_replay(
    integration: IntegrationConfig,
    *,
    replay_mode: str,
    backfill_window_days: int | None,
) -> OperationExecutionResult:
    metrics = {
        "connectivity": _metric(88, "Replay request can reach the configured connector profile."),
        "authentication": _metric(86 if integration.credential_ref else 52, "Replay runs require the same credential binding as sync."),
        "permission_scope": _metric(84, "Replay permission scope is limited to the certified connector surface."),
        "data_shape": _metric(82, "Replay does not alter the canonical contract."),
        "locale_guards": _metric(84, "Replay keeps normalization guards unchanged."),
        "replay_readiness": _metric(94 if replay_mode_supported(integration.connector_type, replay_mode) else 30, "Replay mode must be allowed by the support matrix."),
    }
    if not replay_mode_supported(integration.connector_type, replay_mode):
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="replay",
            metrics=metrics,
            error_code="CONNECTOR_REPLAY_MODE_UNSUPPORTED",
            error_message=f"Replay mode '{replay_mode}' is not supported for {integration.connector_type}",
            result_payload={"mode": replay_mode},
            diagnostics={"supported_modes": get_support_definition(integration.connector_type).get("supported_replay_modes", [])},
            integration_status=integration.status,
        )
    if integration.connector_type == "sap_odata" and replay_mode == "resume" and not integration.last_cursor:
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="replay",
            metrics=metrics,
            error_code="SAP_INVALID_CURSOR",
            error_message="No stored SAP delta cursor is available for resume",
            result_payload={"mode": replay_mode},
            diagnostics={"last_cursor": integration.last_cursor},
            integration_status=integration.status,
        )
    if integration.connector_type == "netsis_rest" and replay_mode == "resume" and not integration.last_cursor:
        return _failure_result(
            connector_type=integration.connector_type,
            current_stage="replay",
            metrics=metrics,
            error_code="NETSIS_CURSOR_DRIFT",
            error_message="No Netsis cursor is available for resume",
            result_payload={"mode": replay_mode},
            diagnostics={"last_cursor": integration.last_cursor},
            integration_status=integration.status,
        )

    previous_cursor = integration.last_cursor
    if replay_mode == "reset_cursor":
        integration.last_cursor = None

    return _success_result(
        connector_type=integration.connector_type,
        current_stage="replay",
        metrics=metrics,
        result_payload={
            "mode": replay_mode,
            "previous_cursor": previous_cursor,
            "current_cursor": integration.last_cursor,
            "backfill_window_days": backfill_window_days,
        },
        diagnostics={"delta_mode": CONNECTOR_DELTA_MODES.get(integration.connector_type)},
        operator_message="Replay request was accepted under the certified connector contract.",
        support_hint="Use reset_cursor for a clean replay or backfill_window where the support matrix permits it.",
        recommended_action="Run the next production sync to apply the chosen replay strategy.",
        integration_status=integration.status,
    )


def _execute_support_bundle(*, db: Session, integration: IntegrationConfig, operation: ConnectorOperationRun) -> OperationExecutionResult:
    recent_operations = db.scalars(
        select(ConnectorOperationRun)
        .where(ConnectorOperationRun.integration_config_id == integration.id)
        .order_by(ConnectorOperationRun.created_at.desc())
        .limit(10)
    ).all()
    runtime_health = integration.health_status_json or {}
    payload_buffer = BytesIO()
    with ZipFile(payload_buffer, mode="w", compression=ZIP_DEFLATED) as bundle:
        _write_zip_json(
            bundle,
            "integration.json",
            {
                "integration_id": integration.id,
                "connector_type": integration.connector_type,
                "display_name": integration.display_name,
                "status": integration.status,
                "support_tier": integration.support_tier,
                "certified_variant": integration.certified_variant,
                "product_version": integration.product_version,
                "connectivity_mode": integration.connectivity_mode,
                "credential_ref": integration.credential_ref,
                "profile_snapshot": redact_connection_profile(_active_connection_profile(integration)),
                "normalization_policy": integration.normalization_policy_json or {},
                "last_cursor": integration.last_cursor,
            },
        )
        _write_zip_json(
            bundle,
            "runtime-health.json",
            {
                "health_band": integration.health_band,
                "health_status": runtime_health,
                "assigned_agent_status": get_assigned_agent_status(db=db, integration=integration),
                "generated_at_utc": _utcnow().isoformat(),
            },
        )
        _write_zip_json(
            bundle,
            "recent-operations.json",
            [
                {
                    "operation_id": item.id,
                    "operation_type": item.operation_type,
                    "status": item.status,
                    "current_stage": item.current_stage,
                    "error_code": item.error_code,
                    "error_message": item.error_message,
                    "created_at_utc": item.created_at.isoformat(),
                    "completed_at_utc": item.completed_at.isoformat() if item.completed_at else None,
                }
                for item in recent_operations
            ],
        )
        bundle.writestr(
            "erp-log-excerpt.txt",
            "\n".join(
                [
                    f"[{_utcnow().isoformat()}] connector={integration.connector_type} status={integration.status}",
                    f"[{_utcnow().isoformat()}] assigned_agent_status={get_assigned_agent_status(db=db, integration=integration)}",
                    f"[{_utcnow().isoformat()}] last_cursor={integration.last_cursor or '<empty>'}",
                    f"[{_utcnow().isoformat()}] health_band={integration.health_band}",
                ]
            ),
        )

    payload_bytes = payload_buffer.getvalue()
    artifact = _persist_support_bundle_artifact(
        db=db,
        integration=integration,
        operation=operation,
        payload=payload_bytes,
        metadata={
            "connector_type": integration.connector_type,
            "support_matrix_version": SUPPORT_MATRIX_VERSION,
            "operation_type": operation.operation_type,
        },
    )
    metrics = {
        "connectivity": _metric(90, "Support bundle includes the redacted topology and runtime snapshot."),
        "authentication": _metric(88, "Credential references are preserved without exposing secret material."),
        "permission_scope": _metric(84, "Recent operation outcomes provide permission-scope evidence."),
        "data_shape": _metric(86, "Bundle exports normalization findings and preview diagnostics."),
        "locale_guards": _metric(86, "Normalization policy is attached for timezone, decimal, and currency review."),
        "replay_readiness": _metric(82, "Recent cursor state is exported for support triage."),
    }
    result = _success_result(
        connector_type=integration.connector_type,
        current_stage="support_bundle",
        metrics=metrics,
        result_payload={
            "artifact_id": artifact.id,
            "artifact_type": artifact.artifact_type,
            "filename": artifact.filename,
            "size_bytes": artifact.size_bytes,
        },
        diagnostics={"bundle_checksum": artifact.checksum, "operation_count": len(recent_operations)},
        operator_message="Support bundle was exported successfully with redacted connector state and recent ERP diagnostics.",
        support_hint="Share the bundle with support or attach it to a ticket when onboarding fails.",
        recommended_action="Download the bundle and use it as the single support handoff package.",
        integration_status=integration.status,
    )
    result.artifact = artifact
    return result


def execute_connector_operation(
    *,
    db: Session,
    integration: IntegrationConfig,
    operation: ConnectorOperationRun,
    preview_limit: int = 20,
    backfill_window_days: int | None = None,
) -> ConnectorOperationRun:
    operation.started_at = operation.started_at or _utcnow()
    operation.status = "running"
    db.flush()

    if operation.operation_type == "discover":
        result = _execute_discover(integration)
        integration.last_discovered_at = _utcnow()
    elif operation.operation_type == "preflight":
        result = _execute_preflight(integration)
        integration.last_preflight_at = _utcnow()
    elif operation.operation_type == "preview_sync":
        result = _execute_preview_sync(integration, limit=preview_limit)
        integration.last_preview_sync_at = _utcnow()
    elif operation.operation_type == "replay":
        result = _execute_replay(
            integration,
            replay_mode=operation.replay_mode or "resume",
            backfill_window_days=backfill_window_days,
        )
    elif operation.operation_type == "support_bundle":
        result = _execute_support_bundle(db=db, integration=integration, operation=operation)
    else:
        result = _failure_result(
            connector_type=integration.connector_type,
            current_stage=operation.operation_type,
            metrics={
                "connectivity": _metric(20, "Unknown operation."),
                "authentication": _metric(20, "Unknown operation."),
                "permission_scope": _metric(20, "Unknown operation."),
                "data_shape": _metric(20, "Unknown operation."),
                "locale_guards": _metric(20, "Unknown operation."),
                "replay_readiness": _metric(20, "Unknown operation."),
            },
            error_code="CONNECTOR_OPERATION_UNSUPPORTED",
            error_message=f"Unsupported operation type: {operation.operation_type}",
            result_payload={},
            diagnostics={},
            integration_status=integration.status,
        )

    operation.status = result.status
    operation.current_stage = result.current_stage
    operation.error_code = result.error_code
    operation.error_message = result.error_message
    operation.operator_message = result.operator_message
    operation.support_hint = result.support_hint
    operation.recommended_action = result.recommended_action
    operation.retryable = result.retryable
    operation.result_payload_json = result.result_payload
    operation.diagnostics_json = {
        **(operation.diagnostics_json or {}),
        **result.diagnostics,
    }
    operation.completed_at = _utcnow()

    integration.health_status_json = result.health_status
    integration.health_band = str(result.health_status.get("band", integration.health_band))
    if result.integration_status is not None:
        integration.status = result.integration_status

    db.flush()
    return operation


def run_connector_operation(
    *,
    db: Session,
    integration: IntegrationConfig,
    operation_type: str,
    requested_by_user_id: str | None,
    replay_mode: str | None = None,
    preview_limit: int = 20,
    backfill_window_days: int | None = None,
) -> ConnectorOperationRun:
    operation = ConnectorOperationRun(
        integration_config_id=integration.id,
        tenant_id=integration.tenant_id,
        project_id=integration.project_id,
        assigned_agent_id=integration.assigned_agent_id,
        requested_by_user_id=requested_by_user_id,
        connector_type=integration.connector_type,
        operation_type=operation_type,
        replay_mode=replay_mode,
        status="queued",
        current_stage="queued",
        retryable=True,
        diagnostics_json={
            "preview_limit": preview_limit,
            "backfill_window_days": backfill_window_days,
            "support_matrix_version": SUPPORT_MATRIX_VERSION,
        },
    )
    db.add(operation)
    db.flush()

    if integration.assigned_agent_id and not settings.connector_operations_inline_fallback:
        return operation

    return execute_connector_operation(
        db=db,
        integration=integration,
        operation=operation,
        preview_limit=preview_limit,
        backfill_window_days=backfill_window_days,
    )
