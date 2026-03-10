from __future__ import annotations

from typing import Any, Literal, TypedDict


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


def create_initial_workflow_state(
    *,
    run_id: str,
    tenant_id: str,
    project_id: str,
    framework_target: list[str],
    active_reg_pack_version: str | None = None,
    scope_decision: dict[str, Any] | None = None,
) -> WorkflowState:
    return WorkflowState(
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
