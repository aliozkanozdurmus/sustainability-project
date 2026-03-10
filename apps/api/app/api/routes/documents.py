from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import PurePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.core.settings import settings
from app.models.core import AuditEvent, Chunk, ExtractionRecord, Project, SourceDocument, Tenant, User
from app.schemas.auth import CurrentUser
from app.schemas.documents import (
    DocumentExtractionEnqueueResponse,
    DocumentExtractionRequest,
    DocumentExtractionResponse,
    DocumentExtractionStatusResponse,
    DocumentIndexStatusResponse,
    DocumentUploadResponse,
)
from app.db.session import get_db
from app.services.blob_storage import BlobStorageService, get_blob_storage_service
from app.services.document_intelligence import (
    DocumentIntelligenceService,
    get_document_intelligence_service,
)
from app.services.job_queue import JobQueueService, get_job_queue_service
from app.services.ocr_pipeline import run_ocr_extraction

router = APIRouter(prefix="/documents", tags=["documents"])


def _safe_filename(name: str) -> str:
    return PurePath(name).name.replace("\\", "_").replace("/", "_")


def _get_ocr_service_safe() -> DocumentIntelligenceService:
    try:
        return get_document_intelligence_service()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _load_source_document(
    *,
    db: Session,
    tenant_id: str,
    project_id: str,
    document_id: str,
) -> SourceDocument:
    source_document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.id == document_id,
            SourceDocument.tenant_id == tenant_id,
            SourceDocument.project_id == project_id,
        )
    )
    if source_document is None:
        raise HTTPException(status_code=404, detail="Document not found for tenant/project.")
    return source_document


def _append_queue_audit_event(
    *,
    db: Session,
    source_document: SourceDocument,
    user: CurrentUser,
    event_name: str,
    payload: dict | None = None,
) -> None:
    actor_user_id = db.scalar(select(User.id).where(User.id == user.user_id))
    db.add(
        AuditEvent(
            tenant_id=source_document.tenant_id,
            project_id=source_document.project_id,
            actor_user_id=actor_user_id,
            event_type="document_extraction_queue",
            event_name=event_name,
            event_payload=payload or {},
        )
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    tenant_id: str = Form(...),
    project_id: str = Form(...),
    document_type: str = Form(...),
    issued_at: datetime | None = Form(default=None),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_roles("admin", "compliance_manager", "analyst")),
    db: Session = Depends(get_db),
    blob_storage: BlobStorageService = Depends(get_blob_storage_service),
) -> DocumentUploadResponse:
    _ = user

    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found for tenant.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    checksum = hashlib.sha256(payload).hexdigest()
    safe_name = _safe_filename(file.filename or "upload.bin")
    blob_name = f"{tenant_id}/{project_id}/{uuid4()}_{safe_name}"
    storage_uri = blob_storage.upload_bytes(payload, blob_name, file.content_type)

    source_document = SourceDocument(
        tenant_id=tenant_id,
        project_id=project_id,
        document_type=document_type,
        filename=safe_name,
        storage_uri=storage_uri,
        checksum=checksum,
        mime_type=file.content_type,
        issued_at=issued_at,
        status="uploaded",
    )
    db.add(source_document)
    db.commit()
    db.refresh(source_document)

    return DocumentUploadResponse(
        document_id=source_document.id,
        tenant_id=source_document.tenant_id,
        project_id=source_document.project_id,
        filename=source_document.filename,
        document_type=source_document.document_type,
        storage_uri=source_document.storage_uri,
        checksum=source_document.checksum or "",
        mime_type=source_document.mime_type,
        status=source_document.status,
        ingested_at=source_document.ingested_at,
    )


@router.post(
    "/{document_id}/extract",
    response_model=DocumentExtractionResponse,
    status_code=status.HTTP_200_OK,
)
async def extract_document(
    document_id: str,
    payload: DocumentExtractionRequest,
    user: CurrentUser = Depends(require_roles("admin", "compliance_manager", "analyst")),
    db: Session = Depends(get_db),
    blob_storage: BlobStorageService = Depends(get_blob_storage_service),
    ocr_service: DocumentIntelligenceService = Depends(_get_ocr_service_safe),
) -> DocumentExtractionResponse:
    _ = user

    source_document = _load_source_document(
        db=db,
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        document_id=document_id,
    )

    try:
        outcome = run_ocr_extraction(
            db=db,
            source_document=source_document,
            blob_storage=blob_storage,
            ocr_service=ocr_service,
            extraction_mode=payload.extraction_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Document extraction failed.") from exc

    return DocumentExtractionResponse(
        extraction_id=outcome.extraction_id,
        source_document_id=outcome.source_document_id,
        status=outcome.status,
        provider=outcome.provider,
        quality_score=outcome.quality_score,
        extracted_text_uri=outcome.extracted_text_uri,
        raw_payload_uri=outcome.raw_payload_uri,
        chunk_count=outcome.chunk_count,
    )


@router.post(
    "/{document_id}/extract/queue",
    response_model=DocumentExtractionEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_document_extraction(
    document_id: str,
    payload: DocumentExtractionRequest,
    user: CurrentUser = Depends(require_roles("admin", "compliance_manager", "analyst")),
    db: Session = Depends(get_db),
    queue: JobQueueService = Depends(get_job_queue_service),
) -> DocumentExtractionEnqueueResponse:
    _ = user
    source_document = _load_source_document(
        db=db,
        tenant_id=payload.tenant_id,
        project_id=payload.project_id,
        document_id=document_id,
    )

    in_flight_extraction = db.scalar(
        select(ExtractionRecord)
        .where(
            ExtractionRecord.source_document_id == source_document.id,
            ExtractionRecord.status.in_(("queued", "processing", "pending", "retrying")),
        )
        .order_by(ExtractionRecord.created_at.desc())
    )
    if in_flight_extraction is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Extraction already in progress: {in_flight_extraction.id}",
        )

    extraction = ExtractionRecord(
        source_document_id=source_document.id,
        provider="azure_document_intelligence",
        extraction_mode=payload.extraction_mode,
        status="queued",
    )
    db.add(extraction)
    db.flush()
    source_document.status = "queued_for_extraction"
    _append_queue_audit_event(
        db=db,
        source_document=source_document,
        user=user,
        event_name="extraction_enqueued",
        payload={"extraction_id": extraction.id, "extraction_mode": payload.extraction_mode},
    )
    db.commit()
    db.refresh(extraction)

    try:
        queue_job_id = await queue.enqueue_extraction(extraction.id)
    except Exception as exc:
        extraction.status = "failed"
        extraction.error_message = "Failed to enqueue extraction job."
        source_document.status = "extraction_failed"
        _append_queue_audit_event(
            db=db,
            source_document=source_document,
            user=user,
            event_name="enqueue_failed",
            payload={"extraction_id": extraction.id},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to enqueue extraction job.",
        ) from exc

    return DocumentExtractionEnqueueResponse(
        extraction_id=extraction.id,
        source_document_id=source_document.id,
        status=extraction.status,
        queue_job_id=queue_job_id,
    )


@router.get(
    "/{document_id}/extractions/{extraction_id}",
    response_model=DocumentExtractionStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def read_document_extraction_status(
    document_id: str,
    extraction_id: str,
    tenant_id: str,
    project_id: str,
    user: CurrentUser = Depends(require_roles("admin", "compliance_manager", "analyst")),
    db: Session = Depends(get_db),
) -> DocumentExtractionStatusResponse:
    _ = user
    source_document = _load_source_document(
        db=db,
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
    )

    extraction = db.scalar(
        select(ExtractionRecord).where(
            ExtractionRecord.id == extraction_id,
            ExtractionRecord.source_document_id == source_document.id,
        )
    )
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction record not found for document.")

    chunk_count = db.scalar(
        select(func.count(Chunk.id)).where(Chunk.extraction_record_id == extraction.id)
    )

    return DocumentExtractionStatusResponse(
        extraction_id=extraction.id,
        source_document_id=source_document.id,
        status=extraction.status,
        provider=extraction.provider,
        extraction_mode=extraction.extraction_mode,
        quality_score=extraction.quality_score,
        chunk_count=int(chunk_count or 0),
        error_message=extraction.error_message,
        started_at=extraction.started_at,
        completed_at=extraction.completed_at,
    )


@router.get(
    "/{document_id}/extractions/{extraction_id}/index-status",
    response_model=DocumentIndexStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def read_document_index_status(
    document_id: str,
    extraction_id: str,
    tenant_id: str,
    project_id: str,
    user: CurrentUser = Depends(require_roles("admin", "compliance_manager", "analyst")),
    db: Session = Depends(get_db),
) -> DocumentIndexStatusResponse:
    _ = user
    source_document = _load_source_document(
        db=db,
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document_id,
    )

    extraction = db.scalar(
        select(ExtractionRecord).where(
            ExtractionRecord.id == extraction_id,
            ExtractionRecord.source_document_id == source_document.id,
        )
    )
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction record not found for document.")

    indexed_chunk_count = db.scalar(
        select(func.count(Chunk.id)).where(Chunk.extraction_record_id == extraction.id)
    )

    if extraction.status == "indexed":
        index_status = "completed"
    elif extraction.status == "indexing":
        index_status = "processing"
    elif extraction.status == "indexing_retrying":
        index_status = "retrying"
    elif extraction.status == "indexing_failed":
        index_status = "failed"
    else:
        index_status = "not_started"

    return DocumentIndexStatusResponse(
        extraction_id=extraction.id,
        source_document_id=source_document.id,
        status=index_status,
        index_provider="azure_ai_search",
        index_name=settings.azure_ai_search_index_name,
        indexed_chunk_count=int(indexed_chunk_count or 0),
        error_message=extraction.error_message,
    )
