# Bu route, retrieval uc noktasinin HTTP giris katmanini tanimlar.

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.models.core import Project, RetrievalRun, Tenant
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import RetrievalQueryRequest, RetrievalQueryResponse
from app.db.session import get_db
from app.services.retrieval import RetrievalQualityGateError, retrieve_evidence

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/query", response_model=RetrievalQueryResponse, status_code=status.HTTP_200_OK)
async def query_retrieval(
    payload: RetrievalQueryRequest,
    user: CurrentUser = Depends(
        require_roles("admin", "compliance_manager", "analyst", "auditor_readonly")
    ),
    db: Session = Depends(get_db),
) -> RetrievalQueryResponse:
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

    try:
        outcome = retrieve_evidence(
            tenant_id=payload.tenant_id,
            project_id=payload.project_id,
            query_text=payload.query_text,
            top_k=payload.top_k,
            retrieval_mode=payload.retrieval_mode,
            min_score=payload.min_score,
            min_coverage=payload.min_coverage,
            retrieval_hints=payload.retrieval_hints,
        )
    except RetrievalQualityGateError as exc:
        retrieval_run = RetrievalRun(
            tenant_id=payload.tenant_id,
            project_id=payload.project_id,
            query_text=payload.query_text,
            retrieval_mode=payload.retrieval_mode,
            top_k=payload.top_k,
            result_count=exc.diagnostics.result_count,
            latency_ms=exc.diagnostics.latency_ms,
            status="failed_quality_gate",
        )
        db.add(retrieval_run)
        db.commit()
        raise HTTPException(
            status_code=422,
            detail={
                "message": exc.reason,
                "diagnostics": exc.diagnostics.model_dump(),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Retrieval query failed.") from exc

    retrieval_run = RetrievalRun(
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        query_text=payload.query_text,
        retrieval_mode=payload.retrieval_mode,
        top_k=payload.top_k,
        result_count=outcome.diagnostics.result_count,
        latency_ms=outcome.diagnostics.latency_ms,
        status="completed",
    )
    db.add(retrieval_run)
    db.commit()
    db.refresh(retrieval_run)

    return RetrievalQueryResponse(
        retrieval_run_id=retrieval_run.id,
        evidence=outcome.evidence,
        diagnostics=outcome.diagnostics,
    )
