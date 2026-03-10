from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.core import AuditEvent, Chunk, ExtractionRecord, Project, SourceDocument, Tenant
from app.api.routes.documents import _get_ocr_service_safe
from app.services.blob_storage import LocalBlobStorageService, get_blob_storage_service
from app.services.job_queue import get_job_queue_service


def _seed_tenant_and_project(db: Session) -> tuple[str, str]:
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
    db.commit()
    return tenant.id, project.id


def test_upload_document_persists_metadata_and_blob(tmp_path: Path) -> None:
    db_file = tmp_path / "test_documents.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    blob_root = tmp_path / "blob-store"
    storage = LocalBlobStorageService(root_path=blob_root, container="raw-documents")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_blob_storage():
        return storage

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_blob_storage_service] = override_blob_storage
    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        file_bytes = b"mock invoice payload"
        response = client.post(
            "/documents/upload",
            data={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "document_type": "invoice",
            },
            files={
                "file": ("invoice.pdf", file_bytes, "application/pdf"),
            },
            headers={"x-user-role": "analyst"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["tenant_id"] == tenant_id
        assert body["project_id"] == project_id
        assert body["document_type"] == "invoice"
        assert body["mime_type"] == "application/pdf"
        assert body["checksum"]
        assert body["storage_uri"].startswith("file://")

        with TestingSessionLocal() as session:
            row = session.get(SourceDocument, body["document_id"])
            assert row is not None
            assert row.filename == "invoice.pdf"
            assert row.storage_uri == body["storage_uri"]

        persisted_file = Path(body["storage_uri"].replace("file://", ""))
        assert persisted_file.exists()
        assert persisted_file.read_bytes() == file_bytes
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


class _FakeOcrService:
    def analyze_document(
        self,
        payload: bytes,
        content_type: str | None = None,
    ) -> Any:
        _ = payload
        _ = content_type

        class _Result:
            full_text = "Invoice Total 1000 TRY"
            raw_payload = {"pages": [{"page_number": 1, "text": "Invoice Total 1000 TRY"}]}
            model_id = "prebuilt-layout"
            pages = [type("Page", (), {"page_number": 1, "text": "Invoice Total 1000 TRY"})()]

        return _Result()


class _FakeQueueService:
    def __init__(self) -> None:
        self.enqueued_ids: list[str] = []

    async def enqueue_extraction(self, extraction_id: str) -> str:
        self.enqueued_ids.append(extraction_id)
        return f"job-{len(self.enqueued_ids)}"


def test_extract_document_creates_extraction_and_chunks(tmp_path: Path) -> None:
    db_file = tmp_path / "test_extract.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    blob_root = tmp_path / "blob-store"
    storage = LocalBlobStorageService(root_path=blob_root, container="raw-documents")

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_blob_storage():
        return storage

    def override_ocr_service():
        return _FakeOcrService()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_blob_storage_service] = override_blob_storage
    app.dependency_overrides[_get_ocr_service_safe] = override_ocr_service
    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        upload_response = client.post(
            "/documents/upload",
            data={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "document_type": "invoice",
            },
            files={
                "file": ("invoice.pdf", b"raw invoice bytes", "application/pdf"),
            },
            headers={"x-user-role": "analyst"},
        )
        assert upload_response.status_code == 201
        document_id = upload_response.json()["document_id"]

        extract_response = client.post(
            f"/documents/{document_id}/extract",
            json={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "extraction_mode": "ocr",
            },
            headers={"x-user-role": "analyst"},
        )
        assert extract_response.status_code == 200
        body = extract_response.json()
        assert body["status"] == "completed"
        assert body["chunk_count"] == 1
        assert body["provider"] == "azure_document_intelligence"
        assert body["extracted_text_uri"].startswith("file://")
        assert body["raw_payload_uri"].startswith("file://")

        with TestingSessionLocal() as session:
            extraction = session.get(ExtractionRecord, body["extraction_id"])
            assert extraction is not None
            assert extraction.status == "completed"
            assert extraction.extracted_text_uri == body["extracted_text_uri"]
            assert extraction.raw_payload_uri == body["raw_payload_uri"]

            chunks = (
                session.query(Chunk)
                .filter(Chunk.source_document_id == document_id)
                .order_by(Chunk.chunk_index.asc())
                .all()
            )
            assert len(chunks) == 1
            assert chunks[0].text == "Invoice Total 1000 TRY"

            source_document = session.get(SourceDocument, document_id)
            assert source_document is not None
            assert source_document.status == "extracted"

        parsed_artifact = Path(body["extracted_text_uri"].replace("file://", ""))
        raw_artifact = Path(body["raw_payload_uri"].replace("file://", ""))
        assert parsed_artifact.exists()
        assert raw_artifact.exists()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_queue_extraction_idempotency_and_status_endpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "test_queue.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    blob_root = tmp_path / "blob-store"
    storage = LocalBlobStorageService(root_path=blob_root, container="raw-documents")
    fake_queue = _FakeQueueService()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_blob_storage():
        return storage

    def override_queue_service():
        return fake_queue

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_blob_storage_service] = override_blob_storage
    app.dependency_overrides[get_job_queue_service] = override_queue_service
    client = TestClient(app)

    try:
        with TestingSessionLocal() as session:
            tenant_id, project_id = _seed_tenant_and_project(session)

        upload_response = client.post(
            "/documents/upload",
            data={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "document_type": "invoice",
            },
            files={"file": ("invoice.pdf", b"raw invoice bytes", "application/pdf")},
            headers={"x-user-role": "analyst"},
        )
        assert upload_response.status_code == 201
        document_id = upload_response.json()["document_id"]

        queue_response = client.post(
            f"/documents/{document_id}/extract/queue",
            json={"tenant_id": tenant_id, "project_id": project_id, "extraction_mode": "ocr"},
            headers={"x-user-role": "analyst"},
        )
        assert queue_response.status_code == 202
        queue_body = queue_response.json()
        extraction_id = queue_body["extraction_id"]
        assert queue_body["status"] == "queued"
        assert queue_body["queue_job_id"] == "job-1"

        with TestingSessionLocal() as session:
            enqueue_events = (
                session.query(AuditEvent)
                .filter(
                    AuditEvent.event_type == "document_extraction_queue",
                    AuditEvent.event_name == "extraction_enqueued",
                )
                .all()
            )
            assert len(enqueue_events) == 1

        second_queue_response = client.post(
            f"/documents/{document_id}/extract/queue",
            json={"tenant_id": tenant_id, "project_id": project_id, "extraction_mode": "ocr"},
            headers={"x-user-role": "analyst"},
        )
        assert second_queue_response.status_code == 409
        assert "already in progress" in second_queue_response.json()["detail"]

        status_response = client.get(
            f"/documents/{document_id}/extractions/{extraction_id}",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["status"] == "queued"
        assert status_body["chunk_count"] == 0

        index_status_response = client.get(
            f"/documents/{document_id}/extractions/{extraction_id}/index-status",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert index_status_response.status_code == 200
        assert index_status_response.json()["status"] == "not_started"

        with TestingSessionLocal() as session:
            extraction = session.get(ExtractionRecord, extraction_id)
            assert extraction is not None
            extraction.status = "completed"
            extraction.started_at = datetime.now(timezone.utc)
            extraction.completed_at = datetime.now(timezone.utc)
            extraction.quality_score = 99.0
            session.add(
                Chunk(
                    source_document_id=document_id,
                    extraction_record_id=extraction_id,
                    chunk_index=0,
                    text="normalized text",
                    page=1,
                    token_count=2,
                )
            )
            session.commit()

        completed_status_response = client.get(
            f"/documents/{document_id}/extractions/{extraction_id}",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert completed_status_response.status_code == 200
        completed_body = completed_status_response.json()
        assert completed_body["status"] == "completed"
        assert completed_body["chunk_count"] == 1
        assert completed_body["quality_score"] == 99.0

        with TestingSessionLocal() as session:
            extraction = session.get(ExtractionRecord, extraction_id)
            assert extraction is not None
            extraction.status = "indexed"
            session.commit()

        indexed_status_response = client.get(
            f"/documents/{document_id}/extractions/{extraction_id}/index-status",
            params={"tenant_id": tenant_id, "project_id": project_id},
            headers={"x-user-role": "analyst"},
        )
        assert indexed_status_response.status_code == 200
        indexed_status_body = indexed_status_response.json()
        assert indexed_status_body["status"] == "completed"
        assert indexed_status_body["indexed_chunk_count"] == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
