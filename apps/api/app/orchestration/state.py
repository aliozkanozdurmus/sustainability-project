# Bu orkestrasyon modulu, state adiminin durum akisini yonetir.

from __future__ import annotations

from typing import Any, Literal, Mapping, TypedDict

from app.orchestration.contracts import (
    CalculationResult,
    DraftSection,
    EvidenceBlock,
    ReadinessScorecard,
    ScopeDecision,
    TaskEnvelope,
    VerificationResultContract,
)


NodeName = Literal[
    "INIT_REQUEST",
    "RESOLVE_APPLICABILITY",
    "VALIDATE_READINESS",
    "PLAN_TASKS",
    "RETRIEVE_EVIDENCE",
    "VALIDATE_KPI_QUALITY",
    "COMPUTE_METRICS",
    "DRAFT_SECTION",
    "VERIFY_CLAIMS",
    "REVIEW_LOOP",
    "RUN_COVERAGE_AUDIT",
    "BUILD_DASHBOARD_SNAPSHOTS",
    "RUN_APPROVAL_ROUTING",
    "HUMAN_APPROVAL",
    "PUBLISH_REPORT_PACKAGE",
    "CLOSE_RUN",
]

HumanApprovalStatus = Literal["pending", "approved", "rejected"]


class WorkflowState(TypedDict):
    run_id: str
    tenant_id: str
    project_id: str
    framework_target: list[str]
    active_reg_pack_version: str | None
    scope_decision: dict[str, Any]
    active_node: NodeName
    completed_nodes: list[NodeName]
    failed_nodes: list[NodeName]
    retry_count_by_node: dict[NodeName, int]
    task_queue: list[dict[str, Any]]
    readiness_scorecard: dict[str, Any]
    evidence_pool: list[dict[str, Any]]
    kpi_quality_pool: list[dict[str, Any]]
    calculation_pool: list[dict[str, Any]]
    draft_pool: list[dict[str, Any]]
    verification_pool: list[dict[str, Any]]
    coverage_audit: dict[str, Any]
    approval_status_board: dict[str, Any]
    dashboard_snapshot_pool: list[dict[str, Any]]
    publish_ready: bool
    human_approval: HumanApprovalStatus


def _normalize_task_queue(
    value: object,
    *,
    tenant_id: str,
    project_id: str,
    framework_target: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    default_framework = framework_target[0] if framework_target else "TSRS2"
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            continue
        payload = {
            "task_id": item.get("task_id") or f"task_{index}",
            "tenant_id": item.get("tenant_id") or tenant_id,
            "project_id": item.get("project_id") or project_id,
            "framework_target": item.get("framework_target") or item.get("framework") or default_framework,
            "section_target": item.get("section_target") or item.get("framework") or default_framework,
            "priority": item.get("priority") or "normal",
            "deadline_utc": item.get("deadline_utc"),
            "query_text": item.get("query_text") or item.get("section_target") or default_framework,
            "retrieval_mode": item.get("retrieval_mode") or "hybrid",
            "top_k": item.get("top_k", 5),
            "min_score": item.get("min_score", 0.0),
            "min_coverage": item.get("min_coverage", 0.0),
            "retrieval_hints": item.get("retrieval_hints"),
            "status": item.get("status") or "planned",
            **item,
        }
        normalized.append(TaskEnvelope.model_validate(payload).model_dump())
    return normalized


def _normalize_model_list(value: object, model_cls: type[Any]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        normalized.append(model_cls.model_validate(item).model_dump())
    return normalized


def normalize_workflow_state(state: Mapping[str, Any]) -> WorkflowState:
    framework_target = [str(item) for item in state.get("framework_target", []) if str(item).strip()]
    tenant_id = str(state.get("tenant_id", "")).strip()
    project_id = str(state.get("project_id", "")).strip()
    return WorkflowState(
        run_id=str(state.get("run_id", "")).strip(),
        tenant_id=tenant_id,
        project_id=project_id,
        framework_target=framework_target,
        active_reg_pack_version=(
            str(state.get("active_reg_pack_version")).strip()
            if state.get("active_reg_pack_version") is not None
            else None
        ),
        scope_decision=ScopeDecision.model_validate(state.get("scope_decision") or {}).model_dump(
            exclude_none=True,
            exclude_defaults=True,
        ),
        active_node=str(state.get("active_node", "INIT_REQUEST")),  # type: ignore[arg-type]
        completed_nodes=[
            str(item)
            for item in state.get("completed_nodes", [])
            if str(item).strip()
        ],
        failed_nodes=[
            str(item)
            for item in state.get("failed_nodes", [])
            if str(item).strip()
        ],
        retry_count_by_node={
            str(node): int(value)
            for node, value in dict(state.get("retry_count_by_node", {})).items()
        },  # type: ignore[arg-type]
        task_queue=_normalize_task_queue(
            state.get("task_queue"),
            tenant_id=tenant_id,
            project_id=project_id,
            framework_target=framework_target,
        ),
        readiness_scorecard=ReadinessScorecard.model_validate(
            state.get("readiness_scorecard") or {}
        ).model_dump(exclude_none=True, exclude_defaults=True),
        evidence_pool=_normalize_model_list(state.get("evidence_pool"), EvidenceBlock),
        kpi_quality_pool=[
            item
            for item in state.get("kpi_quality_pool", [])
            if isinstance(item, dict)
        ],
        calculation_pool=_normalize_model_list(state.get("calculation_pool"), CalculationResult),
        draft_pool=_normalize_model_list(state.get("draft_pool"), DraftSection),
        verification_pool=_normalize_model_list(
            state.get("verification_pool"),
            VerificationResultContract,
        ),
        coverage_audit=dict(state.get("coverage_audit", {})) if isinstance(state.get("coverage_audit"), Mapping) else {},
        approval_status_board=(
            dict(state.get("approval_status_board", {}))
            if isinstance(state.get("approval_status_board"), Mapping)
            else {}
        ),
        dashboard_snapshot_pool=[
            item
            for item in state.get("dashboard_snapshot_pool", [])
            if isinstance(item, dict)
        ],
        publish_ready=bool(state.get("publish_ready", False)),
        human_approval=str(state.get("human_approval", "pending")),  # type: ignore[arg-type]
    )


def create_initial_workflow_state(
    *,
    run_id: str,
    tenant_id: str,
    project_id: str,
    framework_target: list[str],
    active_reg_pack_version: str | None = None,
    scope_decision: dict[str, Any] | None = None,
) -> WorkflowState:
    return normalize_workflow_state(
        WorkflowState(
        run_id=run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        framework_target=framework_target,
        active_reg_pack_version=active_reg_pack_version,
        scope_decision=scope_decision or {},
        active_node="INIT_REQUEST",
        completed_nodes=[],
        failed_nodes=[],
        retry_count_by_node={},
        task_queue=[],
        readiness_scorecard={},
        evidence_pool=[],
        kpi_quality_pool=[],
        calculation_pool=[],
        draft_pool=[],
        verification_pool=[],
        coverage_audit={},
        approval_status_board={},
        dashboard_snapshot_pool=[],
        publish_ready=False,
        human_approval="pending",
    )
    )
