# Bu route, runs uc noktasinin HTTP giris katmanini tanimlar.

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.core.settings import settings
from app.db.session import get_db
from app.models.core import (
    AuditEvent,
    BrandKit,
    CalculationRun,
    Claim,
    ClaimCitation,
    Chunk,
    CompanyProfile,
    Project,
    ReportArtifact,
    ReportRun,
    ReportSection,
    ReportBlueprint,
    SourceDocument,
    Tenant,
    VerificationResult,
)
from app.orchestration.checkpoint_store import CheckpointRecord, get_checkpoint_store
from app.orchestration.executor import execute_workflow
from app.orchestration.graph_scaffold import initialize_workflow, transition_failure, transition_success
from app.schemas.auth import CurrentUser
from app.schemas.runs import (
    ReportArtifactResponse,
    RunAdvanceRequest,
    RunCreateRequest,
    RunExecuteRequest,
    RunExecuteResponse,
    RunListItem,
    RunListResponse,
    RunPackageStatusResponse,
    RunPublishRequest,
    RunPublishResponse,
    RunPublishBlocker,
    RunStatusResponse,
    RunTriageItem,
    RunTriageReportResponse,
)
from app.services.report_context import build_report_factory_readiness, ensure_project_report_context
from app.services.report_factory import (
    ASSUMPTION_REGISTER_ARTIFACT_TYPE,
    CALCULATION_APPENDIX_ARTIFACT_TYPE,
    CITATION_INDEX_ARTIFACT_TYPE,
    COVERAGE_MATRIX_ARTIFACT_TYPE,
    REPORT_PDF_ARTIFACT_TYPE,
    VISUAL_MANIFEST_ARTIFACT_TYPE,
    build_package_status_payload,
    ensure_report_package_record,
    get_report_artifact_by_id,
    get_report_package,
    list_run_artifacts,
    _to_artifact_response_payload,
)
from app.services.job_queue import JobQueueService, get_job_queue_service
from app.services.report_pdf import download_report_artifact_bytes

router = APIRouter(prefix="/runs", tags=["runs"])
RUN_MUTATION_ROLES = ("admin", "compliance_manager", "analyst")
RUN_READ_ROLES = (*RUN_MUTATION_ROLES, "auditor_readonly")
RUN_PUBLISH_ROLES = ("admin", "compliance_manager", "board_member")


def _to_report_artifact_response(artifact: ReportArtifact) -> ReportArtifactResponse:
    return ReportArtifactResponse(
        artifact_id=artifact.id,
        artifact_type=artifact.artifact_type,
        filename=artifact.filename,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        checksum=artifact.checksum,
        created_at_utc=artifact.created_at.isoformat(),
        download_path=(
            f"/runs/{artifact.report_run_id}/artifacts/{artifact.id}"
            f"?tenant_id={artifact.tenant_id}&project_id={artifact.project_id}"
        ),
        metadata=artifact.artifact_metadata_json or {},
    )


def _get_report_pdf_response(
    *,
    db: Session,
    report_run_id: str,
) -> ReportArtifactResponse | None:
    artifact = next(
        (
            item
            for item in list_run_artifacts(db=db, report_run_id=report_run_id)
            if item.artifact_type == REPORT_PDF_ARTIFACT_TYPE
        ),
        None,
    )
    if artifact is None:
        return None
    return _to_report_artifact_response(artifact)


def _resolve_report_factory_context(
    *,
    db: Session,
    tenant: Tenant,
    project: Project,
    payload: RunCreateRequest,
) -> tuple[CompanyProfile, BrandKit, ReportBlueprint]:
    company_profile, brand_kit, blueprint, _ = ensure_project_report_context(
        db=db,
        tenant=tenant,
        project=project,
    )

    if payload.company_profile_ref:
        selected_profile = db.get(CompanyProfile, payload.company_profile_ref)
        if selected_profile is None or selected_profile.project_id != project.id:
            raise HTTPException(status_code=404, detail="Company profile not found for project.")
        company_profile = selected_profile

    if payload.brand_kit_ref:
        selected_brand_kit = db.get(BrandKit, payload.brand_kit_ref)
        if selected_brand_kit is None or selected_brand_kit.project_id != project.id:
            raise HTTPException(status_code=404, detail="Brand kit not found for project.")
        brand_kit = selected_brand_kit

    blueprint_version = payload.report_blueprint_version or settings.report_factory_default_blueprint_version
    selected_blueprint = db.scalar(
        select(ReportBlueprint).where(
            ReportBlueprint.project_id == project.id,
            ReportBlueprint.version == blueprint_version,
        )
    )
    if selected_blueprint is None:
        raise HTTPException(status_code=404, detail="Report blueprint not found for project.")

    factory_mode_requested = bool(
        payload.company_profile_ref
        or payload.brand_kit_ref
        or payload.report_blueprint_version
        or payload.connector_scope
    )
    if factory_mode_requested:
        readiness = build_report_factory_readiness(
            company_profile=company_profile,
            brand_kit=brand_kit,
        )
        if not readiness["is_ready"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "REPORT_FACTORY_CONTEXT_INCOMPLETE",
                    "message": "Brand kit veya company profile eksik. Report factory run'i baslatilamadi.",
                    **readiness,
                },
            )
    return company_profile, brand_kit, selected_blueprint


@router.get("", response_model=RunListResponse, status_code=status.HTTP_200_OK)
async def list_runs(
    tenant_id: str,
    project_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    user: CurrentUser = Depends(
        require_roles(*RUN_READ_ROLES)
    ),
    db: Session = Depends(get_db),
) -> RunListResponse:
    _ = user
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.tenant_id == tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")

    total = int(
        db.scalar(
            select(func.count(ReportRun.id)).where(
                ReportRun.tenant_id == tenant_id,
                ReportRun.project_id == project_id,
            )
        )
        or 0
    )
    offset = (page - 1) * size
    rows = (
        db.execute(
            select(ReportRun)
            .where(
                ReportRun.tenant_id == tenant_id,
                ReportRun.project_id == project_id,
            )
            .order_by(ReportRun.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        .scalars()
        .all()
    )

    artifact_map: dict[str, ReportArtifactResponse] = {}
    run_ids = [run.id for run in rows]
    if run_ids:
        artifacts = db.scalars(
            select(ReportArtifact).where(
                ReportArtifact.report_run_id.in_(run_ids),
                ReportArtifact.artifact_type == REPORT_PDF_ARTIFACT_TYPE,
            )
        ).all()
        artifact_map = {artifact.report_run_id: _to_report_artifact_response(artifact) for artifact in artifacts}

    checkpoint_store = get_checkpoint_store()
    items: list[RunListItem] = []
    for run in rows:
        latest = checkpoint_store.load_latest_checkpoint(run_id=run.id)
        if latest is not None:
            state = latest["state"]
            active_node = str(state.get("active_node", "INIT_REQUEST"))
            human_approval = str(state.get("human_approval", "pending"))
            approval_board = state.get("approval_status_board", {})
            triage_required = bool(approval_board.get("triage_required")) if isinstance(approval_board, dict) else False
            last_checkpoint_status = latest["status"]
            last_checkpoint_at_utc = latest["created_at_utc"]
        else:
            active_node = "INIT_REQUEST"
            human_approval = "pending"
            triage_required = False
            last_checkpoint_status = "completed"
            last_checkpoint_at_utc = None

        items.append(
            RunListItem(
                run_id=run.id,
                report_run_status=run.status,
                publish_ready=run.publish_ready,
                started_at_utc=run.started_at.isoformat() if run.started_at else None,
                completed_at_utc=run.completed_at.isoformat() if run.completed_at else None,
                active_node=active_node,
                human_approval=human_approval,
                triage_required=triage_required,
                last_checkpoint_status=last_checkpoint_status,
                last_checkpoint_at_utc=last_checkpoint_at_utc,
                package_status=run.package_status,
                report_quality_score=run.report_quality_score,
                latest_sync_at_utc=run.latest_sync_at.isoformat() if run.latest_sync_at else None,
                visual_generation_status=run.visual_generation_status,
                report_pdf=artifact_map.get(run.id),
            )
        )

    return RunListResponse(total=total, page=page, size=size, items=items)


def _build_run_status_response(
    *,
    db: Session,
    report_run: ReportRun,
    checkpoint: CheckpointRecord,
) -> RunStatusResponse:
    state = checkpoint["state"]
    approval_board = state.get("approval_status_board", {})
    triage_required = bool(approval_board.get("triage_required")) if isinstance(approval_board, dict) else False
    return RunStatusResponse(
        run_id=report_run.id,
        report_run_id=report_run.id,
        report_run_status=report_run.status,
        active_node=str(state["active_node"]),
        completed_nodes=[str(node) for node in state["completed_nodes"]],
        failed_nodes=[str(node) for node in state["failed_nodes"]],
        retry_count_by_node={str(k): int(v) for k, v in state["retry_count_by_node"].items()},
        publish_ready=bool(state["publish_ready"]),
        human_approval=str(state["human_approval"]),
        triage_required=triage_required,
        last_checkpoint_status=checkpoint["status"],
        last_checkpoint_at_utc=checkpoint["created_at_utc"],
        package_status=report_run.package_status,
        report_quality_score=report_run.report_quality_score,
        latest_sync_at_utc=report_run.latest_sync_at.isoformat() if report_run.latest_sync_at else None,
        visual_generation_status=report_run.visual_generation_status,
        report_pdf=_get_report_pdf_response(db=db, report_run_id=report_run.id),
    )


def _resolve_report_run_status_from_stop_reason(*, stop_reason: str, triage_required: bool) -> str:
    if stop_reason == "completed":
        return "completed"
    if stop_reason == "awaiting_human_approval":
        return "triage_required" if triage_required else "awaiting_human_approval"
    if stop_reason in {"failed_retry_exhausted", "rejected_human_approval"}:
        return "failed"
    return "running"


def _build_run_publish_response(
    *,
    db: Session,
    report_run: ReportRun,
    run_id: str,
    run_attempt: int | None,
    run_execution_id: str | None,
    published: bool,
) -> RunPublishResponse:
    package = get_report_package(db=db, report_run_id=report_run.id)
    artifacts = list_run_artifacts(db=db, report_run_id=report_run.id)
    report_pdf = next(
        (artifact for artifact in artifacts if artifact.artifact_type == REPORT_PDF_ARTIFACT_TYPE),
        None,
    )
    return RunPublishResponse(
        schema_version=PUBLISH_GATE_SCHEMA_VERSION,
        run_id=run_id,
        run_attempt=run_attempt,
        run_execution_id=run_execution_id,
        report_run_status=report_run.status,
        publish_ready=report_run.publish_ready,
        published=published,
        blocked=False,
        blockers=[],
        package_job_id=package.id if package is not None else None,
        package_status=package.status if package is not None else report_run.package_status,
        estimated_stage=package.current_stage if package is not None else report_run.package_status,
        artifacts=[_to_report_artifact_response(artifact) for artifact in artifacts],
        report_pdf=_to_report_artifact_response(report_pdf) if report_pdf is not None else None,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )


VERIFICATION_AUDIT_SCHEMA_VERSION = "verification_audit_v1"
PUBLISH_GATE_SCHEMA_VERSION = "publish_gate_v1"
VERIFIER_VERSION = "v1"


def _detect_numeric_claim(statement: str) -> bool:
    return bool(re.search(r"\d", statement))


def _make_publish_blocker(
    *,
    code: str,
    message: str,
    count: int | None = None,
    sample_claim_ids: list[str] | None = None,
) -> RunPublishBlocker:
    return RunPublishBlocker(
        code=code,
        message=message,
        count=count,
        sample_claim_ids=sample_claim_ids or [],
    )


def _evaluate_publish_gate(
    *,
    db: Session,
    report_run: ReportRun,
) -> tuple[list[RunPublishBlocker], int | None, str | None]:
    blockers: list[RunPublishBlocker] = []
    if not report_run.publish_ready:
        blockers.append(
            _make_publish_blocker(
                code="WORKFLOW_NOT_PUBLISH_READY",
                message="Run workflow has not been marked publish_ready.",
            )
        )
    if report_run.status not in {"completed", "published"}:
        blockers.append(
            _make_publish_blocker(
                code="RUN_STATUS_NOT_COMPLETED",
                message="Run status must be completed before publish.",
            )
        )

    latest_attempt_raw = db.scalar(
        select(func.max(VerificationResult.run_attempt)).where(
            VerificationResult.report_run_id == report_run.id,
        )
    )
    run_attempt = int(latest_attempt_raw or 0)
    if run_attempt <= 0:
        blockers.append(
            _make_publish_blocker(
                code="MISSING_VERIFICATION_RESULTS",
                message="No persisted verification results found for run.",
            )
        )
        return blockers, None, None

    run_execution_id = db.scalar(
        select(VerificationResult.run_execution_id)
        .where(
            VerificationResult.report_run_id == report_run.id,
            VerificationResult.run_attempt == run_attempt,
        )
        .order_by(VerificationResult.checked_at.desc(), VerificationResult.id.desc())
        .limit(1)
    )

    verification_counts = db.execute(
        select(
            func.count(VerificationResult.id),
            func.coalesce(
                func.sum(case((VerificationResult.status == "PASS", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((VerificationResult.status == "FAIL", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((VerificationResult.status == "UNSURE", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                VerificationResult.status == "FAIL",
                                VerificationResult.severity == "critical",
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .where(
            VerificationResult.report_run_id == report_run.id,
            VerificationResult.run_attempt == run_attempt,
        )
    ).one()
    total_claims = int(verification_counts[0] or 0)
    fail_count = int(verification_counts[2] or 0)
    unsure_count = int(verification_counts[3] or 0)
    critical_fail_count = int(verification_counts[4] or 0)

    if total_claims <= 0:
        blockers.append(
            _make_publish_blocker(
                code="EMPTY_VERIFICATION_BATCH",
                message="Latest verification attempt has no claim results.",
            )
        )
        return blockers, run_attempt, run_execution_id

    if critical_fail_count > 0:
        blockers.append(
            _make_publish_blocker(
                code="CRITICAL_FAIL_CLAIMS",
                message="Critical FAIL claims must be resolved before publish.",
                count=critical_fail_count,
            )
        )
    if fail_count + unsure_count > 0:
        blockers.append(
            _make_publish_blocker(
                code="NON_PASS_CLAIMS_PRESENT",
                message="All claims must be PASS before publish.",
                count=fail_count + unsure_count,
            )
        )

    claim_rows = db.execute(
        select(Claim.id, Claim.statement)
        .join(VerificationResult, VerificationResult.claim_id == Claim.id)
        .where(
            VerificationResult.report_run_id == report_run.id,
            VerificationResult.run_attempt == run_attempt,
        )
    ).all()
    claim_ids = [str(row.id) for row in claim_rows]
    if not claim_ids:
        blockers.append(
            _make_publish_blocker(
                code="MISSING_CLAIM_REFERENCES",
                message="Verification rows are not linked to claims.",
            )
        )
        return blockers, run_attempt, run_execution_id

    cited_claim_ids = {
        str(claim_id)
        for claim_id in db.scalars(
            select(ClaimCitation.claim_id).where(ClaimCitation.claim_id.in_(claim_ids))
        )
    }
    missing_citation_claim_ids = [claim_id for claim_id in claim_ids if claim_id not in cited_claim_ids]
    if missing_citation_claim_ids:
        blockers.append(
            _make_publish_blocker(
                code="MISSING_CITATIONS_FOR_CLAIMS",
                message="Each claim must include at least one persisted citation.",
                count=len(missing_citation_claim_ids),
                sample_claim_ids=missing_citation_claim_ids[:10],
            )
        )

    numeric_claim_ids = [
        str(row.id)
        for row in claim_rows
        if _detect_numeric_claim(str(row.statement or ""))
    ]
    if numeric_claim_ids:
        calc_claim_ids = {
            str(claim_id)
            for claim_id in db.scalars(
                select(CalculationRun.claim_id).where(
                    CalculationRun.report_run_id == report_run.id,
                    CalculationRun.claim_id.in_(numeric_claim_ids),
                    CalculationRun.status.in_(("completed", "success")),
                )
            )
            if claim_id is not None
        }
        missing_calc_claim_ids = [claim_id for claim_id in numeric_claim_ids if claim_id not in calc_claim_ids]
        if missing_calc_claim_ids:
            blockers.append(
                _make_publish_blocker(
                    code="MISSING_CALCULATOR_ARTIFACTS",
                    message="Numeric claims require persisted calculator artifacts.",
                    count=len(missing_calc_claim_ids),
                    sample_claim_ids=missing_calc_claim_ids[:10],
                )
            )

    return blockers, run_attempt, run_execution_id


def _get_latest_run_execution_context(
    *,
    db: Session,
    report_run_id: str,
) -> tuple[int | None, str | None]:
    run_attempt = db.scalar(
        select(func.max(VerificationResult.run_attempt)).where(
            VerificationResult.report_run_id == report_run_id,
        )
    )
    run_execution_id = None
    if isinstance(run_attempt, int) and run_attempt > 0:
        run_execution_id = db.scalar(
            select(VerificationResult.run_execution_id)
            .where(
                VerificationResult.report_run_id == report_run_id,
                VerificationResult.run_attempt == run_attempt,
            )
            .order_by(VerificationResult.checked_at.desc(), VerificationResult.id.desc())
            .limit(1)
        )
    return (int(run_attempt) if isinstance(run_attempt, int) and run_attempt > 0 else None, run_execution_id)


def _record_publish_failure(
    *,
    db: Session,
    report_run: ReportRun,
    run_id: str,
    run_attempt: int | None,
    run_execution_id: str | None,
    published: bool,
    exc: Exception,
) -> None:
    failure_payload = {
        "schema_version": PUBLISH_GATE_SCHEMA_VERSION,
        "run_id": run_id,
        "blocked": False,
        "published": published,
        "run_attempt": run_attempt,
        "run_execution_id": run_execution_id,
        "error_code": "REPORT_PACKAGE_GENERATION_FAILED",
        "reason": str(exc),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    db.add(
        AuditEvent(
            tenant_id=report_run.tenant_id,
            project_id=report_run.project_id,
            report_run_id=report_run.id,
            event_type="publish",
            event_name="publish_failed",
            event_payload=failure_payload,
        )
    )
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=failure_payload,
    ) from exc


def _resolve_run_attempt(
    *,
    db: Session,
    report_run_id: str,
    run_execution_id: str,
) -> int:
    existing_attempt = db.scalar(
        select(VerificationResult.run_attempt).where(
            VerificationResult.report_run_id == report_run_id,
            VerificationResult.run_execution_id == run_execution_id,
        )
    )
    if isinstance(existing_attempt, int) and existing_attempt > 0:
        return existing_attempt

    max_attempt = db.scalar(
        select(func.max(VerificationResult.run_attempt)).where(
            VerificationResult.report_run_id == report_run_id,
        )
    )
    return int(max_attempt or 0) + 1


def _build_verification_audit_payload(
    *,
    report_run: ReportRun,
    run_execution_id: str,
    run_attempt: int,
    triage_required: bool,
    verification_stats: dict[str, int],
) -> dict:
    pass_count = int(verification_stats.get("pass_count", 0))
    fail_count = int(verification_stats.get("fail_count", 0))
    unsure_count = int(verification_stats.get("unsure_count", 0))
    critical_fail_count = int(verification_stats.get("critical_fail_count", 0))
    total_claims = pass_count + fail_count + unsure_count
    return {
        "schema_version": VERIFICATION_AUDIT_SCHEMA_VERSION,
        "run_id": report_run.id,
        "report_run_id": report_run.id,
        "run_execution_id": run_execution_id,
        "run_attempt": run_attempt,
        "triage_required": triage_required,
        "summary": {
            "total_claims": total_claims,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "unsure_count": unsure_count,
            "critical_fail_count": critical_fail_count,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _persist_verification_artifacts(
    *,
    db: Session,
    report_run: ReportRun,
    state: dict,
    run_execution_id: str,
    run_attempt: int,
    verifier_version: str,
) -> dict[str, int]:
    draft_pool = state.get("draft_pool", [])
    verification_pool = state.get("verification_pool", [])
    calculation_pool = state.get("calculation_pool", [])
    if not isinstance(draft_pool, list) or not isinstance(verification_pool, list):
        return {
            "persisted_claims": 0,
            "persisted_calculations": 0,
            "pass_count": 0,
            "fail_count": 0,
            "unsure_count": 0,
            "critical_fail_count": 0,
        }
    if not isinstance(calculation_pool, list):
        calculation_pool = []

    section_lookup: dict[str, ReportSection] = {}
    existing_sections = (
        db.query(ReportSection)
        .filter(ReportSection.report_run_id == report_run.id)
        .all()
    )
    for section in existing_sections:
        section_lookup[section.section_code] = section

    verification_by_claim_id: dict[str, dict] = {}
    for row in verification_pool:
        if isinstance(row, dict):
            key = str(row.get("claim_id", "")).strip()
            if key:
                verification_by_claim_id[key] = row

    source_document_cache: dict[str, bool] = {}
    chunk_cache: dict[str, bool] = {}

    persisted_claims = 0
    persisted_calculations = 0
    pass_count = 0
    fail_count = 0
    unsure_count = 0
    critical_fail_count = 0
    calculation_by_external_id: dict[str, dict] = {}
    calculation_refs_by_claim_id: dict[str, set[str]] = {}

    for calc_item in calculation_pool:
        if not isinstance(calc_item, dict):
            continue
        external_calc_id = str(calc_item.get("calc_id", "")).strip()
        if external_calc_id:
            calculation_by_external_id[external_calc_id] = calc_item

    for section_idx, draft in enumerate(draft_pool):
        if not isinstance(draft, dict):
            continue

        section_code = str(draft.get("section_code", "")).strip() or f"SECTION_{section_idx}"
        section = section_lookup.get(section_code)
        if section is None:
            section = ReportSection(
                report_run_id=report_run.id,
                section_code=section_code,
                title=section_code,
                status="draft",
                ordinal=section_idx,
            )
            db.add(section)
            db.flush()
            section_lookup[section_code] = section

        claims = draft.get("claims", [])
        if not isinstance(claims, list):
            continue

        for claim_payload in claims:
            if not isinstance(claim_payload, dict):
                continue
            external_claim_id = str(claim_payload.get("claim_id", "")).strip()
            statement = str(claim_payload.get("statement", "") or "").strip()
            if not statement:
                continue

            claim_row = (
                db.query(Claim)
                .filter(
                    Claim.report_section_id == section.id,
                    Claim.statement == statement,
                )
                .first()
            )
            if claim_row is None:
                claim_row = Claim(
                    report_section_id=section.id,
                    statement=statement,
                    status="draft",
                )
                db.add(claim_row)
                db.flush()

            verification = verification_by_claim_id.get(external_claim_id, {})
            verification_status = str(verification.get("status", "UNSURE")).upper()
            verification_reason = str(verification.get("reason", "verification_not_available"))
            verification_severity = str(verification.get("severity", "normal"))
            confidence_raw = verification.get("confidence")
            confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else None

            claim_row.status = verification_status.lower()
            claim_row.confidence = confidence

            raw_calc_refs = claim_payload.get("calculation_refs", [])
            if isinstance(raw_calc_refs, list):
                for raw_ref in raw_calc_refs:
                    calc_ref = str(raw_ref).strip()
                    if calc_ref:
                        refs = calculation_refs_by_claim_id.setdefault(claim_row.id, set())
                        refs.add(calc_ref)

            if verification_status == "PASS":
                pass_count += 1
            elif verification_status == "FAIL":
                fail_count += 1
                if verification_severity == "critical":
                    critical_fail_count += 1
            elif verification_status == "UNSURE":
                unsure_count += 1

            verification_row = (
                db.query(VerificationResult)
                .filter(
                    VerificationResult.claim_id == claim_row.id,
                    VerificationResult.run_execution_id == run_execution_id,
                )
                .first()
            )
            if verification_row is None:
                verification_row = VerificationResult(
                    report_run_id=report_run.id,
                    claim_id=claim_row.id,
                    run_execution_id=run_execution_id,
                    run_attempt=run_attempt,
                    verifier_version=verifier_version,
                    status=verification_status,
                    reason=verification_reason,
                    severity=verification_severity,
                    confidence=confidence,
                )
                db.add(verification_row)
            else:
                verification_row.report_run_id = report_run.id
                verification_row.run_attempt = run_attempt
                verification_row.verifier_version = verifier_version
                verification_row.status = verification_status
                verification_row.reason = verification_reason
                verification_row.severity = verification_severity
                verification_row.confidence = confidence
                verification_row.checked_at = datetime.now(timezone.utc)

            citations = claim_payload.get("citations", [])
            if isinstance(citations, list):
                for citation in citations:
                    if not isinstance(citation, dict):
                        continue
                    source_document_id = str(citation.get("source_document_id", "")).strip()
                    chunk_id = str(citation.get("chunk_id", "")).strip()
                    if not source_document_id or not chunk_id:
                        continue

                    if source_document_id not in source_document_cache:
                        source_document_cache[source_document_id] = (
                            db.get(SourceDocument, source_document_id) is not None
                        )
                    if not source_document_cache[source_document_id]:
                        continue

                    if chunk_id not in chunk_cache:
                        chunk_cache[chunk_id] = db.get(Chunk, chunk_id) is not None
                    if not chunk_cache[chunk_id]:
                        continue

                    span_start_raw = citation.get("span_start", 0)
                    span_end_raw = citation.get("span_end", 0)
                    span_start = int(span_start_raw) if isinstance(span_start_raw, (int, float)) else 0
                    span_end = int(span_end_raw) if isinstance(span_end_raw, (int, float)) else max(span_start + 1, 1)

                    existing_citation = (
                        db.query(ClaimCitation)
                        .filter(
                            ClaimCitation.claim_id == claim_row.id,
                            ClaimCitation.chunk_id == chunk_id,
                            ClaimCitation.span_start == span_start,
                            ClaimCitation.span_end == span_end,
                        )
                        .first()
                    )
                    if existing_citation is None:
                        db.add(
                            ClaimCitation(
                                claim_id=claim_row.id,
                                source_document_id=source_document_id,
                                chunk_id=chunk_id,
                                span_start=span_start,
                                span_end=span_end,
                            )
                        )

            persisted_claims += 1

    for claim_id, external_calc_ids in calculation_refs_by_claim_id.items():
        for external_calc_id in sorted(external_calc_ids):
            calc_item = calculation_by_external_id.get(external_calc_id)
            if calc_item is None:
                continue

            formula_name = str(calc_item.get("formula_name", "unknown_formula")).strip() or "unknown_formula"
            code_hash = str(calc_item.get("code_hash", "")).strip() or "sha256:unknown"
            inputs_ref = str(calc_item.get("inputs_ref", "")).strip() or f"state://{report_run.id}/unknown"
            output_unit = str(calc_item.get("output_unit", "")).strip() or None
            trace_log_ref = str(calc_item.get("trace_log_ref", "")).strip() or None
            status_value = str(calc_item.get("status", "completed")).strip().lower() or "completed"
            output_raw = calc_item.get("output_value")
            output_value = float(output_raw) if isinstance(output_raw, (int, float)) else None

            calculation_row = (
                db.query(CalculationRun)
                .filter(
                    CalculationRun.report_run_id == report_run.id,
                    CalculationRun.claim_id == claim_id,
                    CalculationRun.formula_name == formula_name,
                    CalculationRun.code_hash == code_hash,
                    CalculationRun.inputs_ref == inputs_ref,
                )
                .first()
            )
            if calculation_row is None:
                calculation_row = CalculationRun(
                    report_run_id=report_run.id,
                    claim_id=claim_id,
                    formula_name=formula_name,
                    code_hash=code_hash,
                    inputs_ref=inputs_ref,
                    output_value=output_value,
                    output_unit=output_unit,
                    trace_log_ref=trace_log_ref,
                    status=status_value,
                )
                db.add(calculation_row)
            else:
                calculation_row.output_value = output_value
                calculation_row.output_unit = output_unit
                calculation_row.trace_log_ref = trace_log_ref
                calculation_row.status = status_value
                calculation_row.executed_at = datetime.now(timezone.utc)
            persisted_calculations += 1

    return {
        "persisted_claims": persisted_claims,
        "persisted_calculations": persisted_calculations,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "unsure_count": unsure_count,
        "critical_fail_count": critical_fail_count,
        "run_attempt": run_attempt,
    }


@router.post("", response_model=RunStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreateRequest,
    user: CurrentUser = Depends(
        require_roles(*RUN_MUTATION_ROLES)
    ),
    db: Session = Depends(get_db),
) -> RunStatusResponse:
    _ = user
    tenant = db.scalar(select(Tenant).where(Tenant.id == payload.tenant_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    project = db.scalar(
        select(Project).where(
            Project.id == payload.project_id,
            Project.tenant_id == payload.tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")

    company_profile, brand_kit, blueprint = _resolve_report_factory_context(
        db=db,
        tenant=tenant,
        project=project,
        payload=payload,
    )
    now = datetime.now(timezone.utc)
    report_run = ReportRun(
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        company_profile_id=company_profile.id,
        brand_kit_id=brand_kit.id,
        status="running",
        started_at=now,
        publish_ready=False,
        report_blueprint_version=blueprint.version,
        connector_scope=payload.connector_scope or ["sap_odata", "logo_tiger_sql_view", "netsis_rest"],
        package_status="not_started",
        visual_generation_status="not_started",
    )
    db.add(report_run)
    db.commit()
    db.refresh(report_run)

    checkpoint_store = get_checkpoint_store()
    state = initialize_workflow(
        run_id=report_run.id,
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        framework_target=payload.framework_target,
        active_reg_pack_version=payload.active_reg_pack_version,
        scope_decision=payload.scope_decision,
        checkpoint_store=checkpoint_store,
    )
    latest = checkpoint_store.load_latest_checkpoint(run_id=report_run.id)
    if latest is None:
        raise HTTPException(status_code=500, detail="Checkpoint initialization failed.")
    return _build_run_status_response(db=db, report_run=report_run, checkpoint=latest)


@router.post("/{run_id}/advance", response_model=RunStatusResponse, status_code=status.HTTP_200_OK)
async def advance_run(
    run_id: str,
    payload: RunAdvanceRequest,
    user: CurrentUser = Depends(
        require_roles(*RUN_MUTATION_ROLES)
    ),
    db: Session = Depends(get_db),
) -> RunStatusResponse:
    _ = user
    report_run = db.scalar(
        select(ReportRun).where(
            ReportRun.id == run_id,
            ReportRun.tenant_id == payload.tenant_id,
            ReportRun.project_id == payload.project_id,
        )
    )
    if report_run is None:
        raise HTTPException(status_code=404, detail="Run not found for tenant/project.")

    checkpoint_store = get_checkpoint_store()
    latest = checkpoint_store.load_latest_checkpoint(run_id=run_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No checkpoint found for run.")

    state = latest["state"]
    if payload.success:
        transition = transition_success(
            state=state,
            checkpoint_store=checkpoint_store,
            metadata=payload.metadata or None,
        )
        if transition.node == "CLOSE_RUN":
            report_run.status = "completed"
            report_run.completed_at = datetime.now(timezone.utc)
        else:
            report_run.status = "running"
    else:
        transition_failure(
            state=state,
            checkpoint_store=checkpoint_store,
            reason=str(payload.failure_reason),
        )
        report_run.status = "failed"

    report_run.publish_ready = bool(state.get("publish_ready", False))
    db.commit()
    db.refresh(report_run)

    latest_after = checkpoint_store.load_latest_checkpoint(run_id=run_id)
    if latest_after is None:
        raise HTTPException(status_code=500, detail="Checkpoint update failed.")
    return _build_run_status_response(db=db, report_run=report_run, checkpoint=latest_after)


@router.post("/{run_id}/execute", response_model=RunExecuteResponse, status_code=status.HTTP_200_OK)
async def execute_run(
    run_id: str,
    payload: RunExecuteRequest,
    user: CurrentUser = Depends(
        require_roles(*RUN_MUTATION_ROLES)
    ),
    db: Session = Depends(get_db),
) -> RunExecuteResponse:
    _ = user
    report_run = db.scalar(
        select(ReportRun).where(
            ReportRun.id == run_id,
            ReportRun.tenant_id == payload.tenant_id,
            ReportRun.project_id == payload.project_id,
        )
    )
    if report_run is None:
        raise HTTPException(status_code=404, detail="Run not found for tenant/project.")

    checkpoint_store = get_checkpoint_store()
    latest = checkpoint_store.load_latest_checkpoint(run_id=run_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No checkpoint found for run.")

    state = latest["state"]
    if payload.human_approval_override is not None:
        state["human_approval"] = payload.human_approval_override

    outcome = execute_workflow(
        state=state,
        checkpoint_store=checkpoint_store,
        max_steps=payload.max_steps or settings.workflow_execute_max_steps,
        retry_budget_by_node=payload.retry_budget_by_node or None,
    )

    triage_required = bool(state.get("approval_status_board", {}).get("triage_required"))
    report_run.status = _resolve_report_run_status_from_stop_reason(
        stop_reason=outcome.stop_reason,
        triage_required=triage_required,
    )
    if report_run.status == "completed":
        report_run.completed_at = datetime.now(timezone.utc)
    report_run.publish_ready = bool(state.get("publish_ready", False))

    run_execution_id = str(outcome.last_checkpoint.get("checkpoint_id", "")).strip() or f"exec_{report_run.id}"
    run_attempt = _resolve_run_attempt(
        db=db,
        report_run_id=report_run.id,
        run_execution_id=run_execution_id,
    )
    verification_stats = _persist_verification_artifacts(
        db=db,
        report_run=report_run,
        state=state,
        run_execution_id=run_execution_id,
        run_attempt=run_attempt,
        verifier_version=VERIFIER_VERSION,
    )
    audit_payload = _build_verification_audit_payload(
        report_run=report_run,
        run_execution_id=run_execution_id,
        run_attempt=run_attempt,
        triage_required=triage_required,
        verification_stats=verification_stats,
    )
    db.add(
        AuditEvent(
            tenant_id=report_run.tenant_id,
            project_id=report_run.project_id,
            report_run_id=report_run.id,
            event_type="verification",
            event_name="verification_results_persisted",
            event_payload=audit_payload,
        )
    )
    if triage_required:
        triage_payload = {
            **audit_payload,
            "triage": {
                "required": True,
                "fail_count": verification_stats.get("fail_count", 0),
                "unsure_count": verification_stats.get("unsure_count", 0),
                "critical_fail_count": verification_stats.get("critical_fail_count", 0),
            },
        }
        db.add(
            AuditEvent(
                tenant_id=report_run.tenant_id,
                project_id=report_run.project_id,
                report_run_id=report_run.id,
                event_type="verification",
                event_name="verification_triage_required",
                event_payload=triage_payload,
            )
        )

    db.commit()
    db.refresh(report_run)

    status_payload = _build_run_status_response(db=db, report_run=report_run, checkpoint=outcome.last_checkpoint)
    return RunExecuteResponse(
        **status_payload.model_dump(),
        executed_steps=outcome.executed_steps,
        stop_reason=outcome.stop_reason,
        compensation_applied=outcome.compensation_applied,
        invalidated_fields=outcome.invalidated_fields,
        escalation_required=outcome.escalation_required,
    )


@router.post("/{run_id}/publish", response_model=RunPublishResponse, status_code=status.HTTP_200_OK)
async def publish_run(
    run_id: str,
    payload: RunPublishRequest,
    user: CurrentUser = Depends(require_roles(*RUN_PUBLISH_ROLES)),
    queue: JobQueueService = Depends(get_job_queue_service),
    db: Session = Depends(get_db),
) -> RunPublishResponse:
    _ = user
    report_run = db.scalar(
        select(ReportRun).where(
            ReportRun.id == run_id,
            ReportRun.tenant_id == payload.tenant_id,
            ReportRun.project_id == payload.project_id,
        )
    )
    if report_run is None:
        raise HTTPException(status_code=404, detail="Run not found for tenant/project.")

    run_attempt, run_execution_id = _get_latest_run_execution_context(db=db, report_run_id=report_run.id)
    current_package = get_report_package(db=db, report_run_id=report_run.id)
    if report_run.status == "published" and current_package is not None and current_package.status == "completed":
        return _build_run_publish_response(
            db=db,
            report_run=report_run,
            run_id=run_id,
            run_attempt=run_attempt,
            run_execution_id=run_execution_id,
            published=True,
        )

    if report_run.status != "published":
        blockers, run_attempt, run_execution_id = _evaluate_publish_gate(db=db, report_run=report_run)
        if blockers:
            detail_payload = {
                "schema_version": PUBLISH_GATE_SCHEMA_VERSION,
                "run_id": run_id,
                "blocked": True,
                "run_attempt": run_attempt,
                "run_execution_id": run_execution_id,
                "blockers": [item.model_dump() for item in blockers],
                "report_pdf": None,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            db.add(
                AuditEvent(
                    tenant_id=report_run.tenant_id,
                    project_id=report_run.project_id,
                    report_run_id=report_run.id,
                    event_type="publish",
                    event_name="publish_blocked",
                    event_payload=detail_payload,
                )
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail_payload,
            )

    try:
        package = ensure_report_package_record(db=db, report_run=report_run)
        db.commit()
        await queue.enqueue_report_package(report_run.id, package_job_id=package.id)
    except Exception as exc:
        package = get_report_package(db=db, report_run_id=report_run.id)
        if package is not None:
            package.status = "failed"
            package.error_message = str(exc)
            package.completed_at = datetime.now(timezone.utc)
        report_run.package_status = "failed"
        db.flush()
        _record_publish_failure(
            db=db,
            report_run=report_run,
            run_id=run_id,
            run_attempt=run_attempt,
            run_execution_id=run_execution_id,
            published=False,
            exc=exc,
        )

    package = get_report_package(db=db, report_run_id=report_run.id)
    success_payload = {
        "schema_version": PUBLISH_GATE_SCHEMA_VERSION,
        "run_id": run_id,
        "blocked": False,
        "published": False,
        "run_attempt": run_attempt,
        "run_execution_id": run_execution_id,
        "package_job_id": package.id if package is not None else None,
        "package_status": package.status if package is not None else report_run.package_status,
        "estimated_stage": package.current_stage if package is not None else report_run.package_status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    db.add(
        AuditEvent(
            tenant_id=report_run.tenant_id,
            project_id=report_run.project_id,
            report_run_id=report_run.id,
            event_type="publish",
            event_name="publish_queued",
            event_payload=success_payload,
        )
    )
    db.commit()
    db.refresh(report_run)

    queued_package = get_report_package(db=db, report_run_id=report_run.id)
    return _build_run_publish_response(
        db=db,
        report_run=report_run,
        run_id=run_id,
        run_attempt=run_attempt,
        run_execution_id=run_execution_id,
        published=bool(queued_package is not None and queued_package.status == "completed" and report_run.status == "published"),
    )


@router.get(
    "/{run_id}/package-status",
    response_model=RunPackageStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_run_package_status(
    run_id: str,
    tenant_id: str,
    project_id: str,
    user: CurrentUser = Depends(require_roles(*RUN_READ_ROLES)),
    db: Session = Depends(get_db),
) -> RunPackageStatusResponse:
    _ = user
    report_run = db.scalar(
        select(ReportRun).where(
            ReportRun.id == run_id,
            ReportRun.tenant_id == tenant_id,
            ReportRun.project_id == project_id,
        )
    )
    if report_run is None:
        raise HTTPException(status_code=404, detail="Run not found for tenant/project.")
    return RunPackageStatusResponse(**build_package_status_payload(db=db, report_run=report_run))


@router.get(
    "/{run_id}/artifacts/{artifact_id}",
    status_code=status.HTTP_200_OK,
)
async def download_run_artifact(
    run_id: str,
    artifact_id: str,
    tenant_id: str,
    project_id: str,
    user: CurrentUser = Depends(require_roles(*RUN_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    _ = user
    report_run = db.scalar(
        select(ReportRun).where(
            ReportRun.id == run_id,
            ReportRun.tenant_id == tenant_id,
            ReportRun.project_id == project_id,
        )
    )
    if report_run is None:
        raise HTTPException(status_code=404, detail="Run not found for tenant/project.")

    artifact = get_report_artifact_by_id(db=db, report_run_id=report_run.id, artifact_id=artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found for run.")

    try:
        payload = download_report_artifact_bytes(artifact)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load report artifact. {exc}",
        ) from exc

    return Response(
        content=payload,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get(
    "/{run_id}/report-pdf",
    status_code=status.HTTP_200_OK,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_run_report_pdf(
    run_id: str,
    tenant_id: str,
    project_id: str,
    user: CurrentUser = Depends(require_roles(*RUN_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Response:
    _ = user
    report_run = db.scalar(
        select(ReportRun).where(
            ReportRun.id == run_id,
            ReportRun.tenant_id == tenant_id,
            ReportRun.project_id == project_id,
        )
    )
    if report_run is None:
        raise HTTPException(status_code=404, detail="Run not found for tenant/project.")

    artifact = next(
        (
            item
            for item in list_run_artifacts(db=db, report_run_id=report_run.id)
            if item.artifact_type == REPORT_PDF_ARTIFACT_TYPE
        ),
        None,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="Published report PDF not found for run.")

    try:
        payload = download_report_artifact_bytes(artifact)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load report PDF artifact. {exc}",
        ) from exc

    return Response(
        content=payload,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Content-Length": str(len(payload)),
        },
    )


@router.get("/{run_id}/triage-report", response_model=RunTriageReportResponse, status_code=status.HTTP_200_OK)
async def get_run_triage_report(
    run_id: str,
    tenant_id: str,
    project_id: str,
    status_filter: Literal["FAIL", "UNSURE"] | None = Query(default=None),
    section_code: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(
        require_roles(*RUN_READ_ROLES)
    ),
    db: Session = Depends(get_db),
) -> RunTriageReportResponse:
    _ = user
    report_run = db.scalar(
        select(ReportRun).where(
            ReportRun.id == run_id,
            ReportRun.tenant_id == tenant_id,
            ReportRun.project_id == project_id,
        )
    )
    if report_run is None:
        raise HTTPException(status_code=404, detail="Run not found for tenant/project.")

    latest_attempt = db.scalar(
        select(func.max(VerificationResult.run_attempt)).where(
            VerificationResult.report_run_id == run_id,
        )
    )
    run_attempt = int(latest_attempt or 0)
    run_execution_id: str | None = None
    if run_attempt > 0:
        run_execution_id = db.scalar(
            select(VerificationResult.run_execution_id)
            .where(
                VerificationResult.report_run_id == run_id,
                VerificationResult.run_attempt == run_attempt,
            )
            .order_by(VerificationResult.checked_at.desc(), VerificationResult.id.desc())
            .limit(1)
        )
    section_code_filter = section_code.strip() if section_code and section_code.strip() else None

    fail_count = 0
    unsure_count = 0
    critical_fail_count = 0
    total_items = 0
    items: list[RunTriageItem] = []

    if run_attempt > 0:
        filters = [
            VerificationResult.report_run_id == run_id,
            VerificationResult.run_attempt == run_attempt,
            VerificationResult.status.in_(("FAIL", "UNSURE")),
        ]
        if status_filter is not None:
            filters.append(VerificationResult.status == status_filter)
        if section_code_filter is not None:
            filters.append(ReportSection.section_code == section_code_filter)

        counts_row = db.execute(
            select(
                func.count(VerificationResult.id),
                func.coalesce(
                    func.sum(case((VerificationResult.status == "FAIL", 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((VerificationResult.status == "UNSURE", 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    VerificationResult.status == "FAIL",
                                    VerificationResult.severity == "critical",
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .select_from(VerificationResult)
            .join(Claim, Claim.id == VerificationResult.claim_id)
            .join(ReportSection, ReportSection.id == Claim.report_section_id)
            .where(*filters)
        ).one()

        total_items = int(counts_row[0] or 0)
        fail_count = int(counts_row[1] or 0)
        unsure_count = int(counts_row[2] or 0)
        critical_fail_count = int(counts_row[3] or 0)

        start_idx = (page - 1) * size
        item_rows = db.execute(
            select(
                VerificationResult.claim_id,
                VerificationResult.status,
                VerificationResult.severity,
                VerificationResult.reason,
                VerificationResult.confidence,
                ReportSection.section_code,
            )
            .select_from(VerificationResult)
            .join(Claim, Claim.id == VerificationResult.claim_id)
            .join(ReportSection, ReportSection.id == Claim.report_section_id)
            .where(*filters)
            .order_by(VerificationResult.checked_at.desc(), VerificationResult.id.desc())
            .offset(start_idx)
            .limit(size)
        ).all()

        claim_ids = [str(row.claim_id) for row in item_rows]
        citation_map: dict[str, list[str]] = {}
        if claim_ids:
            citation_rows = db.execute(
                select(ClaimCitation.claim_id, ClaimCitation.chunk_id).where(
                    ClaimCitation.claim_id.in_(claim_ids),
                )
            ).all()
            for citation in citation_rows:
                claim_id = str(citation.claim_id)
                chunk_id = str(citation.chunk_id)
                refs = citation_map.setdefault(claim_id, [])
                if chunk_id not in refs:
                    refs.append(chunk_id)

        for row in item_rows:
            claim_id = str(row.claim_id)
            status_value = str(row.status).upper()
            confidence_raw = row.confidence
            confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else None
            items.append(
                RunTriageItem(
                    section_code=str(row.section_code),
                    claim_id=claim_id,
                    status=status_value,  # type: ignore[arg-type]
                    severity=str(row.severity),
                    reason=str(row.reason),
                    confidence=confidence,
                    evidence_refs=citation_map.get(claim_id, []),
                )
            )

    triage_required = report_run.status == "triage_required" or fail_count > 0 or unsure_count > 0
    return RunTriageReportResponse(
        schema_version=VERIFICATION_AUDIT_SCHEMA_VERSION,
        run_id=run_id,
        run_attempt=run_attempt if run_attempt > 0 else None,
        run_execution_id=run_execution_id,
        report_run_status=report_run.status,
        triage_required=triage_required,
        fail_count=fail_count,
        unsure_count=unsure_count,
        critical_fail_count=critical_fail_count,
        total_items=total_items,
        page=page,
        size=size,
        status_filter=status_filter,
        section_code_filter=section_code_filter,
        items=items,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )
