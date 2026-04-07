# Bu test dosyasi, orchestration executor davranisini dogrular.

from __future__ import annotations

import json
from pathlib import Path

from app.core.settings import settings
from app.orchestration.checkpoint_store import LocalJsonlCheckpointStore
from app.orchestration.executor import DEFAULT_NODE_HANDLERS, execute_workflow
from app.orchestration.graph_scaffold import initialize_workflow


def _write_local_index(root: Path, index_name: str, rows: dict[str, dict[str, object]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{index_name}.json"
    target.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")


def test_execute_workflow_stops_at_human_approval_when_pending(tmp_path: Path) -> None:
    checkpoint_store = LocalJsonlCheckpointStore(root_path=tmp_path / "checkpoints")
    search_root = tmp_path / "search-index"
    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(search_root)
    settings.azure_ai_search_index_name = "exec-index-1"

    _write_local_index(
        search_root,
        settings.azure_ai_search_index_name,
        {
            "chk-1": {
                "id": "chk-1",
                "chunk_id": "chk-1",
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "source_document_id": "doc-1",
                "chunk_index": 0,
                "page": 1,
                "section_label": "TSRS2",
                "token_count": 12,
                "content": "TSRS2 sustainability disclosures 2025 scope 2 emissions 150 and climate strategy.",
            },
            "chk-2": {
                "id": "chk-2",
                "chunk_id": "chk-2",
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "source_document_id": "doc-2",
                "chunk_index": 0,
                "page": 2,
                "section_label": "CSRD",
                "token_count": 11,
                "content": "CSRD sustainability disclosures 2025 include risk controls and target progress 90.",
            },
        },
    )

    state = initialize_workflow(
        run_id="run-exec-1",
        tenant_id="tenant-1",
        project_id="project-1",
        framework_target=["TSRS2", "CSRD"],
        checkpoint_store=checkpoint_store,
        scope_decision={
            "retrieval_tasks": [
                {
                    "task_id": "t-tsrs2",
                    "framework": "TSRS2",
                    "query_text": "TSRS2 sustainability disclosures scope 2 emissions",
                    "top_k": 2,
                    "retrieval_mode": "hybrid",
                },
                {
                    "task_id": "t-csrd",
                    "framework": "CSRD",
                    "query_text": "CSRD sustainability disclosures risk controls",
                    "top_k": 2,
                    "retrieval_mode": "hybrid",
                },
            ]
        },
    )

    try:
        outcome = execute_workflow(
            state=state,
            checkpoint_store=checkpoint_store,
            max_steps=64,
        )

        assert outcome.stop_reason == "awaiting_human_approval"
        assert outcome.executed_steps == 13
        assert state["active_node"] == "HUMAN_APPROVAL"
        assert state["publish_ready"] is False
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name


def test_execute_workflow_completes_when_human_approval_approved(tmp_path: Path) -> None:
    checkpoint_store = LocalJsonlCheckpointStore(root_path=tmp_path / "checkpoints")
    search_root = tmp_path / "search-index"
    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(search_root)
    settings.azure_ai_search_index_name = "exec-index-2"

    _write_local_index(
        search_root,
        settings.azure_ai_search_index_name,
        {
            "chk-1": {
                "id": "chk-1",
                "chunk_id": "chk-1",
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "source_document_id": "doc-1",
                "chunk_index": 0,
                "page": 1,
                "section_label": "TSRS2",
                "token_count": 10,
                "content": "TSRS2 sustainability disclosures include emission intensity 42 and governance controls.",
            }
        },
    )

    state = initialize_workflow(
        run_id="run-exec-2",
        tenant_id="tenant-1",
        project_id="project-1",
        framework_target=["TSRS2"],
        checkpoint_store=checkpoint_store,
        scope_decision={
            "retrieval_tasks": [
                {
                    "task_id": "t-tsrs2",
                    "framework": "TSRS2",
                    "query_text": "TSRS2 sustainability disclosures emission intensity",
                    "top_k": 2,
                    "retrieval_mode": "hybrid",
                }
            ]
        },
    )
    state["human_approval"] = "approved"

    try:
        outcome = execute_workflow(
            state=state,
            checkpoint_store=checkpoint_store,
            max_steps=64,
        )

        assert outcome.stop_reason == "completed"
        assert outcome.executed_steps == 16
        assert state["active_node"] == "CLOSE_RUN"
        assert state["publish_ready"] is True
        assert "PUBLISH_REPORT_PACKAGE" in state["completed_nodes"]
        assert "CLOSE_RUN" in state["completed_nodes"]
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name


def test_execute_workflow_retry_exhaustion_applies_compensation(tmp_path: Path) -> None:
    checkpoint_store = LocalJsonlCheckpointStore(root_path=tmp_path / "checkpoints")
    state = initialize_workflow(
        run_id="run-exec-3",
        tenant_id="tenant-1",
        project_id="project-1",
        framework_target=["CSRD"],
        checkpoint_store=checkpoint_store,
        scope_decision={
            "simulate_failures": {
                "RETRIEVE_EVIDENCE": 3,
            }
        },
    )

    outcome = execute_workflow(
        state=state,
        checkpoint_store=checkpoint_store,
        max_steps=64,
        retry_budget_by_node={"RETRIEVE_EVIDENCE": 1},
    )

    assert outcome.stop_reason == "failed_retry_exhausted"
    assert outcome.compensation_applied is True
    assert outcome.escalation_required is True
    assert "evidence_pool" in outcome.invalidated_fields
    assert "draft_pool" in outcome.invalidated_fields
    assert "verification_pool" in outcome.invalidated_fields

    assert state["active_node"] == "RETRIEVE_EVIDENCE"
    assert state["retry_count_by_node"]["RETRIEVE_EVIDENCE"] == 2
    assert state["evidence_pool"] == []
    assert state["calculation_pool"] == []
    assert state["draft_pool"] == []
    assert state["verification_pool"] == []
    assert state["publish_ready"] is False


def test_execute_workflow_verifier_blocks_numeric_claim_without_calc_artifact(
    tmp_path: Path,
) -> None:
    checkpoint_store = LocalJsonlCheckpointStore(root_path=tmp_path / "checkpoints")
    search_root = tmp_path / "search-index"
    original_use_local = settings.azure_ai_search_use_local
    original_root = settings.local_search_index_root
    original_index_name = settings.azure_ai_search_index_name
    settings.azure_ai_search_use_local = True
    settings.local_search_index_root = str(search_root)
    settings.azure_ai_search_index_name = "exec-index-verifier-fail"

    _write_local_index(
        search_root,
        settings.azure_ai_search_index_name,
        {
            "chk-vf-1": {
                "id": "chk-vf-1",
                "chunk_id": "chk-vf-1",
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "source_document_id": "doc-vf-1",
                "chunk_index": 0,
                "page": 1,
                "section_label": "TSRS2",
                "token_count": 9,
                "content": "TSRS2 sustainability disclosures numeric value 77 for climate KPI.",
            }
        },
    )

    state = initialize_workflow(
        run_id="run-exec-4",
        tenant_id="tenant-1",
        project_id="project-1",
        framework_target=["TSRS2"],
        checkpoint_store=checkpoint_store,
        scope_decision={
            "retrieval_tasks": [
                {
                    "task_id": "t-tsrs2",
                    "framework": "TSRS2",
                    "query_text": "TSRS2 sustainability disclosures numeric value",
                    "top_k": 2,
                    "retrieval_mode": "hybrid",
                }
            ]
        },
    )
    state["human_approval"] = "approved"

    handlers = dict(DEFAULT_NODE_HANDLERS)

    def _compute_without_artifact(local_state):
        local_state["calculation_pool"] = []
        return {"handler": "compute_metrics_overridden"}

    handlers["COMPUTE_METRICS"] = _compute_without_artifact

    try:
        outcome = execute_workflow(
            state=state,
            checkpoint_store=checkpoint_store,
            max_steps=64,
            handler_registry=handlers,
        )

        assert outcome.stop_reason == "awaiting_human_approval"
        assert outcome.compensation_applied is False
        assert outcome.escalation_required is False
        assert state["active_node"] == "HUMAN_APPROVAL"
        assert state["approval_status_board"]["triage_required"] is True
        assert state["approval_status_board"]["verifier_fail_count"] > 0
        assert state["approval_status_board"]["verifier_unsure_count"] == 0
        assert any(item.get("status") == "FAIL" for item in state["verification_pool"])
    finally:
        settings.azure_ai_search_use_local = original_use_local
        settings.local_search_index_root = original_root
        settings.azure_ai_search_index_name = original_index_name
