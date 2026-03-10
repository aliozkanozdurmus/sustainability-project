from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.core import AuditEvent, Chunk, ExtractionRecord, Project, SourceDocument, Tenant
from app.services.indexing_pipeline import (
    mark_indexing_failed_state,
    mark_indexing_retry_state,
    run_chunk_indexing_for_extraction,
)
import app.services.indexing_pipeline as indexing_pipeline
from app.services.search_index import SearchChunkDocument


class _FakeIndexService:
    def __init__(self) -> None:
        self.docs: list[SearchChunkDocument] = []

    def upsert_chunk_documents(self, documents: list[SearchChunkDocument]) -> int:
        self.docs.extend(documents)
        return len(documents)


def _seed_extraction_with_chunks(db: Session) -> tuple[SourceDocument, ExtractionRecord]:
    tenant = Tenant(name="Tenant A", slug="tenant-a")
    db.add(tenant)
    db.flush()

    project = Project(
        tenant_id=tenant.id,
        name="Project A",
        code="PRJ-A",
        reporting_currency="TRY",
    )
    db.add(project)
    db.flush()

    source_document = SourceDocument(
        tenant_id=tenant.id,
        project_id=project.id,
        document_type="invoice",
        filename="invoice.pdf",
        storage_uri="file://dummy",
        checksum="abc",
        mime_type="application/pdf",
        status="extracted",
    )
    db.add(source_document)
    db.flush()

    extraction = ExtractionRecord(
        source_document_id=source_document.id,
        provider="azure_document_intelligence",
        extraction_mode="ocr",
        status="completed",
    )
    db.add(extraction)
    db.flush()

    db.add(
        Chunk(
            source_document_id=source_document.id,
            extraction_record_id=extraction.id,
            chunk_index=0,
            text="Invoice   Total\n\n1000 TRY",
            page=1,
            token_count=None,
        )
    )
    db.commit()
    db.refresh(source_document)
    db.refresh(extraction)
    return source_document, extraction


def test_run_chunk_indexing_for_extraction_indexes_normalized_chunks(tmp_path: Path) -> None:
    db_file = tmp_path / "test_indexing.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        source_document, extraction = _seed_extraction_with_chunks(session)
        index_service = _FakeIndexService()

        outcome = run_chunk_indexing_for_extraction(
            db=session,
            extraction_id=extraction.id,
            index_service=index_service,
        )

        assert outcome.status == "indexed"
        assert outcome.indexed_chunk_count == 1
        session.refresh(extraction)
        session.refresh(source_document)
        assert extraction.status == "indexed"
        assert source_document.status == "indexed"
        assert index_service.docs[0].content == "Invoice Total 1000 TRY"

        event_names = [
            row.event_name
            for row in session.query(AuditEvent)
            .filter(AuditEvent.event_type == "document_indexing")
            .all()
        ]
        assert "indexing_started" in event_names
        assert "indexing_completed" in event_names

    engine.dispose()


def test_run_chunk_indexing_for_extraction_raises_when_lock_not_acquired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "test_indexing_lock.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        _, extraction = _seed_extraction_with_chunks(session)
        monkeypatch.setattr(indexing_pipeline, "_try_acquire_indexing_lock", lambda *_a, **_k: False)
        with pytest.raises(RuntimeError, match="Indexing lock not acquired"):
            run_chunk_indexing_for_extraction(
                db=session,
                extraction_id=extraction.id,
                index_service=_FakeIndexService(),
            )

    engine.dispose()


def test_mark_indexing_retry_and_failed_states_emit_events(tmp_path: Path) -> None:
    db_file = tmp_path / "test_indexing_retry.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        source_document, extraction = _seed_extraction_with_chunks(session)

        mark_indexing_retry_state(
            db=session,
            extraction_id=extraction.id,
            attempt=1,
            defer_seconds=2,
            error_message="transient failure",
        )
        session.refresh(extraction)
        session.refresh(source_document)
        assert extraction.status == "indexing_retrying"
        assert source_document.status == "indexing_retrying"

        mark_indexing_failed_state(
            db=session,
            extraction_id=extraction.id,
            error_message="retry exhausted",
        )
        session.refresh(extraction)
        session.refresh(source_document)
        assert extraction.status == "indexing_failed"
        assert source_document.status == "indexing_failed"

        event_names = [
            row.event_name
            for row in session.query(AuditEvent)
            .filter(AuditEvent.event_type == "document_indexing")
            .all()
        ]
        assert "indexing_retry_scheduled" in event_names
        assert "indexing_retry_exhausted" in event_names

    engine.dispose()
