from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import AuditEvent, Chunk, ExtractionRecord, SourceDocument
from app.services.blob_storage import BlobStorageService
from app.services.document_intelligence import DocumentIntelligenceService, OcrResult

PROCESSABLE_STATUSES = ("queued", "pending", "retrying")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _quality_score(text: str) -> float:
    stripped = text.strip()
    if not stripped:
        return 0.0
    total = len(stripped)
    signal = sum(1 for ch in stripped if ch.isalnum())
    return round((signal / total) * 100.0, 2)


@dataclass
class OcrExtractionOutcome:
    extraction_id: str
    source_document_id: str
    status: str
    quality_score: float | None
    extracted_text_uri: str | None
    raw_payload_uri: str | None
    chunk_count: int
    provider: str


def _append_audit_event(
    *,
    db: Session,
    source_document: SourceDocument,
    event_name: str,
    payload: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            tenant_id=source_document.tenant_id,
            project_id=source_document.project_id,
            actor_user_id=None,
            event_type="document_extraction",
            event_name=event_name,
            event_payload=payload or {},
        )
    )


def _build_chunks(result: OcrResult) -> list[tuple[int | None, str]]:
    chunks: list[tuple[int | None, str]] = []
    for page in result.pages:
        page_text = page.text.strip()
        if page_text:
            chunks.append((page.page_number, page_text))

    if chunks:
        return chunks
    if result.full_text.strip():
        return [(None, result.full_text.strip())]
    return []


def _count_chunks(db: Session, extraction_id: str) -> int:
    count = db.scalar(
        select(func.count(Chunk.id)).where(Chunk.extraction_record_id == extraction_id)
    )
    return int(count or 0)


def _outcome_from_extraction(db: Session, extraction: ExtractionRecord) -> OcrExtractionOutcome:
    return OcrExtractionOutcome(
        extraction_id=extraction.id,
        source_document_id=extraction.source_document_id,
        status=extraction.status,
        quality_score=extraction.quality_score,
        extracted_text_uri=extraction.extracted_text_uri,
        raw_payload_uri=extraction.raw_payload_uri,
        chunk_count=_count_chunks(db, extraction.id),
        provider=extraction.provider,
    )


def _try_acquire_processing_lock(db: Session, extraction_id: str) -> bool:
    started_at = _now_utc()
    result = db.execute(
        update(ExtractionRecord)
        .where(
            ExtractionRecord.id == extraction_id,
            ExtractionRecord.status.in_(PROCESSABLE_STATUSES),
        )
        .values(
            status="processing",
            started_at=started_at,
            completed_at=None,
            error_message=None,
        )
    )
    db.commit()
    return bool(result.rowcount)


def _execute_extraction(
    *,
    db: Session,
    extraction: ExtractionRecord,
    source_document: SourceDocument,
    blob_storage: BlobStorageService,
    ocr_service: DocumentIntelligenceService,
    max_attempts: int,
) -> OcrExtractionOutcome:
    try:
        _append_audit_event(
            db=db,
            source_document=source_document,
            event_name="extraction_started",
            payload={"extraction_id": extraction.id},
        )
        db.commit()

        raw_document = blob_storage.download_bytes(source_document.storage_uri)

        attempts = 0
        last_error: Exception | None = None
        result: OcrResult | None = None
        while attempts < max_attempts:
            attempts += 1
            try:
                result = ocr_service.analyze_document(raw_document, source_document.mime_type)
                break
            except Exception as exc:  # pragma: no cover - exercised through final failure path
                last_error = exc

        if result is None:
            raise RuntimeError(f"OCR analysis failed after {max_attempts} attempts.") from last_error

        content_text = result.full_text.strip()
        if not content_text and result.pages:
            content_text = "\n\n".join(page.text.strip() for page in result.pages if page.text).strip()

        base_blob_name = (
            f"{source_document.tenant_id}/{source_document.project_id}/"
            f"{source_document.id}/{extraction.id}"
        )
        extracted_text_uri = blob_storage.upload_bytes(
            payload=content_text.encode("utf-8"),
            blob_name=f"{base_blob_name}/extracted.txt",
            content_type="text/plain; charset=utf-8",
            container=settings.azure_storage_container_parsed,
        )
        raw_payload_uri = blob_storage.upload_bytes(
            payload=json.dumps(result.raw_payload, ensure_ascii=True, indent=2).encode("utf-8"),
            blob_name=f"{base_blob_name}/raw-payload.json",
            content_type="application/json",
            container=settings.azure_storage_container_artifacts,
        )

        db.execute(delete(Chunk).where(Chunk.source_document_id == source_document.id))
        chunk_rows = _build_chunks(result)
        for idx, (page, text) in enumerate(chunk_rows):
            db.add(
                Chunk(
                    source_document_id=source_document.id,
                    extraction_record_id=extraction.id,
                    chunk_index=idx,
                    text=text,
                    page=page,
                    token_count=len(text.split()),
                )
            )

        extraction.status = "completed"
        extraction.completed_at = _now_utc()
        extraction.quality_score = _quality_score(content_text)
        extraction.extracted_text_uri = extracted_text_uri
        extraction.raw_payload_uri = raw_payload_uri
        extraction.error_message = None
        source_document.status = "extracted"
        _append_audit_event(
            db=db,
            source_document=source_document,
            event_name="extraction_completed",
            payload={
                "extraction_id": extraction.id,
                "chunk_count": len(chunk_rows),
                "quality_score": extraction.quality_score,
            },
        )
        db.commit()
        db.refresh(extraction)

        return _outcome_from_extraction(db, extraction)
    except Exception as exc:
        extraction.status = "failed"
        extraction.completed_at = _now_utc()
        extraction.error_message = str(exc)[:2000]
        source_document.status = "extraction_failed"
        _append_audit_event(
            db=db,
            source_document=source_document,
            event_name="extraction_failed",
            payload={"extraction_id": extraction.id, "error": extraction.error_message},
        )
        db.commit()
        db.refresh(extraction)
        raise


def run_ocr_extraction(
    *,
    db: Session,
    source_document: SourceDocument,
    blob_storage: BlobStorageService,
    ocr_service: DocumentIntelligenceService,
    extraction_mode: str = "ocr",
    max_attempts: int = 3,
) -> OcrExtractionOutcome:
    extraction = ExtractionRecord(
        source_document_id=source_document.id,
        provider="azure_document_intelligence",
        extraction_mode=extraction_mode,
        status="pending",
    )
    db.add(extraction)
    db.flush()
    _append_audit_event(
        db=db,
        source_document=source_document,
        event_name="extraction_record_created",
        payload={"extraction_id": extraction.id, "mode": extraction_mode},
    )
    db.commit()
    db.refresh(extraction)
    return run_ocr_extraction_for_record(
        db=db,
        extraction_id=extraction.id,
        blob_storage=blob_storage,
        ocr_service=ocr_service,
        max_attempts=max_attempts,
    )


def mark_extraction_retry_state(
    *,
    db: Session,
    extraction_id: str,
    attempt: int,
    defer_seconds: int,
    error_message: str,
) -> None:
    extraction = db.scalar(select(ExtractionRecord).where(ExtractionRecord.id == extraction_id))
    if extraction is None:
        return
    source_document = db.scalar(
        select(SourceDocument).where(SourceDocument.id == extraction.source_document_id)
    )
    if source_document is None:
        return

    extraction.status = "retrying"
    extraction.error_message = (
        f"Retry scheduled (attempt={attempt}, defer={defer_seconds}s): {error_message}"
    )[:2000]
    source_document.status = "queued_for_extraction"
    _append_audit_event(
        db=db,
        source_document=source_document,
        event_name="extraction_retry_scheduled",
        payload={
            "extraction_id": extraction.id,
            "attempt": attempt,
            "defer_seconds": defer_seconds,
            "error": error_message[:500],
        },
    )
    db.commit()


def mark_extraction_failed_state(
    *,
    db: Session,
    extraction_id: str,
    error_message: str,
) -> None:
    extraction = db.scalar(select(ExtractionRecord).where(ExtractionRecord.id == extraction_id))
    if extraction is None:
        return
    source_document = db.scalar(
        select(SourceDocument).where(SourceDocument.id == extraction.source_document_id)
    )
    if source_document is None:
        return

    extraction.status = "failed"
    extraction.completed_at = _now_utc()
    extraction.error_message = error_message[:2000]
    source_document.status = "extraction_failed"
    _append_audit_event(
        db=db,
        source_document=source_document,
        event_name="extraction_retry_exhausted",
        payload={"extraction_id": extraction.id, "error": error_message[:500]},
    )
    db.commit()


def run_ocr_extraction_for_record(
    *,
    db: Session,
    extraction_id: str,
    blob_storage: BlobStorageService,
    ocr_service: DocumentIntelligenceService,
    max_attempts: int = 3,
) -> OcrExtractionOutcome:
    extraction = db.scalar(select(ExtractionRecord).where(ExtractionRecord.id == extraction_id))
    if extraction is None:
        raise ValueError("Extraction record not found.")

    source_document = db.scalar(
        select(SourceDocument).where(SourceDocument.id == extraction.source_document_id)
    )
    if source_document is None:
        raise ValueError("Source document not found for extraction.")

    if extraction.status == "completed":
        return _outcome_from_extraction(db, extraction)
    if extraction.status == "processing":
        raise RuntimeError("Extraction is already processing.")

    if not _try_acquire_processing_lock(db, extraction.id):
        db.refresh(extraction)
        if extraction.status == "completed":
            return _outcome_from_extraction(db, extraction)
        raise RuntimeError("Extraction lock not acquired.")

    db.refresh(extraction)
    return _execute_extraction(
        db=db,
        extraction=extraction,
        source_document=source_document,
        blob_storage=blob_storage,
        ocr_service=ocr_service,
        max_attempts=max_attempts,
    )
