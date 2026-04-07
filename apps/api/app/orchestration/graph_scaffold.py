# Bu orkestrasyon modulu, graph_scaffold adiminin durum akisini yonetir.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.orchestration.checkpoint_store import CheckpointRecord, CheckpointStore
from app.orchestration.state import NodeName, WorkflowState, create_initial_workflow_state


NODE_FLOW_ONE_CLICK: tuple[NodeName, ...] = (
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
)


@dataclass
class NodeTransitionOutcome:
    node: NodeName
    next_node: NodeName
    checkpoint: CheckpointRecord


def _next_node(node: NodeName) -> NodeName:
    idx = NODE_FLOW_ONE_CLICK.index(node)
    if idx >= len(NODE_FLOW_ONE_CLICK) - 1:
        return NODE_FLOW_ONE_CLICK[-1]
    return NODE_FLOW_ONE_CLICK[idx + 1]


def initialize_workflow(
    *,
    run_id: str,
    tenant_id: str,
    project_id: str,
    framework_target: list[str],
    checkpoint_store: CheckpointStore,
    active_reg_pack_version: str | None = None,
    scope_decision: dict[str, Any] | None = None,
) -> WorkflowState:
    state = create_initial_workflow_state(
        run_id=run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        framework_target=framework_target,
        active_reg_pack_version=active_reg_pack_version,
        scope_decision=scope_decision,
    )
    checkpoint_store.save_checkpoint(
        run_id=state["run_id"],
        node=state["active_node"],
        status="completed",
        state=state,
        metadata={"transition": "workflow_initialized"},
    )
    return state


def transition_success(
    *,
    state: WorkflowState,
    checkpoint_store: CheckpointStore,
    metadata: dict[str, Any] | None = None,
) -> NodeTransitionOutcome:
    current_node = state["active_node"]
    if current_node not in NODE_FLOW_ONE_CLICK:
        raise ValueError(f"Unknown active node: {current_node}")

    if current_node not in state["completed_nodes"]:
        state["completed_nodes"].append(current_node)
    state["failed_nodes"] = [node for node in state["failed_nodes"] if node != current_node]

    next_node = _next_node(current_node)
    state["active_node"] = next_node

    checkpoint = checkpoint_store.save_checkpoint(
        run_id=state["run_id"],
        node=current_node,
        status="completed",
        state=state,
        metadata=metadata or {"transition": f"{current_node}->{next_node}"},
    )
    return NodeTransitionOutcome(node=current_node, next_node=next_node, checkpoint=checkpoint)


def transition_failure(
    *,
    state: WorkflowState,
    checkpoint_store: CheckpointStore,
    reason: str,
) -> CheckpointRecord:
    current_node = state["active_node"]
    if current_node not in NODE_FLOW_ONE_CLICK:
        raise ValueError(f"Unknown active node: {current_node}")

    if current_node not in state["failed_nodes"]:
        state["failed_nodes"].append(current_node)

    retries = state["retry_count_by_node"].get(current_node, 0) + 1
    state["retry_count_by_node"][current_node] = retries

    return checkpoint_store.save_checkpoint(
        run_id=state["run_id"],
        node=current_node,
        status="failed",
        state=state,
        metadata={"reason": reason, "retry_count": retries},
    )
