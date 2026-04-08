# Bu servis, connector support contract bilgisini tek yerde tutar.

from __future__ import annotations

from copy import deepcopy
from typing import Any


SUPPORT_MATRIX_VERSION = "2026.04.08"
REPLAY_MODES = {"resume", "reset_cursor", "backfill_window"}
HEALTH_METRIC_LABELS = {
    "connectivity": "Connectivity",
    "authentication": "Authentication",
    "permission_scope": "Permission Scope",
    "data_shape": "Data Shape",
    "locale_guards": "Locale Guards",
    "replay_readiness": "Replay Readiness",
}


CONNECTOR_SUPPORT_MATRIX: dict[str, dict[str, Any]] = {
    "sap_odata": {
        "display_name": "SAP Sustainability Feed",
        "default_auth_mode": "odata",
        "support_tier": "certified",
        "connectivity_mode": "customer_network_agent",
        "delta_mode": "delta_token",
        "certified_variants": [
            {
                "code": "sap_s4hana_odp_odata_v4",
                "label": "SAP S/4HANA ODP OData V4",
                "supported_product_versions": ["2023", "2024", "2025"],
            }
        ],
        "required_profile_fields": ["service_url", "resource_path", "company_code", "auth_method"],
        "supported_replay_modes": ["resume", "reset_cursor", "backfill_window"],
        "normalization_policy": {
            "timezone": "UTC",
            "decimal_separator": ".",
            "currency_source": "project_currency",
        },
        "default_profile": {
            "service_url": "https://sap.example.local",
            "resource_path": "/sap/opu/odata/sustainability",
            "company_code": "1000",
            "auth_method": "technical_user",
        },
        "demo_sample_payload": {
            "@odata.deltaLink": "sap-delta-token-2025",
            "value": [
                {
                    "MetricCode": "e_scope2_tco2e",
                    "MetricName": "Scope 2 Emissions",
                    "FiscalYear": "2025",
                    "Unit": "tco2e",
                    "Value": "12450",
                    "RecordId": "sap-scope2-2025",
                    "OwnerEmail": "energy@example.com",
                    "TraceRef": "sap://scope2/2025",
                    "updatedAt": "2026-04-01T08:30:00Z",
                },
                {
                    "MetricCode": "renewable_electricity_share",
                    "MetricName": "Renewable Electricity Share",
                    "FiscalYear": "2025",
                    "Unit": "percent",
                    "Value": "42",
                    "RecordId": "sap-renewable-share-2025",
                    "OwnerEmail": "energy@example.com",
                    "TraceRef": "sap://renewable-share/2025",
                    "updatedAt": "2026-04-01T08:31:00Z",
                },
            ],
        },
    },
    "logo_tiger_sql_view": {
        "display_name": "Logo Tiger SQL View",
        "default_auth_mode": "sql_view",
        "support_tier": "certified",
        "connectivity_mode": "customer_network_agent",
        "delta_mode": "snapshot_watermark",
        "certified_variants": [
            {
                "code": "tiger3_enterprise_sqlserver",
                "label": "Tiger 3 Enterprise SQL Server",
                "supported_product_versions": ["3.58", "3.59", "3.60"],
            },
            {
                "code": "tiger3_sqlserver",
                "label": "Tiger 3 SQL Server",
                "supported_product_versions": ["3.58", "3.59", "3.60"],
            },
        ],
        "required_profile_fields": ["host", "database_name", "sql_view_name", "auth_method"],
        "supported_replay_modes": ["resume", "reset_cursor"],
        "normalization_policy": {
            "timezone": "Europe/Istanbul",
            "decimal_separator": ".",
            "currency_source": "project_currency",
        },
        "default_profile": {
            "host": "logo-sql.example.local",
            "database_name": "TIGERDB",
            "sql_view_name": "vw_sustainability_metrics",
            "auth_method": "read_only_sql_login",
        },
        "demo_sample_payload": {
            "snapshot_watermark": "2026-04-01T09:00:00Z",
            "rows": [
                {
                    "METRIC_KODU": "workforce_headcount",
                    "METRIC_ADI": "Workforce Headcount",
                    "DONEM": "2025",
                    "BIRIM": "employees",
                    "DEGER": 1850,
                    "ROW_ID": "logo-headcount-2025",
                    "updated_at": "2026-04-01T09:00:00Z",
                },
                {
                    "METRIC_KODU": "ltifr",
                    "METRIC_ADI": "Lost Time Injury Frequency Rate",
                    "DONEM": "2025",
                    "BIRIM": "rate",
                    "DEGER": "0.48",
                    "ROW_ID": "logo-ltifr-2025",
                    "updated_at": "2026-04-01T09:00:00Z",
                },
            ],
        },
    },
    "netsis_rest": {
        "display_name": "Netsis Sustainability REST",
        "default_auth_mode": "rest",
        "support_tier": "certified",
        "connectivity_mode": "customer_network_agent",
        "delta_mode": "cursor_or_updated_at",
        "certified_variants": [
            {
                "code": "netsis3_rest",
                "label": "Netsis 3 REST / NetOpenX REST",
                "supported_product_versions": ["3.2", "3.3", "3.4"],
            }
        ],
        "required_profile_fields": ["service_url", "resource_path", "firm_code", "auth_method"],
        "supported_replay_modes": ["resume", "reset_cursor", "backfill_window"],
        "normalization_policy": {
            "timezone": "Europe/Istanbul",
            "decimal_separator": ".",
            "currency_source": "project_currency",
        },
        "default_profile": {
            "service_url": "https://netsis.example.local",
            "resource_path": "/api/v1/sustainability-metrics",
            "firm_code": "01",
            "auth_method": "service_account",
        },
        "demo_sample_payload": {
            "next_cursor": "netsis-cursor-2",
            "items": [
                {
                    "metric": {
                        "code": "supplier_coverage",
                        "name": "Supplier Coverage",
                    },
                    "periodKey": "2025",
                    "unit": "percentage",
                    "value": "96",
                    "id": "netsis-supplier-2025",
                    "updatedAt": "2026-03-31T10:00:00Z",
                    "traceRef": "netsis://supplier-coverage/2025",
                },
                {
                    "metric": {
                        "code": "material_topic_count",
                        "name": "Material Topic Count",
                    },
                    "periodKey": "2025",
                    "unit": "count",
                    "value": "9",
                    "id": "netsis-material-topic-count-2025",
                    "updatedAt": "2026-03-31T10:02:00Z",
                    "traceRef": "netsis://materiality/topics/2025",
                },
            ],
        },
    },
}


CONNECTOR_ERROR_LIBRARY: dict[str, dict[str, dict[str, Any]]] = {
    "sap_odata": {
        "SAP_DISCOVERY_INCOMPLETE": {
            "operator_message": "SAP OData service address or company code is missing.",
            "support_hint": "Confirm the service root, resource path, and company code against the SAP outbound agent config.",
            "recommended_action": "Complete the SAP profile and rerun discovery.",
            "retryable": True,
        },
        "SAP_AUTH_PREFLIGHT_FAILED": {
            "operator_message": "SAP credential reference is missing or unusable for preflight.",
            "support_hint": "Bind a technical user credential in the customer-network agent secret store.",
            "recommended_action": "Update credential_ref and rerun preflight.",
            "retryable": True,
        },
        "SAP_DELTA_UNAVAILABLE": {
            "operator_message": "SAP payload does not expose a usable delta token or delta link.",
            "support_hint": "Check OData delta support or switch to a delta-capable feed.",
            "recommended_action": "Review the SAP extract endpoint and retry preflight.",
            "retryable": False,
        },
        "SAP_INVALID_CURSOR": {
            "operator_message": "SAP replay cursor is invalid for the selected replay mode.",
            "support_hint": "Reset the cursor or request a bounded backfill window.",
            "recommended_action": "Choose reset_cursor or provide a supported backfill window.",
            "retryable": True,
        },
    },
    "logo_tiger_sql_view": {
        "LOGO_DISCOVERY_INCOMPLETE": {
            "operator_message": "Logo SQL topology is incomplete.",
            "support_hint": "Host, database, read-only view, and auth method are required for Tiger SQL onboarding.",
            "recommended_action": "Complete the SQL view profile and rerun discovery.",
            "retryable": True,
        },
        "LOGO_SQL_VIEW_MISSING": {
            "operator_message": "Logo preview payload does not expose any rows from the configured SQL view.",
            "support_hint": "Confirm the view name, permissions, and selected database.",
            "recommended_action": "Validate the read-only SQL view and rerun preview sync.",
            "retryable": True,
        },
        "LOGO_COLLATION_CONFLICT": {
            "operator_message": "Logo payload could not satisfy decimal or locale guard rules.",
            "support_hint": "Check SQL collation, decimal formatting, and date serialization in the view output.",
            "recommended_action": "Normalize view output and rerun preflight.",
            "retryable": True,
        },
    },
    "netsis_rest": {
        "NETSIS_DISCOVERY_INCOMPLETE": {
            "operator_message": "Netsis REST profile is missing service URL, resource path, or firm code.",
            "support_hint": "Review the REST endpoint, firm code, and auth method in the onboarding profile.",
            "recommended_action": "Complete the Netsis profile and rerun discovery.",
            "retryable": True,
        },
        "NETSIS_AUTH_PREFLIGHT_FAILED": {
            "operator_message": "Netsis credential reference is missing or expired.",
            "support_hint": "Refresh the service account binding in the connector agent.",
            "recommended_action": "Update credential_ref and rerun preflight.",
            "retryable": True,
        },
        "NETSIS_CURSOR_DRIFT": {
            "operator_message": "Netsis payload does not expose a stable cursor or updated_at marker.",
            "support_hint": "Expose next_cursor or a deterministic updatedAt field in the REST payload.",
            "recommended_action": "Adjust the Netsis feed and rerun preview sync.",
            "retryable": False,
        },
        "NETSIS_ENDPOINT_UNREACHABLE": {
            "operator_message": "Netsis preview payload is empty and the endpoint looks unreachable from the current profile.",
            "support_hint": "Check service URL, TLS, and customer-network agent reachability to the Netsis host.",
            "recommended_action": "Fix endpoint connectivity and rerun discovery.",
            "retryable": True,
        },
    },
}

GENERIC_ERROR = {
    "operator_message": "Connector operation could not be completed with the current profile.",
    "support_hint": "Review topology, credential reference, and sample payload before retrying.",
    "recommended_action": "Fix the reported input and rerun the failed step.",
    "retryable": True,
}


def get_support_definition(connector_type: str) -> dict[str, Any]:
    if connector_type not in CONNECTOR_SUPPORT_MATRIX:
        raise ValueError(f"Unsupported connector type: {connector_type}")
    return deepcopy(CONNECTOR_SUPPORT_MATRIX[connector_type])


def get_default_variant_code(connector_type: str) -> str:
    definition = get_support_definition(connector_type)
    variants = definition.get("certified_variants", [])
    if not variants:
        raise ValueError(f"No certified variants configured for {connector_type}")
    return str(variants[0]["code"])


def get_default_product_version(connector_type: str) -> str:
    definition = get_support_definition(connector_type)
    variants = definition.get("certified_variants", [])
    if not variants:
        raise ValueError(f"No product versions configured for {connector_type}")
    supported_versions = variants[0].get("supported_product_versions", [])
    if not supported_versions:
        raise ValueError(f"No supported product versions configured for {connector_type}")
    return str(supported_versions[-1])


def get_required_profile_fields(connector_type: str) -> list[str]:
    definition = get_support_definition(connector_type)
    return [str(item) for item in definition.get("required_profile_fields", [])]


def build_default_connection_profile(connector_type: str) -> dict[str, Any]:
    definition = get_support_definition(connector_type)
    return deepcopy(definition.get("default_profile", {}))


def build_default_demo_sample_payload(connector_type: str) -> dict[str, Any]:
    definition = get_support_definition(connector_type)
    return deepcopy(definition.get("demo_sample_payload", {}))


def build_default_normalization_policy(
    connector_type: str,
    *,
    reporting_currency: str = "TRY",
) -> dict[str, Any]:
    definition = get_support_definition(connector_type)
    policy = deepcopy(definition.get("normalization_policy", {}))
    policy["reporting_currency"] = reporting_currency
    policy["support_matrix_version"] = SUPPORT_MATRIX_VERSION
    return policy


def resolve_support_tier(
    connector_type: str,
    *,
    certified_variant: str | None,
    product_version: str | None,
) -> str:
    definition = get_support_definition(connector_type)
    variants = definition.get("certified_variants", [])
    variant = next(
        (item for item in variants if str(item.get("code")) == str(certified_variant or "").strip()),
        None,
    )
    if variant is None:
        return "unsupported"
    supported_versions = {str(item) for item in variant.get("supported_product_versions", [])}
    if product_version and str(product_version).strip() not in supported_versions:
        return "beta"
    return str(definition.get("support_tier", "beta"))


def replay_mode_supported(connector_type: str, mode: str) -> bool:
    definition = get_support_definition(connector_type)
    return mode in {str(item) for item in definition.get("supported_replay_modes", [])}


def missing_required_profile_fields(
    connector_type: str,
    connection_profile: dict[str, Any] | None,
) -> list[str]:
    profile = connection_profile or {}
    missing: list[str] = []
    for field_name in get_required_profile_fields(connector_type):
        value = profile.get(field_name)
        if value is None or not str(value).strip():
            missing.append(field_name)
    return missing


def contains_secret_literal(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    sensitive_tokens = ("password", "secret", "token", "api_key", "client_secret", "private_key")
    for key, value in payload.items():
        normalized_key = str(key).strip().lower()
        if any(token in normalized_key for token in sensitive_tokens):
            return True
        if isinstance(value, dict) and contains_secret_literal(value):
            return True
        if isinstance(value, list):
            if any(isinstance(item, dict) and contains_secret_literal(item) for item in value):
                return True
    return False


def support_error_payload(connector_type: str, code: str) -> dict[str, Any]:
    connector_errors = CONNECTOR_ERROR_LIBRARY.get(connector_type, {})
    payload = connector_errors.get(code, GENERIC_ERROR)
    result = deepcopy(payload)
    result["error_code"] = code
    return result


def health_status_from_score(score: int) -> str:
    if score >= 85:
        return "good"
    if score >= 60:
        return "attention"
    return "critical"


def health_band_from_scores(scores: list[int]) -> str:
    if not scores:
        return "red"
    overall = round(sum(scores) / len(scores))
    if min(scores) >= 85 and overall >= 90:
        return "green"
    if min(scores) >= 60 and overall >= 70:
        return "amber"
    return "red"


def summarize_health(
    *,
    connector_type: str,
    metrics: dict[str, dict[str, Any]],
    error_code: str | None = None,
) -> dict[str, Any]:
    scores = [int(item.get("score", 0)) for item in metrics.values()]
    overall_score = round(sum(scores) / len(scores)) if scores else 0
    band = health_band_from_scores(scores)
    error_payload = support_error_payload(connector_type, error_code or "CONNECTOR_REVIEW_REQUIRED")
    return {
        "score": overall_score,
        "band": band,
        "metrics": [
            {
                "key": key,
                "label": HEALTH_METRIC_LABELS.get(key, key.replace("_", " ").title()),
                "score": int(value.get("score", 0)),
                "status": health_status_from_score(int(value.get("score", 0))),
                "detail": str(value.get("detail", "")).strip(),
            }
            for key, value in metrics.items()
        ],
        "operator_message": error_payload["operator_message"],
        "support_hint": error_payload["support_hint"],
        "recommended_action": error_payload["recommended_action"],
        "retryable": bool(error_payload["retryable"]),
        "support_matrix_version": SUPPORT_MATRIX_VERSION,
    }

