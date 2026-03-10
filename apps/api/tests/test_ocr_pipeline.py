from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.core import AuditEvent, ExtractionRecord, Project, SourceDocument, Tenant
from app.services.blob_storage import LocalBlobStorageService
from app.services.ocr_pipeline import (
    mark_extraction_failed_state,
    mark_extraction_retry_state,
    run_ocr_extraction_for_record,
)
import app.services.ocr_pipeline as ocr_pipeline


def _seed_source_document(db: Session, storage_uri: str) -> SourceDocument:
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
        storage_uri=storage_uri,
        checksum="abc",
        mime_type="application/pdf",
        status="uploaded",
    )
    db.add(source_document)
    db.commit()
    db.refresh(source_document)
    return source_document


def test_run_ocr_extraction_for_record_raises_when_lock_not_acquired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "test_ocr_lock.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    blob_root = tmp_path / "blob-store"
    storage = LocalBlobStorageService(root_path=blob_root, container="raw-documents")
    source_payload = b"raw payload"
    source_uri = storage.upload_bytes(source_payload, "ten/prj/raw.bin", "application/pdf")

    with TestingSessionLocal() as session:
        source_document = _seed_source_document(session, source_uri)
        extraction = ExtractionRecord(
            source_document_id=source_document.id,
            provider="azure_document_intelligence",
            extraction_mode="ocr",
            status="queued",
        )
        session.add(extraction)
        session.commit()
        session.refresh(extraction)

        monkeypatch.setattr(ocr_pipeline, "_try_acquire_processing_lock", lambda *_args, **_kwargs: False)

        with pytest.raises(RuntimeError, match="lock not acquired"):
            run_ocr_extraction_for_record(
                db=session,
                extraction_id=extraction.id,
                blob_storage=storage,
                ocr_service=object(),  # not used due lock failure
            )

    engine.dispose()


def test_mark_extraction_retry_and_failed_states_emit_audit_events(tmp_path: Path) -> None:
    db_file = tmp_path / "test_ocr_retry.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    blob_root = tmp_path / "blob-store"
    storage = LocalBlobStorageService(root_path=blob_root, container="raw-documents")
    source_uri = storage.upload_bytes(b"raw payload", "ten/prj/raw.bin", "application/pdf")

    with TestingSessionLocal() as session:
        source_document = _seed_source_document(session, source_uri)
        extraction = ExtractionRecord(
            source_document_id=source_document.id,
            provider="azure_document_intelligence",
            extraction_mode="ocr",
            status="queued",
        )
        session.add(extraction)
        session.commit()
        session.refresh(extraction)

        mark_extraction_retry_state(
            db=session,
            extraction_id=extraction.id,
            attempt=1,
            defer_seconds=2,
            error_message="transient failure",
        )
        session.refresh(extraction)
        assert extraction.status == "retrying"
        assert "Retry scheduled" in (extraction.error_message or "")

        mark_extraction_failed_state(
            db=session,
            extraction_id=extraction.id,
            error_message="retry exhausted",
        )
        session.refresh(extraction)
        assert extraction.status == "failed"
        assert extraction.error_message == "retry exhausted"

        event_names = [
            row.event_name
            for row in session.query(AuditEvent)
            .filter(AuditEvent.event_type == "document_extraction")
            .all()
        ]
        assert "extraction_retry_scheduled" in event_names
        assert "extraction_retry_exhausted" in event_names

    engine.dispose()
