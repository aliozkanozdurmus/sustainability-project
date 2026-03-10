from __future__ import annotations

from pathlib import Path

from app.orchestration.checkpoint_store import LocalJsonlCheckpointStore
from app.orchestration.graph_scaffold import (
    NODE_FLOW_ONE_CLICK,
    initialize_workflow,
    transition_failure,
    transition_success,
)
from app.orchestration.state import create_initial_workflow_state


def test_create_initial_workflow_state_contains_required_fields() -> None:
    state = create_initial_workflow_state(
        run_id="run-001",
        tenant_id="tenant-001",
        project_id="project-001",
        framework_target=["TSRS2"],
        active_reg_pack_version="TSRS_2026.1",
    )

    assert state["run_id"] == "run-001"
    assert state["tenant_id"] == "tenant-001"
    assert state["project_id"] == "project-001"
    assert state["framework_target"] == ["TSRS2"]
    assert state["active_node"] == "INIT_REQUEST"
    assert state["completed_nodes"] == []
    assert state["failed_nodes"] == []
    assert state["retry_count_by_node"] == {}
    assert state["publish_ready"] is False
    assert state["human_approval"] == "pending"

    required_keys = {
        "run_id",
        "tenant_id",
        "project_id",
        "framework_target",
        "active_reg_pack_version",
        "scope_decision",
        "active_node",
        "completed_nodes",
        "failed_nodes",
        "retry_count_by_node",
        "task_queue",
        "readiness_scorecard",
        "evidence_pool",
        "kpi_quality_pool",
        "calculation_pool",
        "draft_pool",
        "verification_pool",
        "coverage_audit",
        "approval_status_board",
        "dashboard_snapshot_pool",
        "publish_ready",
        "human_approval",
    }
    assert required_keys.issubset(state.keys())


def test_initialize_and_transition_success_checkpointing(tmp_path: Path) -> None:
    store = LocalJsonlCheckpointStore(root_path=tmp_path / "checkpoints")
    state = initialize_workflow(
        run_id="run-002",
        tenant_id="tenant-001",
        project_id="project-001",
        framework_target=["TSRS2", "CSRD"],
        checkpoint_store=store,
    )

    first_checkpoint = store.load_latest_checkpoint(run_id="run-002")
    assert first_checkpoint is not None
    assert first_checkpoint["node"] == "INIT_REQUEST"
    assert first_checkpoint["status"] == "completed"
    assert first_checkpoint["metadata"]["transition"] == "workflow_initialized"

    transition = transition_success(state=state, checkpoint_store=store)
    assert transition.node == "INIT_REQUEST"
    assert transition.next_node == "RESOLVE_APPLICABILITY"
    assert state["active_node"] == "RESOLVE_APPLICABILITY"
    assert "INIT_REQUEST" in state["completed_nodes"]

    latest = store.load_latest_checkpoint(run_id="run-002")
    assert latest is not None
    assert latest["status"] == "completed"
    assert latest["metadata"]["transition"] == "INIT_REQUEST->RESOLVE_APPLICABILITY"


def test_transition_failure_tracks_retry_and_keeps_active_node(tmp_path: Path) -> None:
    store = LocalJsonlCheckpointStore(root_path=tmp_path / "checkpoints")
    state = create_initial_workflow_state(
        run_id="run-003",
        tenant_id="tenant-001",
        project_id="project-001",
        framework_target=["TSRS2"],
    )

    checkpoint = transition_failure(
        state=state,
        checkpoint_store=store,
        reason="retrieval timeout",
    )

    assert checkpoint["status"] == "failed"
    assert checkpoint["metadata"]["reason"] == "retrieval timeout"
    assert checkpoint["metadata"]["retry_count"] == 1
    assert state["active_node"] == "INIT_REQUEST"
    assert state["retry_count_by_node"]["INIT_REQUEST"] == 1
    assert "INIT_REQUEST" in state["failed_nodes"]


def test_node_flow_contains_expected_first_and_last_nodes() -> None:
    assert NODE_FLOW_ONE_CLICK[0] == "INIT_REQUEST"
    assert NODE_FLOW_ONE_CLICK[-1] == "CLOSE_RUN"
