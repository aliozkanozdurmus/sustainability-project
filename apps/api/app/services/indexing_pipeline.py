from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import AuditEvent, Chunk, ExtractionRecord, SourceDocument
from app.services.search_index import SearchChunkDocument, SearchIndexService

INDEX_PROCESSABLE_STATUSES = ("completed", "indexing_retrying")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IndexingOutcome:
    extraction_id: str
    source_document_id: str
    status: str
    indexed_chunk_count: int
    provider: str
    index_name: str


def _append_indexing_audit_event(
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
            event_type="document_indexing",
            event_name=event_name,
            event_payload=payload or {},
        )
    )


def _normalize_chunk_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed


def _build_search_documents(
    *,
    source_document: SourceDocument,
    extraction: ExtractionRecord,
    chunks: list[Chunk],
) -> list[SearchChunkDocument]:
    documents: list[SearchChunkDocument] = []
    for chunk in chunks:
        normalized_content = _normalize_chunk_text(chunk.text)
        if not normalized_content:
            continue
        token_count = chunk.token_count or len(normalized_content.split())
        documents.append(
            SearchChunkDocument(
                chunk_id=chunk.id,
                tenant_id=source_document.tenant_id,
                project_id=source_document.project_id,
                source_document_id=source_document.id,
                extraction_record_id=extraction.id,
                chunk_index=chunk.chunk_index,
                page=chunk.page,
                section_label=chunk.section_label,
                token_count=token_count,
                content=normalized_content,
                metadata={
                    "document_type": source_document.document_type,
                    "mime_type": source_document.mime_type,
                    "issued_at": (
                        source_document.issued_at.isoformat() if source_document.issued_at else None
                    ),
                },
            )
        )
    return documents


def _try_acquire_indexing_lock(db: Session, extraction_id: str) -> bool:
    result = db.execute(
        update(ExtractionRecord)
        .where(
            ExtractionRecord.id == extraction_id,
            ExtractionRecord.status.in_(INDEX_PROCESSABLE_STATUSES),
        )
        .values(
            status="indexing",
            error_message=None,
            updated_at=_now_utc(),
        )
    )
    db.commit()
    return bool(result.rowcount)


def run_chunk_indexing_for_extraction(
    *,
    db: Session,
    extraction_id: str,
    index_service: SearchIndexService,
) -> IndexingOutcome:
    extraction = db.scalar(select(ExtractionRecord).where(ExtractionRecord.id == extraction_id))
    if extraction is None:
        raise ValueError("Extraction record not found.")

    source_document = db.scalar(
        select(SourceDocument).where(SourceDocument.id == extraction.source_document_id)
    )
    if source_document is None:
        raise ValueError("Source document not found for extraction.")

    if extraction.status == "indexed":
        indexed_count = (
            len(
                db.scalars(
                    select(Chunk).where(Chunk.extraction_record_id == extraction.id)
                ).all()
            )
        )
        return IndexingOutcome(
            extraction_id=extraction.id,
            source_document_id=source_document.id,
            status="indexed",
            indexed_chunk_count=indexed_count,
            provider="azure_ai_search",
            index_name=settings.azure_ai_search_index_name,
        )

    if not _try_acquire_indexing_lock(db, extraction.id):
        db.refresh(extraction)
        if extraction.status == "indexed":
            indexed_count = (
                len(
                    db.scalars(
                        select(Chunk).where(Chunk.extraction_record_id == extraction.id)
                    ).all()
                )
            )
            return IndexingOutcome(
                extraction_id=extraction.id,
                source_document_id=source_document.id,
                status="indexed",
                indexed_chunk_count=indexed_count,
                provider="azure_ai_search",
                index_name=settings.azure_ai_search_index_name,
            )
        raise RuntimeError("Indexing lock not acquired.")

    db.refresh(extraction)

    try:
        _append_indexing_audit_event(
            db=db,
            source_document=source_document,
            event_name="indexing_started",
            payload={"extraction_id": extraction.id},
        )
        chunks = db.scalars(select(Chunk).where(Chunk.extraction_record_id == extraction.id)).all()
        documents = _build_search_documents(
            source_document=source_document,
            extraction=extraction,
            chunks=chunks,
        )
        indexed_count = index_service.upsert_chunk_documents(documents)

        extraction.status = "indexed"
        extraction.error_message = None
        source_document.status = "indexed"
        _append_indexing_audit_event(
            db=db,
            source_document=source_document,
            event_name="indexing_completed",
            payload={
                "extraction_id": extraction.id,
                "indexed_chunk_count": indexed_count,
                "index_name": settings.azure_ai_search_index_name,
            },
        )
        db.commit()
        return IndexingOutcome(
            extraction_id=extraction.id,
            source_document_id=source_document.id,
            status="indexed",
            indexed_chunk_count=indexed_count,
            provider="azure_ai_search",
            index_name=settings.azure_ai_search_index_name,
        )
    except Exception as exc:
        extraction.status = "indexing_failed"
        extraction.error_message = str(exc)[:2000]
        source_document.status = "indexing_failed"
        _append_indexing_audit_event(
            db=db,
            source_document=source_document,
            event_name="indexing_failed",
            payload={"extraction_id": extraction.id, "error": extraction.error_message},
        )
        db.commit()
        raise


def mark_indexing_retry_state(
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

    extraction.status = "indexing_retrying"
    extraction.error_message = (
        f"Index retry scheduled (attempt={attempt}, defer={defer_seconds}s): {error_message}"
    )[:2000]
    source_document.status = "indexing_retrying"
    _append_indexing_audit_event(
        db=db,
        source_document=source_document,
        event_name="indexing_retry_scheduled",
        payload={
            "extraction_id": extraction.id,
            "attempt": attempt,
            "defer_seconds": defer_seconds,
            "error": error_message[:500],
        },
    )
    db.commit()


def mark_indexing_failed_state(
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

    extraction.status = "indexing_failed"
    extraction.error_message = error_message[:2000]
    source_document.status = "indexing_failed"
    _append_indexing_audit_event(
        db=db,
        source_document=source_document,
        event_name="indexing_retry_exhausted",
        payload={"extraction_id": extraction.id, "error": error_message[:500]},
    )
    db.commit()
