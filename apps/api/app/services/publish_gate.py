from __future__ import annotations

import re

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.core import CalculationRun, Claim, ClaimCitation, ReportRun, VerificationResult
from app.schemas.runs import RunPublishBlocker


def detect_numeric_claim(statement: str) -> bool:
    return bool(re.search(r"\d", statement))


def make_publish_blocker(
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


def resolve_latest_run_execution_context(
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
    return (
        int(run_attempt) if isinstance(run_attempt, int) and run_attempt > 0 else None,
        run_execution_id,
    )


def evaluate_publish_gate(
    *,
    db: Session,
    report_run: ReportRun,
) -> tuple[list[RunPublishBlocker], int | None, str | None]:
    blockers: list[RunPublishBlocker] = []
    if not report_run.publish_ready:
        blockers.append(
            make_publish_blocker(
                code="WORKFLOW_NOT_PUBLISH_READY",
                message="Run workflow has not been marked publish_ready.",
            )
        )
    if report_run.status not in {"completed", "published"}:
        blockers.append(
            make_publish_blocker(
                code="RUN_STATUS_NOT_COMPLETED",
                message="Run status must be completed before publish.",
            )
        )

    run_attempt, run_execution_id = resolve_latest_run_execution_context(
        db=db,
        report_run_id=report_run.id,
    )
    if run_attempt is None:
        blockers.append(
            make_publish_blocker(
                code="MISSING_VERIFICATION_RESULTS",
                message="No persisted verification results found for run.",
            )
        )
        return blockers, None, None

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
            make_publish_blocker(
                code="EMPTY_VERIFICATION_BATCH",
                message="Latest verification attempt has no claim results.",
            )
        )
        return blockers, run_attempt, run_execution_id

    if critical_fail_count > 0:
        blockers.append(
            make_publish_blocker(
                code="CRITICAL_FAIL_CLAIMS",
                message="Critical FAIL claims must be resolved before publish.",
                count=critical_fail_count,
            )
        )
    if fail_count + unsure_count > 0:
        blockers.append(
            make_publish_blocker(
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
            make_publish_blocker(
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
            make_publish_blocker(
                code="MISSING_CITATIONS_FOR_CLAIMS",
                message="Each claim must include at least one persisted citation.",
                count=len(missing_citation_claim_ids),
                sample_claim_ids=missing_citation_claim_ids[:10],
            )
        )

    numeric_claim_ids = [
        str(row.id)
        for row in claim_rows
        if detect_numeric_claim(str(row.statement or ""))
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
                make_publish_blocker(
                    code="MISSING_CALCULATOR_ARTIFACTS",
                    message="Numeric claims require persisted calculator artifacts.",
                    count=len(missing_calc_claim_ids),
                    sample_claim_ids=missing_calc_claim_ids[:10],
                )
            )

    return blockers, run_attempt, run_execution_id
