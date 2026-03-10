from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Protocol

from app.core.settings import settings
from app.orchestration.checkpoint_store import CheckpointRecord, CheckpointStore
from app.orchestration.graph_scaffold import NODE_FLOW_ONE_CLICK, transition_failure, transition_success
from app.orchestration.state import NodeName, WorkflowState
from app.schemas.retrieval import RetrievalHints
from app.services.retrieval import RetrievalQualityGateError, retrieve_evidence
from app.services.verifier import ClaimInput, verify_claims


ExecutionStopReason = Literal[
    "completed",
    "awaiting_human_approval",
    "rejected_human_approval",
    "failed_retry_exhausted",
    "max_steps_reached",
]


class NodeExecutionError(RuntimeError):
    pass


class NodeHandler(Protocol):
    def __call__(self, state: WorkflowState) -> dict[str, Any] | None: ...


@dataclass
class ExecutionOutcome:
    executed_steps: int
    stop_reason: ExecutionStopReason
    last_checkpoint: CheckpointRecord
    compensation_applied: bool
    invalidated_fields: list[str]
    escalation_required: bool


NODE_OUTPUT_FIELDS: dict[NodeName, list[str]] = {
    "VALIDATE_READINESS": ["readiness_scorecard"],
    "PLAN_TASKS": ["task_queue"],
    "RETRIEVE_EVIDENCE": ["evidence_pool"],
    "VALIDATE_KPI_QUALITY": ["kpi_quality_pool"],
    "COMPUTE_METRICS": ["calculation_pool"],
    "DRAFT_SECTION": ["draft_pool"],
    "VERIFY_CLAIMS": ["verification_pool"],
    "RUN_COVERAGE_AUDIT": ["coverage_audit"],
    "BUILD_DASHBOARD_SNAPSHOTS": ["dashboard_snapshot_pool"],
    "RUN_APPROVAL_ROUTING": ["approval_status_board"],
    "PUBLISH_REPORT_PACKAGE": ["publish_ready"],
}


def _default_retry_budget() -> dict[NodeName, int]:
    return {node: settings.workflow_retry_max_per_node for node in NODE_FLOW_ONE_CLICK}


def _merge_retry_budget(overrides: dict[str, int] | None) -> dict[NodeName, int]:
    budget = _default_retry_budget()
    if not overrides:
        return budget
    for node, value in overrides.items():
        if node in budget and value >= 0:
            budget[node] = value
    return budget


def _compute_backoff_seconds(*, attempt: int) -> int:
    if attempt <= 0:
        return 0
    base = max(1, settings.workflow_retry_base_seconds)
    max_defer = max(base, settings.workflow_retry_max_defer_seconds)
    return min(max_defer, base * (2 ** (attempt - 1)))


def _reset_state_field(state: WorkflowState, field: str) -> None:
    current = state[field]  # type: ignore[index]
    if isinstance(current, list):
        state[field] = []  # type: ignore[index]
    elif isinstance(current, dict):
        state[field] = {}  # type: ignore[index]
    elif isinstance(current, bool):
        state[field] = False  # type: ignore[index]
    else:
        state[field] = None  # type: ignore[index]


def compensate_failed_node(
    *,
    state: WorkflowState,
    failed_node: NodeName,
) -> list[str]:
    failed_idx = NODE_FLOW_ONE_CLICK.index(failed_node)
    impacted_nodes = set(NODE_FLOW_ONE_CLICK[failed_idx:])
    invalidated_fields: set[str] = set()

    for node in NODE_FLOW_ONE_CLICK[failed_idx:]:
        for field in NODE_OUTPUT_FIELDS.get(node, []):
            _reset_state_field(state, field)
            invalidated_fields.add(field)

    state["completed_nodes"] = [node for node in state["completed_nodes"] if node not in impacted_nodes]
    state["publish_ready"] = False
    return sorted(invalidated_fields)


def _consume_simulated_failure(
    *,
    state: WorkflowState,
    node: NodeName,
) -> bool:
    scope = state.get("scope_decision", {})
    simulate = scope.get("simulate_failures") if isinstance(scope, dict) else None
    if not isinstance(simulate, dict):
        return False
    remaining = simulate.get(node)
    if not isinstance(remaining, int) or remaining <= 0:
        return False
    simulate[node] = remaining - 1
    return True


def _detect_numeric_text(text: str) -> bool:
    return bool(re.search(r"\d", text))


def _extract_first_number(text: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _handle_init_request(state: WorkflowState) -> dict[str, Any]:
    state["scope_decision"].setdefault("mode", "one_click")
    return {"handler": "init_request"}


def _handle_resolve_applicability(state: WorkflowState) -> dict[str, Any]:
    state["readiness_scorecard"]["applicability_resolved"] = True
    state["readiness_scorecard"]["framework_target"] = state["framework_target"]
    return {"handler": "resolve_applicability"}


def _handle_validate_readiness(state: WorkflowState) -> dict[str, Any]:
    state["readiness_scorecard"]["status"] = "ready"
    return {"handler": "validate_readiness"}


def _handle_plan_tasks(state: WorkflowState) -> dict[str, Any]:
    if state["task_queue"]:
        return {"handler": "plan_tasks", "task_count": len(state["task_queue"])}

    scope = state.get("scope_decision", {})
    retrieval_defaults = scope.get("retrieval_defaults", {}) if isinstance(scope, dict) else {}
    retrieval_tasks = scope.get("retrieval_tasks", []) if isinstance(scope, dict) else []

    default_top_k = int(retrieval_defaults.get("top_k", 5))
    default_mode = str(retrieval_defaults.get("retrieval_mode", "hybrid"))
    default_min_score = float(retrieval_defaults.get("min_score", 0.0))
    default_min_coverage = float(retrieval_defaults.get("min_coverage", 0.0))
    default_hints = retrieval_defaults.get("retrieval_hints")

    tasks: list[dict[str, Any]] = []
    if isinstance(retrieval_tasks, list) and retrieval_tasks:
        for idx, raw_task in enumerate(retrieval_tasks):
            if not isinstance(raw_task, dict):
                continue
            framework = str(raw_task.get("framework") or state["framework_target"][0])
            query_text = str(raw_task.get("query_text") or "").strip()
            if not query_text:
                continue
            tasks.append(
                {
                    "task_id": str(raw_task.get("task_id") or f"task_{idx}_{framework.lower()}"),
                    "framework": framework,
                    "section_target": str(raw_task.get("section_target") or framework),
                    "query_text": query_text,
                    "retrieval_mode": str(raw_task.get("retrieval_mode") or default_mode),
                    "top_k": int(raw_task.get("top_k", default_top_k)),
                    "min_score": float(raw_task.get("min_score", default_min_score)),
                    "min_coverage": float(raw_task.get("min_coverage", default_min_coverage)),
                    "retrieval_hints": raw_task.get("retrieval_hints", default_hints),
                    "status": "planned",
                }
            )
    else:
        for framework in state["framework_target"]:
            tasks.append(
                {
                    "task_id": f"task_{framework.lower()}",
                    "framework": framework,
                    "section_target": framework,
                    "query_text": f"{framework} sustainability disclosures",
                    "retrieval_mode": default_mode,
                    "top_k": default_top_k,
                    "min_score": default_min_score,
                    "min_coverage": default_min_coverage,
                    "retrieval_hints": default_hints,
                    "status": "planned",
                }
            )

    if not tasks:
        raise NodeExecutionError("No executable retrieval tasks planned for workflow.")

    state["task_queue"] = tasks
    return {"handler": "plan_tasks", "task_count": len(tasks)}


def _handle_retrieve_evidence(state: WorkflowState) -> dict[str, Any]:
    if not state["task_queue"]:
        raise NodeExecutionError("Task queue is empty. PLAN_TASKS must run before retrieval.")

    evidence_pool: list[dict[str, Any]] = []
    diagnostics_pool: list[dict[str, Any]] = []

    for task in state["task_queue"]:
        query_text = str(task.get("query_text") or "").strip()
        if not query_text:
            raise NodeExecutionError(f"Task {task.get('task_id')} does not define query_text.")

        hints_payload = task.get("retrieval_hints")
        hints = None
        if isinstance(hints_payload, dict):
            hints = RetrievalHints.model_validate(hints_payload)

        try:
            outcome = retrieve_evidence(
                tenant_id=state["tenant_id"],
                project_id=state["project_id"],
                query_text=query_text,
                top_k=int(task.get("top_k", 5)),
                retrieval_mode=str(task.get("retrieval_mode", "hybrid")),
                min_score=float(task.get("min_score", 0.0)),
                min_coverage=float(task.get("min_coverage", 0.0)),
                retrieval_hints=hints,
            )
        except RetrievalQualityGateError as exc:
            raise NodeExecutionError(
                f"Retrieval quality gate failed for task {task.get('task_id')}: {exc.reason}"
            ) from exc
        except Exception as exc:
            raise NodeExecutionError(f"Retrieval execution failed for task {task.get('task_id')}: {exc}") from exc

        diagnostics_pool.append(
            {
                "task_id": str(task.get("task_id")),
                "query_text": query_text,
                "diagnostics": outcome.diagnostics.model_dump(),
            }
        )

        for row in outcome.evidence:
            text = row.text or ""
            evidence_pool.append(
                {
                    "evidence_id": row.evidence_id,
                    "task_id": str(task.get("task_id")),
                    "framework": str(task.get("framework")),
                    "section_target": str(task.get("section_target", "")),
                    "query_text": query_text,
                    "source_document_id": row.source_document_id,
                    "chunk_id": row.chunk_id,
                    "page": row.page,
                    "text": text,
                    "score_final": row.score_final,
                    "score_dense": row.score_dense,
                    "score_sparse": row.score_sparse,
                    "metadata": row.metadata,
                    "citations": [
                        {
                            "source_document_id": row.source_document_id,
                            "chunk_id": row.chunk_id,
                            "span_start": 0,
                            "span_end": min(len(text), 200),
                        }
                    ],
                }
            )

    if not evidence_pool:
        raise NodeExecutionError("Retrieval returned no evidence across planned tasks.")

    state["evidence_pool"] = evidence_pool
    state["coverage_audit"]["retrieval"] = {
        "task_count": len(state["task_queue"]),
        "evidence_count": len(evidence_pool),
        "diagnostics": diagnostics_pool,
    }
    return {
        "handler": "retrieve_evidence",
        "task_count": len(state["task_queue"]),
        "evidence_count": len(evidence_pool),
    }


def _handle_validate_kpi_quality(state: WorkflowState) -> dict[str, Any]:
    policy = state.get("scope_decision", {}).get("quality_policy", {})
    min_score_final = float(policy.get("min_score_final", 0.0)) if isinstance(policy, dict) else 0.0
    min_text_length = int(policy.get("min_text_length", 8)) if isinstance(policy, dict) else 8
    block_on_quality_fail = bool(policy.get("block_on_quality_fail", False)) if isinstance(policy, dict) else False

    quality_items: list[dict[str, Any]] = []
    fail_count = 0
    for evidence in state["evidence_pool"]:
        score_final = float(evidence.get("score_final", 0.0) or 0.0)
        text = str(evidence.get("text", "") or "")
        has_provenance = bool(evidence.get("source_document_id")) and bool(evidence.get("chunk_id"))
        reasons: list[str] = []
        if score_final < min_score_final:
            reasons.append("low_retrieval_score")
        if len(text.strip()) < min_text_length:
            reasons.append("insufficient_text_length")
        if not has_provenance:
            reasons.append("missing_provenance")

        quality_score = max(0, min(100, int(round(score_final * 100))))
        if reasons:
            quality_grade = "C" if quality_score >= 60 else "D"
            status = "fail"
            fail_count += 1
        else:
            quality_grade = "A" if quality_score >= 80 else "B"
            status = "pass"

        quality_items.append(
            {
                "evidence_id": evidence["evidence_id"],
                "quality_grade": quality_grade,
                "quality_score": quality_score,
                "status": status,
                "reasons": reasons,
            }
        )
    state["kpi_quality_pool"] = quality_items
    if block_on_quality_fail and fail_count > 0:
        raise NodeExecutionError(f"KPI quality validation failed for {fail_count} evidence entries.")
    return {
        "handler": "validate_kpi_quality",
        "quality_count": len(quality_items),
        "fail_count": fail_count,
    }


def _handle_compute_metrics(state: WorkflowState) -> dict[str, Any]:
    calc_items: list[dict[str, Any]] = []
    for evidence in state["evidence_pool"]:
        text = str(evidence.get("text", "") or "")
        if not _detect_numeric_text(text):
            continue
        parsed_value = _extract_first_number(text)
        calc_items.append(
            {
                "calc_id": f"calc_{evidence['evidence_id']}",
                "evidence_id": evidence["evidence_id"],
                "status": "completed",
                "formula_name": "regex_numeric_extract_v1",
                "code_hash": "sha256:regex_numeric_extract_v1",
                "inputs_ref": f"state://{state['run_id']}/evidence/{evidence['evidence_id']}",
                "output_unit": "unitless",
                "output_value": parsed_value,
                "trace_log_ref": f"state://{state['run_id']}/calc/{evidence['evidence_id']}/trace",
            }
        )
    state["calculation_pool"] = calc_items
    return {"handler": "compute_metrics", "calc_count": len(calc_items)}


def _handle_draft_section(state: WorkflowState) -> dict[str, Any]:
    calc_map = {
        str(row.get("evidence_id")): str(row.get("calc_id"))
        for row in state["calculation_pool"]
        if row.get("evidence_id") and row.get("calc_id")
    }

    drafts: list[dict[str, Any]] = []
    for task in state["task_queue"]:
        task_id = str(task.get("task_id"))
        task_evidence = [row for row in state["evidence_pool"] if str(row.get("task_id")) == task_id]
        claims: list[dict[str, Any]] = []
        for idx, evidence in enumerate(task_evidence):
            statement = str(evidence.get("text", "")).strip()
            is_numeric = _detect_numeric_text(statement)
            citations = evidence.get("citations", [])
            evidence_id = str(evidence.get("evidence_id"))
            calculation_refs: list[str] = []
            if is_numeric:
                calc_id = calc_map.get(evidence_id)
                if calc_id:
                    calculation_refs.append(calc_id)
            claims.append(
                {
                    "claim_id": f"clm_{task_id}_{idx}",
                    "statement": statement,
                    "is_numeric": is_numeric,
                    "citations": citations,
                    "calculation_refs": calculation_refs,
                    "evidence_id": evidence_id,
                }
            )
        drafts.append(
            {
                "section_code": str(task.get("framework")),
                "status": "drafted",
                "claims": claims,
                "claim_count": len(claims),
            }
        )

    if not drafts:
        raise NodeExecutionError("No draft sections created from evidence.")

    state["draft_pool"] = drafts
    return {"handler": "draft_section", "draft_count": len(drafts)}


def _handle_verify_claims(state: WorkflowState) -> dict[str, Any]:
    evidence_map = {
        (str(item.get("source_document_id")), str(item.get("chunk_id"))): str(item.get("text", "") or "")
        for item in state["evidence_pool"]
        if item.get("source_document_id") and item.get("chunk_id")
    }
    calc_ids = {str(item.get("calc_id")) for item in state["calculation_pool"] if item.get("calc_id")}

    claim_inputs: list[ClaimInput] = []
    section_by_claim: dict[str, str] = {}
    for draft in state["draft_pool"]:
        claims = draft.get("claims", [])
        if not isinstance(claims, list):
            continue
        for claim in claims:
            claim_id = str(claim.get("claim_id", "")).strip()
            if not claim_id:
                continue
            citations = claim.get("citations", [])
            calc_refs = claim.get("calculation_refs", [])
            claim_inputs.append(
                ClaimInput(
                    claim_id=claim_id,
                    statement=str(claim.get("statement", "") or ""),
                    is_numeric=bool(claim.get("is_numeric")),
                    citations=citations if isinstance(citations, list) else [],
                    calculation_refs=[str(ref) for ref in calc_refs] if isinstance(calc_refs, list) else [],
                )
            )
            section_by_claim[claim_id] = str(draft.get("section_code", ""))

    verifier_policy = state.get("scope_decision", {}).get("verifier_policy", {})
    pass_threshold = None
    unsure_threshold = None
    min_citations = 1
    if isinstance(verifier_policy, dict):
        if "pass_threshold" in verifier_policy:
            pass_threshold = float(verifier_policy["pass_threshold"])
        if "unsure_threshold" in verifier_policy:
            unsure_threshold = float(verifier_policy["unsure_threshold"])
        if "min_citations" in verifier_policy:
            min_citations = max(1, int(verifier_policy["min_citations"]))

    decisions = verify_claims(
        claims=claim_inputs,
        evidence_map=evidence_map,
        calculation_ids=calc_ids,
        pass_threshold=pass_threshold,
        unsure_threshold=unsure_threshold,
    )
    citation_count_by_claim = {claim.claim_id: len(claim.citations) for claim in claim_inputs}

    verifications: list[dict[str, Any]] = []
    fail_count = 0
    critical_fail_count = 0
    unsure_count = 0
    for decision in decisions:
        citation_count = citation_count_by_claim.get(decision.claim_id, 0)
        if decision.status == "PASS" and citation_count < min_citations:
            decision.status = "UNSURE"
            decision.severity = "normal"
            decision.reason = "insufficient_citation_count_for_policy"

        if decision.status == "FAIL":
            fail_count += 1
            if decision.severity == "critical":
                critical_fail_count += 1
        elif decision.status == "UNSURE":
            unsure_count += 1

        verifications.append(
            {
                "section_code": section_by_claim.get(decision.claim_id, ""),
                "claim_id": decision.claim_id,
                "status": decision.status,
                "severity": decision.severity,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "evidence_refs": decision.evidence_refs,
            }
        )

    triage_required = critical_fail_count > 0 or unsure_count > 0
    state["verification_pool"] = verifications
    state["approval_status_board"]["triage_required"] = triage_required
    state["approval_status_board"]["verifier_fail_count"] = fail_count
    state["approval_status_board"]["verifier_unsure_count"] = unsure_count
    if triage_required:
        state["human_approval"] = "pending"
        state["publish_ready"] = False

    return {
        "handler": "verify_claims",
        "verification_count": len(verifications),
        "fail_count": fail_count,
        "critical_fail_count": critical_fail_count,
        "unsure_count": unsure_count,
        "triage_required": triage_required,
    }


def _handle_review_loop(state: WorkflowState) -> dict[str, Any]:
    fail_count = sum(1 for item in state["verification_pool"] if item.get("status") != "PASS")
    state["coverage_audit"]["review_loop_fail_count"] = fail_count
    return {"handler": "review_loop", "fail_count": fail_count}


def _handle_run_coverage_audit(state: WorkflowState) -> dict[str, Any]:
    has_failures = any(item.get("status") == "FAIL" for item in state["verification_pool"])
    has_unsure = any(item.get("status") == "UNSURE" for item in state["verification_pool"])
    state["coverage_audit"]["status"] = "pass" if not (has_failures or has_unsure) else "fail"
    state["coverage_audit"]["pass_ratio"] = (
        1.0 if not state["verification_pool"] else sum(
            1 for item in state["verification_pool"] if item.get("status") == "PASS"
        ) / len(state["verification_pool"])
    )
    state["coverage_audit"]["fail_count"] = sum(1 for item in state["verification_pool"] if item.get("status") == "FAIL")
    state["coverage_audit"]["unsure_count"] = sum(1 for item in state["verification_pool"] if item.get("status") == "UNSURE")
    return {"handler": "run_coverage_audit", "status": state["coverage_audit"]["status"]}


def _handle_build_dashboard_snapshots(state: WorkflowState) -> dict[str, Any]:
    snapshots = [
        {
            "snapshot_id": f"dash_{idx}",
            "status": "generated",
        }
        for idx, _ in enumerate(state["verification_pool"])
    ]
    state["dashboard_snapshot_pool"] = snapshots
    return {"handler": "build_dashboard_snapshots", "snapshot_count": len(snapshots)}


def _handle_run_approval_routing(state: WorkflowState) -> dict[str, Any]:
    previous_board = state.get("approval_status_board", {})
    triage_required = bool(previous_board.get("triage_required")) if isinstance(previous_board, dict) else False
    verifier_fail_count = (
        int(previous_board.get("verifier_fail_count", 0)) if isinstance(previous_board, dict) else 0
    )
    verifier_unsure_count = (
        int(previous_board.get("verifier_unsure_count", 0)) if isinstance(previous_board, dict) else 0
    )
    state["approval_status_board"] = {
        "triage_required": triage_required,
        "verifier_fail_count": verifier_fail_count,
        "verifier_unsure_count": verifier_unsure_count,
        "board_stage": (
            "triage_required"
            if triage_required
            else ("pending" if state["human_approval"] != "approved" else "approved")
        ),
        "sla_breach": False,
    }
    return {"handler": "run_approval_routing", "board_stage": state["approval_status_board"]["board_stage"]}


def _handle_human_approval(state: WorkflowState) -> dict[str, Any]:
    return {"handler": "human_approval", "status": state["human_approval"]}


def _handle_publish_report_package(state: WorkflowState) -> dict[str, Any]:
    if state["human_approval"] != "approved":
        raise NodeExecutionError("Publish blocked: human approval is not approved.")
    if bool(state["approval_status_board"].get("triage_required")):
        raise NodeExecutionError("Publish blocked: verifier triage is still required.")
    if not state["verification_pool"]:
        raise NodeExecutionError("Publish blocked: verification pool is empty.")
    if any(item.get("status") != "PASS" for item in state["verification_pool"]):
        raise NodeExecutionError("Publish blocked: verifier has non-PASS claims.")
    if state["coverage_audit"].get("status") == "fail":
        raise NodeExecutionError("Publish blocked: coverage audit failed.")
    state["publish_ready"] = True
    return {"handler": "publish_report_package", "publish_ready": True}


def _handle_close_run(state: WorkflowState) -> dict[str, Any]:
    return {"handler": "close_run", "publish_ready": state["publish_ready"]}


DEFAULT_NODE_HANDLERS: dict[NodeName, NodeHandler] = {
    "INIT_REQUEST": _handle_init_request,
    "RESOLVE_APPLICABILITY": _handle_resolve_applicability,
    "VALIDATE_READINESS": _handle_validate_readiness,
    "PLAN_TASKS": _handle_plan_tasks,
    "RETRIEVE_EVIDENCE": _handle_retrieve_evidence,
    "VALIDATE_KPI_QUALITY": _handle_validate_kpi_quality,
    "COMPUTE_METRICS": _handle_compute_metrics,
    "DRAFT_SECTION": _handle_draft_section,
    "VERIFY_CLAIMS": _handle_verify_claims,
    "REVIEW_LOOP": _handle_review_loop,
    "RUN_COVERAGE_AUDIT": _handle_run_coverage_audit,
    "BUILD_DASHBOARD_SNAPSHOTS": _handle_build_dashboard_snapshots,
    "RUN_APPROVAL_ROUTING": _handle_run_approval_routing,
    "HUMAN_APPROVAL": _handle_human_approval,
    "PUBLISH_REPORT_PACKAGE": _handle_publish_report_package,
    "CLOSE_RUN": _handle_close_run,
}


def execute_workflow(
    *,
    state: WorkflowState,
    checkpoint_store: CheckpointStore,
    max_steps: int,
    retry_budget_by_node: dict[str, int] | None = None,
    handler_registry: dict[NodeName, NodeHandler] | None = None,
) -> ExecutionOutcome:
    handlers = handler_registry or DEFAULT_NODE_HANDLERS
    retry_budget = _merge_retry_budget(retry_budget_by_node)
    executed_steps = 0
    compensation_applied = False
    invalidated_fields: list[str] = []
    escalation_required = False

    last_checkpoint = checkpoint_store.load_latest_checkpoint(run_id=state["run_id"])
    if last_checkpoint is None:
        raise ValueError("No checkpoint found for workflow execution.")

    while executed_steps < max_steps:
        current_node = state["active_node"]

        if current_node == "HUMAN_APPROVAL":
            if state["human_approval"] == "pending":
                last_checkpoint = checkpoint_store.save_checkpoint(
                    run_id=state["run_id"],
                    node=current_node,
                    status="completed",
                    state=state,
                    metadata={"execution_stop": "awaiting_human_approval"},
                )
                return ExecutionOutcome(
                    executed_steps=executed_steps,
                    stop_reason="awaiting_human_approval",
                    last_checkpoint=last_checkpoint,
                    compensation_applied=compensation_applied,
                    invalidated_fields=invalidated_fields,
                    escalation_required=escalation_required,
                )
            if state["human_approval"] == "rejected":
                last_checkpoint = transition_failure(
                    state=state,
                    checkpoint_store=checkpoint_store,
                    reason="Human approval rejected.",
                )
                escalation_required = True
                return ExecutionOutcome(
                    executed_steps=executed_steps + 1,
                    stop_reason="rejected_human_approval",
                    last_checkpoint=last_checkpoint,
                    compensation_applied=compensation_applied,
                    invalidated_fields=invalidated_fields,
                    escalation_required=escalation_required,
                )

        try:
            if _consume_simulated_failure(state=state, node=current_node):
                raise NodeExecutionError(f"Simulated failure for node {current_node}.")

            handler = handlers.get(current_node)
            if handler is None:
                raise NodeExecutionError(f"No handler registered for node {current_node}.")

            metadata = handler(state) or {}
            transition = transition_success(
                state=state,
                checkpoint_store=checkpoint_store,
                metadata={
                    "execution_mode": "auto",
                    "node": current_node,
                    **metadata,
                },
            )
            executed_steps += 1
            last_checkpoint = transition.checkpoint

            if current_node == "CLOSE_RUN":
                return ExecutionOutcome(
                    executed_steps=executed_steps,
                    stop_reason="completed",
                    last_checkpoint=last_checkpoint,
                    compensation_applied=compensation_applied,
                    invalidated_fields=invalidated_fields,
                    escalation_required=escalation_required,
                )
        except Exception as exc:
            failed_checkpoint = transition_failure(
                state=state,
                checkpoint_store=checkpoint_store,
                reason=str(exc),
            )
            executed_steps += 1
            last_checkpoint = failed_checkpoint

            retries = state["retry_count_by_node"].get(current_node, 0)
            budget = retry_budget[current_node]
            if retries > budget:
                invalidated_fields = compensate_failed_node(state=state, failed_node=current_node)
                compensation_applied = True
                escalation_required = True
                last_checkpoint = checkpoint_store.save_checkpoint(
                    run_id=state["run_id"],
                    node=current_node,
                    status="failed",
                    state=state,
                    metadata={
                        "execution_stop": "failed_retry_exhausted",
                        "reason": str(exc),
                        "retry_count": retries,
                        "retry_budget": budget,
                        "compensation_applied": True,
                        "invalidated_fields": invalidated_fields,
                    },
                )
                return ExecutionOutcome(
                    executed_steps=executed_steps,
                    stop_reason="failed_retry_exhausted",
                    last_checkpoint=last_checkpoint,
                    compensation_applied=compensation_applied,
                    invalidated_fields=invalidated_fields,
                    escalation_required=escalation_required,
                )

            backoff_seconds = _compute_backoff_seconds(attempt=retries)
            last_checkpoint = checkpoint_store.save_checkpoint(
                run_id=state["run_id"],
                node=current_node,
                status="failed",
                state=state,
                metadata={
                    "execution_mode": "auto",
                    "retry_scheduled_seconds": backoff_seconds,
                    "retry_count": retries,
                    "retry_budget": budget,
                },
            )

    last_checkpoint = checkpoint_store.save_checkpoint(
        run_id=state["run_id"],
        node=state["active_node"],
        status="completed",
        state=state,
        metadata={"execution_stop": "max_steps_reached"},
    )
    return ExecutionOutcome(
        executed_steps=executed_steps,
        stop_reason="max_steps_reached",
        last_checkpoint=last_checkpoint,
        compensation_applied=compensation_applied,
        invalidated_fields=invalidated_fields,
        escalation_required=escalation_required,
    )
