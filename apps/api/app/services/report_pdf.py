# Bu servis, report_pdf akisindaki uygulama mantigini tek yerde toplar.

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from io import BytesIO
import re

import pdfplumber
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import (
    CalculationRun,
    Claim,
    ClaimCitation,
    Project,
    ReportArtifact,
    ReportRun,
    ReportSection,
    SourceDocument,
    Tenant,
    VerificationResult,
)
from app.services.blob_storage import BlobStorageService, get_blob_storage_service


REPORT_PDF_ARTIFACT_TYPE = "report_pdf"
REPORT_PDF_CONTENT_TYPE = "application/pdf"
REPORT_PDF_COVER_TITLE = "2025 Sustainability Report Demo"
REPORT_PDF_COVER_MARKER = "Sustainability Report Demo"


class ReportPdfGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportPdfPayload:
    filename: str
    content_type: str
    payload: bytes
    checksum: str


def _page_number(canvas, _doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawRightString(545, 24, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=colors.HexColor("#103b2f"),
            spaceAfter=20,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=22,
            textColor=colors.HexColor("#0d3b66"),
            spaceBefore=12,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ClaimBody",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Meta",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#555555"),
            spaceAfter=4,
        )
    )
    return styles


def _safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-")
    return normalized or "project"


def _build_filename(*, project: Project, report_run: ReportRun) -> str:
    project_part = _safe_filename_part(project.code or project.name)
    return f"{project_part}-report-{report_run.id}.pdf"


def _validate_pdf_bytes(payload: bytes) -> None:
    with pdfplumber.open(BytesIO(payload)) as pdf:
        if not pdf.pages:
            raise ReportPdfGenerationError("Generated PDF validation failed: empty document.")
        first_page_text = (pdf.pages[0].extract_text() or "").strip()
        if REPORT_PDF_COVER_MARKER not in first_page_text:
            raise ReportPdfGenerationError(
                "Generated PDF validation failed: cover text missing."
            )


def get_report_artifact(
    *,
    db: Session,
    report_run_id: str,
    artifact_type: str = REPORT_PDF_ARTIFACT_TYPE,
) -> ReportArtifact | None:
    return db.scalar(
        select(ReportArtifact).where(
            ReportArtifact.report_run_id == report_run_id,
            ReportArtifact.artifact_type == artifact_type,
        )
    )


def build_report_pdf_payload(
    *,
    db: Session,
    report_run: ReportRun,
) -> ReportPdfPayload:
    tenant = db.get(Tenant, report_run.tenant_id)
    project = db.get(Project, report_run.project_id)
    if tenant is None or project is None:
        raise ReportPdfGenerationError("Run is missing tenant/project references.")

    latest_attempt = int(
        db.scalar(
            select(func.max(VerificationResult.run_attempt)).where(
                VerificationResult.report_run_id == report_run.id,
            )
        )
        or 0
    )

    sections = db.scalars(
        select(ReportSection)
        .where(ReportSection.report_run_id == report_run.id)
        .order_by(ReportSection.ordinal.asc(), ReportSection.created_at.asc())
    ).all()

    claims = db.scalars(
        select(Claim)
        .join(ReportSection, ReportSection.id == Claim.report_section_id)
        .where(ReportSection.report_run_id == report_run.id)
        .order_by(ReportSection.ordinal.asc(), Claim.created_at.asc())
    ).all()
    claim_ids = [claim.id for claim in claims]

    citations = (
        db.execute(
            select(
                ClaimCitation.claim_id,
                ClaimCitation.chunk_id,
                ClaimCitation.page,
                SourceDocument.filename,
            )
            .join(SourceDocument, SourceDocument.id == ClaimCitation.source_document_id)
            .where(ClaimCitation.claim_id.in_(claim_ids))
            .order_by(ClaimCitation.created_at.asc())
        ).all()
        if claim_ids
        else []
    )

    calculations = (
        db.scalars(
            select(CalculationRun).where(
                CalculationRun.report_run_id == report_run.id,
                CalculationRun.claim_id.in_(claim_ids),
            )
        ).all()
        if claim_ids
        else []
    )

    verifications = (
        db.scalars(
            select(VerificationResult).where(
                VerificationResult.report_run_id == report_run.id,
                VerificationResult.run_attempt == latest_attempt,
            )
        ).all()
        if latest_attempt
        else []
    )

    styles = _build_styles()
    story = []

    citation_map: dict[str, list[str]] = defaultdict(list)
    for row in citations:
        page_text = f" page {row.page}" if row.page else ""
        citation_map[str(row.claim_id)].append(f"{row.filename}{page_text} - chunk {row.chunk_id}")

    calc_map = {str(calc.claim_id): calc for calc in calculations if calc.claim_id is not None}
    verification_map = {verification.claim_id: verification for verification in verifications}

    pass_count = sum(1 for row in verifications if row.status == "PASS")
    fail_count = sum(1 for row in verifications if row.status == "FAIL")
    unsure_count = sum(1 for row in verifications if row.status == "UNSURE")

    story.append(Spacer(1, 36))
    story.append(Paragraph(REPORT_PDF_COVER_TITLE, styles["CoverTitle"]))
    story.append(Paragraph(escape(tenant.name), styles["Heading2"]))
    story.append(Paragraph(escape(project.name), styles["Heading3"]))
    story.append(Spacer(1, 24))

    summary_table = Table(
        [
            ["Run ID", report_run.id],
            ["Status", report_run.status],
            ["Publish Ready", "yes" if report_run.publish_ready else "no"],
            ["Latest Verification Attempt", str(latest_attempt or "-")],
            ["Verified PASS Claims", str(pass_count)],
            ["FAIL / UNSURE Claims", f"{fail_count} / {unsure_count}"],
        ],
        colWidths=[170, 340],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f1ed")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1f2937")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#95b8ad")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d9d2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 18))
    story.append(
        Paragraph(
            (
                "This package was produced from deterministic demo evidence, persisted claims, "
                "and the latest verification artifacts in the application database. Every listed "
                "claim below includes its evidence reference and, when numeric, its calculator artifact."
            ),
            styles["BodyText"],
        )
    )
    story.append(PageBreak())
    story.append(Paragraph("Verified Disclosure Sections", styles["SectionHeading"]))

    claims_by_section: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        claims_by_section[claim.report_section_id].append(claim)

    if not sections:
        story.append(Paragraph("No persisted sections for this run.", styles["Meta"]))
        story.append(Spacer(1, 8))

    for section in sections:
        story.append(
            Paragraph(
                f"{escape(section.section_code)} - {escape(section.title)}",
                styles["Heading2"],
            )
        )
        section_claims = claims_by_section.get(section.id, [])
        if not section_claims:
            story.append(Paragraph("No persisted claims for this section.", styles["Meta"]))
            story.append(Spacer(1, 8))
            continue

        for idx, claim in enumerate(section_claims, start=1):
            story.append(
                Paragraph(
                    f"<b>Claim {idx}.</b> {escape(claim.statement)}",
                    styles["ClaimBody"],
                )
            )
            verification = verification_map.get(claim.id)
            if verification is not None:
                story.append(
                    Paragraph(
                        (
                            f"Verification: {escape(verification.status)} | "
                            f"Reason: {escape(verification.reason)} | "
                            f"Confidence: {verification.confidence if verification.confidence is not None else '-'}"
                        ),
                        styles["Meta"],
                    )
                )

            calc = calc_map.get(claim.id)
            if calc is not None:
                value = "-" if calc.output_value is None else f"{calc.output_value:.2f}"
                unit = calc.output_unit or "-"
                story.append(
                    Paragraph(
                        (
                            f"Calculator artifact: {escape(calc.id)} | "
                            f"Formula: {escape(calc.formula_name)} | Output: {value} {escape(unit)}"
                        ),
                        styles["Meta"],
                    )
                )

            references = citation_map.get(claim.id, [])
            if references:
                story.append(Paragraph("Citations: " + escape("; ".join(references)), styles["Meta"]))
            story.append(Spacer(1, 6))
        story.append(Spacer(1, 12))

    story.append(PageBreak())
    story.append(Paragraph("Evidence Index", styles["SectionHeading"]))

    evidence_rows = [["Claim ID", "Evidence Reference"]]
    for claim in claims:
        references = citation_map.get(claim.id, ["No citation persisted"])
        evidence_rows.append([claim.id, references[0]])
        for extra in references[1:]:
            evidence_rows.append(["", extra])

    evidence_table = Table(evidence_rows, colWidths=[140, 370], repeatRows=1)
    evidence_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d3b66")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#9cb3c1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d3dde4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(evidence_table)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=40,
        title="Sustainability Report Demo",
        author="Codex",
    )
    doc.build(story, onFirstPage=_page_number, onLaterPages=_page_number)
    payload = buffer.getvalue()
    _validate_pdf_bytes(payload)

    return ReportPdfPayload(
        filename=_build_filename(project=project, report_run=report_run),
        content_type=REPORT_PDF_CONTENT_TYPE,
        payload=payload,
        checksum=f"sha256:{sha256(payload).hexdigest()}",
    )


def ensure_report_pdf_artifact(
    *,
    db: Session,
    report_run: ReportRun,
    blob_storage: BlobStorageService | None = None,
) -> ReportArtifact:
    existing_artifact = get_report_artifact(db=db, report_run_id=report_run.id)
    if existing_artifact is not None:
        return existing_artifact

    report_pdf = build_report_pdf_payload(db=db, report_run=report_run)
    storage = blob_storage or get_blob_storage_service()
    storage_uri = storage.upload_bytes(
        payload=report_pdf.payload,
        blob_name=(
            f"{report_run.tenant_id}/{report_run.project_id}/runs/{report_run.id}/"
            f"{report_pdf.filename}"
        ),
        content_type=report_pdf.content_type,
        container=settings.azure_storage_container_artifacts,
    )

    artifact = ReportArtifact(
        tenant_id=report_run.tenant_id,
        project_id=report_run.project_id,
        report_run_id=report_run.id,
        artifact_type=REPORT_PDF_ARTIFACT_TYPE,
        filename=report_pdf.filename,
        content_type=report_pdf.content_type,
        storage_uri=storage_uri,
        size_bytes=len(report_pdf.payload),
        checksum=report_pdf.checksum,
    )
    db.add(artifact)
    db.flush()
    return artifact


def download_report_artifact_bytes(
    artifact: ReportArtifact,
    *,
    blob_storage: BlobStorageService | None = None,
) -> bytes:
    storage = blob_storage or get_blob_storage_service()
    return storage.download_bytes(artifact.storage_uri)
