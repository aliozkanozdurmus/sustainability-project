from __future__ import annotations

import argparse
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import delete, select


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.core import Chunk, ExtractionRecord, Project, SourceDocument, Tenant
from app.services.blob_storage import get_blob_storage_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_pdf_bytes(*, title: str, lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setTitle(title)
    y = height - 72
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, y, title)
    y -= 32
    pdf.setFont("Helvetica", 11)
    for line in lines:
        for wrapped in _wrap_line(line, 90):
            pdf.drawString(72, y, wrapped)
            y -= 18
            if y < 72:
                pdf.showPage()
                y = height - 72
                pdf.setFont("Helvetica", 11)
    pdf.save()
    return buffer.getvalue()


def _wrap_line(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


@dataclass(frozen=True)
class DemoDocument:
    filename: str
    document_type: str
    section_label: str
    period: str
    text: str


DEMO_DOCUMENTS: tuple[DemoDocument, ...] = (
    DemoDocument(
        filename="energy-and-emissions-2025.pdf",
        document_type="energy_report",
        section_label="TSRS2 Climate and Energy",
        period="2025",
        text=(
            "TSRS2 climate and energy performance for 2025 shows Scope 2 electricity emissions "
            "of 12450 tCO2e compared with 14670 tCO2e in 2024, representing a 15.1 percent "
            "year over year decrease. Renewable electricity share reached 42 percent and energy "
            "efficiency projects reduced purchased electricity demand by 8.4 percent."
        ),
    ),
    DemoDocument(
        filename="governance-and-risk-2025.pdf",
        document_type="governance_pack",
        section_label="TSRS1 Governance and Risk Management",
        period="2025",
        text=(
            "TSRS1 governance and risk management oversight remained active in 2025. The "
            "sustainability committee met 12 times, board oversight covered 100 percent of "
            "material ESG matters, and climate risk review was integrated into annual strategy "
            "and capital allocation decisions."
        ),
    ),
    DemoDocument(
        filename="workforce-and-supply-chain-2025.pdf",
        document_type="social_report",
        section_label="CSRD Workforce and Supply Chain",
        period="2025",
        text=(
            "CSRD workforce and supply chain controls improved in 2025. Lost time injury "
            "frequency rate fell to 0.48 from 0.62, a 22.6 percent improvement, while supplier "
            "code of conduct coverage increased to 96 percent and high risk supplier screening "
            "completion reached 93 percent."
        ),
    ),
)


def _upsert_local_index_entries(project_id: str, source_document_ids: set[str], documents: list[dict]) -> None:
    settings.local_search_index_root_path.mkdir(parents=True, exist_ok=True)
    target = settings.local_search_index_root_path / f"{settings.azure_ai_search_index_name}.json"
    existing: dict[str, dict] = {}
    if target.exists():
        try:
            parsed = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = {
                    str(key): value
                    for key, value in parsed.items()
                    if isinstance(value, dict)
                    and value.get("project_id") != project_id
                    and value.get("source_document_id") not in source_document_ids
                }
        except json.JSONDecodeError:
            existing = {}

    for document in documents:
        existing[str(document["chunk_id"])] = document

    target.write_text(json.dumps(existing, ensure_ascii=True, indent=2), encoding="utf-8")


def seed_demo_evidence(*, tenant_id: str, project_id: str) -> dict[str, object]:
    blob_storage = get_blob_storage_service()
    index_payloads: list[dict] = []
    source_document_ids: set[str] = set()

    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        if tenant is None:
            raise SystemExit(f"Tenant not found: {tenant_id}")

        project = db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
            )
        )
        if project is None:
            raise SystemExit(f"Project not found for tenant: {project_id}")

        for demo in DEMO_DOCUMENTS:
            source_document = db.scalar(
                select(SourceDocument).where(
                    SourceDocument.project_id == project.id,
                    SourceDocument.filename == demo.filename,
                )
            )

            pdf_bytes = _build_pdf_bytes(
                title=demo.section_label,
                lines=[
                    f"Tenant: {tenant.name}",
                    f"Project: {project.name}",
                    f"Reporting period: {demo.period}",
                    "",
                    demo.text,
                ],
            )
            storage_uri = blob_storage.upload_bytes(
                payload=pdf_bytes,
                blob_name=f"{tenant.id}/{project.id}/demo/{demo.filename}",
                content_type="application/pdf",
            )

            if source_document is None:
                source_document = SourceDocument(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    document_type=demo.document_type,
                    filename=demo.filename,
                    storage_uri=storage_uri,
                    checksum=f"seed-{demo.filename}",
                    mime_type="application/pdf",
                    issued_at=datetime(int(demo.period), 12, 31, tzinfo=timezone.utc),
                    status="indexed",
                )
                db.add(source_document)
                db.flush()
            else:
                source_document.document_type = demo.document_type
                source_document.storage_uri = storage_uri
                source_document.checksum = f"seed-{demo.filename}"
                source_document.mime_type = "application/pdf"
                source_document.issued_at = datetime(int(demo.period), 12, 31, tzinfo=timezone.utc)
                source_document.status = "indexed"

            extraction = db.scalar(
                select(ExtractionRecord)
                .where(ExtractionRecord.source_document_id == source_document.id)
                .order_by(ExtractionRecord.created_at.desc())
            )
            if extraction is None:
                extraction = ExtractionRecord(
                    source_document_id=source_document.id,
                    provider="demo_seed",
                    extraction_mode="seed",
                    status="indexed",
                    quality_score=99.0,
                    started_at=_utcnow(),
                    completed_at=_utcnow(),
                )
                db.add(extraction)
                db.flush()
            else:
                extraction.provider = "demo_seed"
                extraction.extraction_mode = "seed"
                extraction.status = "indexed"
                extraction.quality_score = 99.0
                extraction.started_at = extraction.started_at or _utcnow()
                extraction.completed_at = _utcnow()
                extraction.error_message = None

            existing_chunks = db.scalars(
                select(Chunk).where(Chunk.source_document_id == source_document.id)
            ).all()
            if existing_chunks:
                db.execute(delete(Chunk).where(Chunk.source_document_id == source_document.id))
                db.flush()

            chunk = Chunk(
                source_document_id=source_document.id,
                extraction_record_id=extraction.id,
                chunk_index=0,
                text=demo.text,
                page=1,
                section_label=demo.section_label,
                token_count=len(demo.text.split()),
            )
            db.add(chunk)
            db.flush()

            source_document_ids.add(source_document.id)
            index_payloads.append(
                {
                    "id": chunk.id,
                    "chunk_id": chunk.id,
                    "tenant_id": tenant.id,
                    "project_id": project.id,
                    "source_document_id": source_document.id,
                    "extraction_record_id": extraction.id,
                    "chunk_index": chunk.chunk_index,
                    "page": chunk.page,
                    "section_label": chunk.section_label,
                    "token_count": chunk.token_count,
                    "content": chunk.text,
                    "metadata": {
                        "document_type": source_document.document_type,
                        "mime_type": source_document.mime_type,
                        "period": demo.period,
                    },
                }
            )

        db.commit()

    _upsert_local_index_entries(project_id, source_document_ids, index_payloads)
    return {"seeded_documents": len(DEMO_DOCUMENTS), "project_id": project_id, "tenant_id": tenant_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed deterministic demo ESG evidence into the local project store.")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    print(json.dumps(seed_demo_evidence(tenant_id=args.tenant_id, project_id=args.project_id), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
