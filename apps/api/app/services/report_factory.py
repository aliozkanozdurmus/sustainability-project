from __future__ import annotations

from base64 import b64decode, b64encode
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Iterable
from urllib import error, request

from jinja2 import Template
from PIL import Image, ImageDraw, ImageFilter
from pypdf import PdfReader, PdfWriter
import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import (
    BrandKit,
    CalculationRun,
    CanonicalFact,
    Claim,
    ClaimCitation,
    CompanyProfile,
    ConnectorSyncJob,
    IntegrationConfig,
    KpiSnapshot,
    Project,
    ReportArtifact,
    ReportBlueprint,
    ReportPackage,
    ReportRun,
    ReportSection,
    ReportVisualAsset,
    SourceDocument,
    Tenant,
    VerificationResult,
)
from app.services.blob_storage import BlobStorageService, get_blob_storage_service
from app.services.report_context import ensure_project_report_context


REPORT_PDF_ARTIFACT_TYPE = "report_pdf"
VISUAL_MANIFEST_ARTIFACT_TYPE = "visual_manifest"
CITATION_INDEX_ARTIFACT_TYPE = "citation_index"
CALCULATION_APPENDIX_ARTIFACT_TYPE = "calculation_appendix"
COVERAGE_MATRIX_ARTIFACT_TYPE = "coverage_matrix"
ASSUMPTION_REGISTER_ARTIFACT_TYPE = "assumption_register"

PACKAGE_STAGES = (
    "sync",
    "normalize",
    "outline",
    "write",
    "verify",
    "charts_images",
    "compose",
    "package",
    "controlled_publish",
)

PAGE_SIZE = landscape(A4)
PAGE_WIDTH = float(PAGE_SIZE[0])
PAGE_HEIGHT = float(PAGE_SIZE[1])

SECTION_GROUPS: dict[str, tuple[str, str]] = {
    "CEO_MESSAGE": ("Rapor Hakkında", "#f07f13"),
    "COMPANY_PROFILE": ("Şirket Hakkında", "#3a98eb"),
    "GOVERNANCE": ("Sürdürülebilirlik Bakışı", "#72bf44"),
    "DOUBLE_MATERIALITY": ("Sürdürülebilirlik Bakışı", "#0c4a6e"),
    "ENVIRONMENT": ("Çevremiz İçin", "#f4b400"),
    "SOCIAL": ("Toplum İçin", "#0c4a6e"),
}


class ReportPackageGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageArtifacts:
    package: ReportPackage
    artifacts: list[ReportArtifact]


@dataclass(frozen=True)
class RenderedPdf:
    payload: bytes
    renderer: str
    page_count: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "report"


def _to_data_uri(payload: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{b64encode(payload).decode('ascii')}"


def _artifact_filename(project: Project, report_run: ReportRun, artifact_type: str, extension: str) -> str:
    return f"{_safe_slug(project.code or project.name)}-{artifact_type}-{report_run.id}.{extension}"


def _build_artifact_download_path(*, report_run_id: str, artifact_id: str, tenant_id: str, project_id: str) -> str:
    return (
        f"/runs/{report_run_id}/artifacts/{artifact_id}"
        f"?tenant_id={tenant_id}&project_id={project_id}"
    )


def _serialize_stage_history(package: ReportPackage) -> list[dict[str, Any]]:
    history = package.stage_history_json or []
    return history if isinstance(history, list) else []


def _append_stage(package: ReportPackage, stage: str, status: str, detail: str | None = None) -> None:
    history = _serialize_stage_history(package)
    history.append(
        {
            "stage": stage,
            "status": status,
            "at_utc": _utcnow().isoformat(),
            "detail": detail,
        }
    )
    package.current_stage = stage
    package.status = status
    package.stage_history_json = history


def _update_stage(package: ReportPackage, stage: str, status: str, detail: str | None = None) -> None:
    history = _serialize_stage_history(package)
    if history and history[-1]["stage"] == stage and history[-1]["status"] == "running":
        history[-1]["status"] = status
        history[-1]["detail"] = detail
        history[-1]["at_utc"] = _utcnow().isoformat()
    else:
        history.append(
            {
                "stage": stage,
                "status": status,
                "at_utc": _utcnow().isoformat(),
                "detail": detail,
            }
        )
    package.current_stage = stage
    package.status = status
    package.stage_history_json = history


def _to_artifact_response_payload(artifact: ReportArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "filename": artifact.filename,
        "content_type": artifact.content_type,
        "size_bytes": artifact.size_bytes,
        "checksum": artifact.checksum,
        "created_at_utc": artifact.created_at.isoformat(),
        "download_path": _build_artifact_download_path(
            report_run_id=artifact.report_run_id,
            artifact_id=artifact.id,
            tenant_id=artifact.tenant_id,
            project_id=artifact.project_id,
        ),
        "metadata": artifact.artifact_metadata_json or {},
    }


def list_run_artifacts(*, db: Session, report_run_id: str) -> list[ReportArtifact]:
    return db.scalars(
        select(ReportArtifact)
        .where(ReportArtifact.report_run_id == report_run_id)
        .order_by(ReportArtifact.created_at.asc())
    ).all()


def get_report_package(*, db: Session, report_run_id: str) -> ReportPackage | None:
    return db.scalar(select(ReportPackage).where(ReportPackage.report_run_id == report_run_id))


def get_report_artifact_by_id(*, db: Session, report_run_id: str, artifact_id: str) -> ReportArtifact | None:
    return db.scalar(
        select(ReportArtifact).where(
            ReportArtifact.id == artifact_id,
            ReportArtifact.report_run_id == report_run_id,
        )
    )


def _load_weasyprint_html():
    try:
        from weasyprint import HTML
    except Exception:
        return None
    return HTML


def _hex_to_rgba(value: str, alpha: int) -> tuple[int, int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        return (240, 127, 19, alpha)
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4)) + (alpha,)


def _hex_color(value: str, fallback: str) -> colors.Color:
    try:
        return colors.HexColor(value)
    except Exception:
        return colors.HexColor(fallback)


def _build_monogram_svg(brand_name: str, brand: BrandKit) -> str:
    letter = (brand_name.strip() or "V")[0].upper()
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="220" height="220" viewBox="0 0 220 220">
      <rect width="220" height="220" rx="28" fill="{brand.primary_color}"/>
      <rect x="16" y="16" width="188" height="188" rx="24" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.28)" stroke-width="4"/>
      <text x="110" y="136" font-size="104" font-family="{brand.font_family_headings}" text-anchor="middle" fill="white">{letter}</text>
    </svg>
    """.strip()


def _call_image_generation(prompt: str) -> bytes | None:
    endpoint = settings.azure_openai_endpoint
    api_key = settings.azure_openai_api_key
    deployments = [
        deployment
        for deployment in (
            settings.azure_openai_image_deployment,
            settings.azure_openai_image_fallback_deployment,
        )
        if deployment
    ]
    if not (endpoint and api_key and deployments):
        return None

    for deployment in deployments:
        url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/images/generations"
            f"?api-version={settings.azure_openai_api_version}"
        )
        payload = json.dumps(
            {
                "prompt": prompt,
                "size": "1536x1024",
                "quality": "high",
            }
        ).encode("utf-8")
        req = request.Request(
            url=url,
            method="POST",
            data=payload,
            headers={"Content-Type": "application/json", "api-key": str(api_key)},
        )
        try:
            with request.urlopen(req, timeout=45) as response:
                raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
            item = parsed.get("data", [{}])[0]
            if isinstance(item, dict) and item.get("b64_json"):
                return b64decode(item["b64_json"])
            if isinstance(item, dict) and item.get("url"):
                with request.urlopen(item["url"], timeout=45) as image_response:
                    return image_response.read()
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, ValueError):
            continue
    return None


def _generate_fallback_visual(*, title: str, brand: BrandKit, accent_label: str) -> bytes:
    width = 1600
    height = 1000
    image = Image.new("RGB", (width, height), brand.primary_color)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse((840, 120, 1500, 820), fill=_hex_to_rgba(brand.secondary_color, 144))
    draw.rounded_rectangle((140, 240, 980, 860), radius=120, fill=_hex_to_rgba("#ffffff", 48))
    draw.ellipse((160, 680, 520, 1010), fill=_hex_to_rgba(brand.accent_color, 196))
    draw.rectangle((0, 0, 520, height), fill=_hex_to_rgba("#ffffff", 22))
    draw.text((140, 124), title, fill=(255, 255, 255, 255))
    draw.text((145, 184), accent_label, fill=(255, 255, 255, 236))
    composite = Image.alpha_composite(image.convert("RGBA"), overlay.filter(ImageFilter.GaussianBlur(radius=2)))
    buffer = BytesIO()
    composite.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _upsert_visual_asset(
    *,
    db: Session,
    package: ReportPackage,
    visual_slot: str,
    asset_type: str,
    source_type: str,
    decorative_ai_generated: bool,
    prompt_text: str | None,
    storage_uri: str,
    content_type: str,
    checksum: str,
    status: str,
    alt_text: str,
    metadata: dict[str, Any],
) -> None:
    asset = db.scalar(
        select(ReportVisualAsset).where(
            ReportVisualAsset.report_package_id == package.id,
            ReportVisualAsset.visual_slot == visual_slot,
        )
    )
    if asset is None:
        asset = ReportVisualAsset(
            report_package_id=package.id,
            tenant_id=package.tenant_id,
            project_id=package.project_id,
            visual_slot=visual_slot,
            asset_type=asset_type,
            source_type=source_type,
            decorative_ai_generated=decorative_ai_generated,
            prompt_text=prompt_text,
            storage_uri=storage_uri,
            content_type=content_type,
            checksum=checksum,
            status=status,
            alt_text=alt_text,
            metadata_json=metadata,
        )
        db.add(asset)
    else:
        asset.asset_type = asset_type
        asset.source_type = source_type
        asset.decorative_ai_generated = decorative_ai_generated
        asset.prompt_text = prompt_text
        asset.storage_uri = storage_uri
        asset.content_type = content_type
        asset.checksum = checksum
        asset.status = status
        asset.alt_text = alt_text
        asset.metadata_json = metadata
    db.flush()


def _upload_visual_image_asset(
    *,
    db: Session,
    blob_storage: BlobStorageService,
    package: ReportPackage,
    brand: BrandKit,
    visual_slot: str,
    title: str,
    prompt_text: str,
) -> tuple[bytes, str]:
    payload = _call_image_generation(prompt_text)
    source_type = "azure_openai_image" if payload is not None else "generated_placeholder"
    decorative_ai_generated = payload is not None
    if payload is None:
        payload = _generate_fallback_visual(
            title=title,
            brand=brand,
            accent_label=visual_slot.replace("_", " ").upper(),
        )
    checksum = f"sha256:{sha256(payload).hexdigest()}"
    storage_uri = blob_storage.upload_bytes(
        payload=payload,
        blob_name=f"{package.tenant_id}/{package.project_id}/packages/{package.id}/visuals/{visual_slot}.png",
        content_type="image/png",
        container=settings.azure_storage_container_artifacts,
    )
    _upsert_visual_asset(
        db=db,
        package=package,
        visual_slot=visual_slot,
        asset_type="image/png",
        source_type=source_type,
        decorative_ai_generated=decorative_ai_generated,
        prompt_text=prompt_text,
        storage_uri=storage_uri,
        content_type="image/png",
        checksum=checksum,
        status="completed",
        alt_text=title,
        metadata={"title": title},
    )
    return payload, "image/png"


def _upload_visual_svg_asset(
    *,
    db: Session,
    blob_storage: BlobStorageService,
    package: ReportPackage,
    visual_slot: str,
    title: str,
    svg: str,
) -> tuple[bytes, str]:
    payload = svg.encode("utf-8")
    checksum = f"sha256:{sha256(payload).hexdigest()}"
    storage_uri = blob_storage.upload_bytes(
        payload=payload,
        blob_name=f"{package.tenant_id}/{package.project_id}/packages/{package.id}/visuals/{visual_slot}.svg",
        content_type="image/svg+xml",
        container=settings.azure_storage_container_artifacts,
    )
    _upsert_visual_asset(
        db=db,
        package=package,
        visual_slot=visual_slot,
        asset_type="image/svg+xml",
        source_type="deterministic_svg",
        decorative_ai_generated=False,
        prompt_text=None,
        storage_uri=storage_uri,
        content_type="image/svg+xml",
        checksum=checksum,
        status="completed",
        alt_text=title,
        metadata={"title": title},
    )
    return payload, "image/svg+xml"


def _build_chart_svg(*, title: str, values: list[tuple[str, float]], brand: BrandKit) -> str:
    max_value = max((value for _, value in values), default=1.0)
    bar_gap = 82
    bar_width = 52
    baseline = 232
    bars: list[str] = []
    for index, (label, value) in enumerate(values):
        x = 58 + (index * bar_gap)
        bar_height = 0 if max_value <= 0 else max(8, int((value / max_value) * 150))
        y = baseline - bar_height
        fill = brand.primary_color if index == len(values) - 1 else brand.secondary_color
        bars.append(
            f"""
            <rect x="{x}" y="{y}" width="{bar_width}" height="{bar_height}" rx="14" fill="{fill}" />
            <text x="{x + 26}" y="{baseline + 26}" text-anchor="middle" font-size="14" fill="#385168">{escape(label)}</text>
            <text x="{x + 26}" y="{y - 10}" text-anchor="middle" font-size="14" fill="#102a43">{value:g}</text>
            """
        )
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="700" height="300" viewBox="0 0 700 300">
      <rect width="700" height="300" rx="28" fill="#f7fafc" />
      <text x="40" y="44" font-size="22" font-family="{escape(brand.font_family_headings)}" fill="#0f172a">{escape(title)}</text>
      <line x1="44" y1="{baseline}" x2="656" y2="{baseline}" stroke="#cbd5e1" stroke-width="2" />
      {''.join(bars)}
    </svg>
    """.strip()


def _build_matrix_svg(*, title: str, metrics: list[dict[str, Any]], brand: BrandKit) -> str:
    points: list[str] = []
    for index, metric in enumerate(metrics[:6], start=1):
        x = 150 + (index * 70) % 380
        y = 210 - ((index * 47) % 140)
        points.append(
            f"""
            <circle cx="{x}" cy="{y}" r="11" fill="{brand.primary_color}" opacity="0.9" />
            <text x="{x + 16}" y="{y + 4}" font-size="12" fill="#163047">{escape(metric["metric_code"])}</text>
            """
        )
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="700" height="320" viewBox="0 0 700 320">
      <rect width="700" height="320" rx="28" fill="#f8fafc" />
      <text x="38" y="42" font-size="22" font-family="{escape(brand.font_family_headings)}" fill="#0f172a">{escape(title)}</text>
      <line x1="120" y1="260" x2="620" y2="260" stroke="#cbd5e1" stroke-width="2" />
      <line x1="120" y1="260" x2="120" y2="84" stroke="#cbd5e1" stroke-width="2" />
      <text x="22" y="96" font-size="13" fill="#475569">Etki</text>
      <text x="600" y="288" font-size="13" fill="#475569">Finansal</text>
      <rect x="360" y="96" width="230" height="96" rx="24" fill="{brand.accent_color}" opacity="0.14" />
      <text x="382" y="124" font-size="16" fill="#102a43">Öncelikli Alanlar</text>
      <text x="382" y="148" font-size="12" fill="#334155">Kurumsal risk, enerji, tedarik zinciri</text>
      {''.join(points)}
    </svg>
    """.strip()


def _build_grid_svg(*, title: str, metrics: list[dict[str, Any]], brand: BrandKit) -> str:
    cards: list[str] = []
    for index, metric in enumerate(metrics[:4]):
        x = 34 + (index % 2) * 320
        y = 82 + (index // 2) * 104
        cards.append(
            f"""
            <rect x="{x}" y="{y}" width="292" height="82" rx="22" fill="white" stroke="#d8e4ea" />
            <text x="{x + 18}" y="{y + 28}" font-size="12" fill="#64748b">{escape(metric["metric_name"])}</text>
            <text x="{x + 18}" y="{y + 58}" font-size="24" font-family="{escape(brand.font_family_headings)}" fill="{brand.secondary_color}">{escape(metric["display_value"])}</text>
            """
        )
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="700" height="300" viewBox="0 0 700 300">
      <rect width="700" height="300" rx="28" fill="#f8fafc" />
      <text x="36" y="42" font-size="22" font-family="{escape(brand.font_family_headings)}" fill="#0f172a">{escape(title)}</text>
      {''.join(cards)}
    </svg>
    """.strip()


def _quality_grade(score: float) -> str:
    if score >= 95:
        return "A"
    if score >= 90:
        return "A-"
    if score >= 85:
        return "B+"
    if score >= 80:
        return "B"
    return "C+"


def _metric_bucket(facts: list[CanonicalFact]) -> dict[str, list[CanonicalFact]]:
    bucket: dict[str, list[CanonicalFact]] = defaultdict(list)
    for fact in facts:
        bucket[fact.metric_code].append(fact)
    for metric_code in bucket:
        bucket[metric_code].sort(key=lambda row: (row.period_key, row.created_at), reverse=True)
    return bucket


def _ensure_snapshot_rows(*, db: Session, report_run: ReportRun, facts: list[CanonicalFact]) -> None:
    for fact in facts:
        snapshot = db.scalar(
            select(KpiSnapshot).where(
                KpiSnapshot.report_run_id == report_run.id,
                KpiSnapshot.metric_code == fact.metric_code,
                KpiSnapshot.period_key == fact.period_key,
            )
        )
        if snapshot is None:
            snapshot = KpiSnapshot(
                report_run_id=report_run.id,
                tenant_id=report_run.tenant_id,
                project_id=report_run.project_id,
                metric_code=fact.metric_code,
                metric_name=fact.metric_name,
                period_key=fact.period_key,
                unit=fact.unit,
                value_numeric=fact.value_numeric,
                value_text=fact.value_text,
                quality_grade=_quality_grade((fact.confidence_score or 0.9) * 100),
                freshness_at=fact.freshness_at,
                source_fact_ids=[fact.id],
                snapshot_metadata_json={"auto_generated": True},
            )
            db.add(snapshot)
            continue
        snapshot.metric_name = fact.metric_name
        snapshot.unit = fact.unit
        snapshot.value_numeric = fact.value_numeric
        snapshot.value_text = fact.value_text
        snapshot.quality_grade = _quality_grade((fact.confidence_score or 0.9) * 100)
        snapshot.freshness_at = fact.freshness_at
        snapshot.source_fact_ids = [fact.id]
        snapshot.snapshot_metadata_json = {"auto_generated": True}
    db.flush()


def _build_claim_domains(
    *,
    db: Session,
    report_run_id: str,
) -> tuple[dict[str, list[str]], list[dict[str, Any]], list[dict[str, Any]]]:
    latest_attempt = int(
        db.scalar(
            select(func.max(VerificationResult.run_attempt)).where(
                VerificationResult.report_run_id == report_run_id,
            )
        )
        or 0
    )

    claim_rows = db.execute(
        select(
            ReportSection.section_code,
            Claim.id,
            Claim.statement,
            VerificationResult.status,
        )
        .select_from(Claim)
        .join(ReportSection, ReportSection.id == Claim.report_section_id)
        .join(VerificationResult, VerificationResult.claim_id == Claim.id)
        .where(
            ReportSection.report_run_id == report_run_id,
            VerificationResult.report_run_id == report_run_id,
            VerificationResult.run_attempt == latest_attempt,
        )
        .order_by(ReportSection.ordinal.asc(), Claim.created_at.asc())
    ).all()

    citation_rows = db.execute(
        select(
            Claim.id,
            SourceDocument.filename,
            ClaimCitation.chunk_id,
            ClaimCitation.page,
        )
        .select_from(ClaimCitation)
        .join(Claim, Claim.id == ClaimCitation.claim_id)
        .join(SourceDocument, SourceDocument.id == ClaimCitation.source_document_id)
        .join(ReportSection, ReportSection.id == Claim.report_section_id)
        .where(ReportSection.report_run_id == report_run_id)
    ).all()

    citation_map: dict[str, list[str]] = defaultdict(list)
    for row in citation_rows:
        page_label = f" sayfa {row.page}" if row.page else ""
        citation_map[str(row.id)].append(f"{row.filename}{page_label} / chunk {row.chunk_id}")

    claim_domains: dict[str, list[str]] = defaultdict(list)
    citation_index: list[dict[str, Any]] = []
    for row in claim_rows:
        if str(row.status or "").upper() != "PASS":
            continue
        section_code = str(row.section_code)
        claim_text = str(row.statement)
        domain = "governance"
        if "TSRS2" in section_code or "ENVIRONMENT" in section_code:
            domain = "environment"
        elif "CSRD" in section_code or "SOCIAL" in section_code:
            domain = "social"
        claim_domains[domain].append(claim_text)
        citation_index.append(
            {
                "section_code": section_code,
                "statement": claim_text,
                "reference": "; ".join(citation_map.get(str(row.id), ["Kaynak bulunamadı"])),
            }
        )

    calculations = [
        {
            "formula_name": row.formula_name,
            "output_value": row.output_value,
            "output_unit": row.output_unit,
            "trace_log_ref": row.trace_log_ref,
        }
        for row in db.scalars(select(CalculationRun).where(CalculationRun.report_run_id == report_run_id)).all()
    ]
    return claim_domains, citation_index, calculations


def _resolve_section_domain(section_code: str) -> str:
    code = section_code.upper()
    if code in {"ENVIRONMENT"} or "TSRS2" in code:
        return "environment"
    if code in {"SOCIAL"} or "CSRD" in code:
        return "social"
    return "governance"


def _metric_display_value(fact: CanonicalFact) -> str:
    if fact.value_numeric is not None:
        return f"{fact.value_numeric:g} {fact.unit or ''}".strip()
    return fact.value_text or "-"


def _find_metric(metric_bucket: dict[str, list[CanonicalFact]], metric_code: str) -> CanonicalFact | None:
    rows = metric_bucket.get(metric_code, [])
    return rows[0] if rows else None


def _percentage_change(current: CanonicalFact | None, previous: CanonicalFact | None) -> str | None:
    if current is None or previous is None:
        return None
    if current.value_numeric is None or previous.value_numeric in {None, 0}:
        return None
    delta = ((current.value_numeric - previous.value_numeric) / previous.value_numeric) * 100
    direction = "azalış" if delta < 0 else "artış"
    return f"%{abs(delta):.1f} {direction}"


def _build_section_copy(
    *,
    company_profile: CompanyProfile,
    section_code: str,
    title: str,
    facts: list[CanonicalFact],
    metric_bucket: dict[str, list[CanonicalFact]],
    claims: list[str],
) -> tuple[str, list[str]]:
    if section_code == "CEO_MESSAGE":
        highlights = [item for item in claims[:2] if item]
        if company_profile.sustainability_approach:
            highlights.append(company_profile.sustainability_approach)
        if not highlights:
            highlights = [
                "Kurumsal sürdürülebilirlik yaklaşımı veri bütünlüğü ve denetlenebilirlik üzerine kuruludur.",
            ]
        return (
            company_profile.ceo_message
            or (
                f"{company_profile.legal_name}, sürdürülebilirlik gündemini ERP verileri, kanıt havuzu ve "
                "kontrollü yayın akışı ile kurumsal karar alma süreçlerine bağlamaktadır."
            ),
            highlights[:3],
        )

    if section_code == "COMPANY_PROFILE":
        facts_text = ", ".join(_metric_display_value(item) for item in facts[:3])
        return (
            f"{company_profile.legal_name}; {company_profile.sector or 'çok sektörlü üretim'} odağında, "
            f"{company_profile.headquarters or 'Türkiye'} merkezli operasyonlarını veriyle izlenen bir "
            f"sürdürülebilirlik dönüşüm programı ile yönetmektedir. Ölçek göstergeleri: {facts_text}.",
            claims[:3]
            or [
                "Kurumsal profil bölümü şirket tanımı, ölçek ve operasyonel ayak izi ile desteklenir.",
            ],
        )

    if section_code == "GOVERNANCE":
        return (
            "Yönetişim yapısı, sürdürülebilirlik komitesi, yönetim kurulu gözetimi ve karar mekanizmalarının "
            "izlenebilirliğini güçlendirecek şekilde yapılandırılmıştır.",
            claims[:3]
            or [
                "Yönetim kurulu gözetimi ve komite ritmi rapor kapsamına dahil edilmiştir.",
                "Politika ve risk izleme adımları sadece doğrulanmış kanıtlardan türetilir.",
            ],
        )

    if section_code == "DOUBLE_MATERIALITY":
        topic_count = _find_metric(metric_bucket, "MATERIAL_TOPIC_COUNT")
        touchpoints = _find_metric(metric_bucket, "STAKEHOLDER_ENGAGEMENT_TOUCHPOINTS")
        summary_parts = []
        if topic_count is not None:
            summary_parts.append(f"öncelikli konu sayısı {_metric_display_value(topic_count)}")
        if touchpoints is not None:
            summary_parts.append(f"paydaş temas noktası {_metric_display_value(touchpoints)}")
        summary_suffix = ", ".join(summary_parts) if summary_parts else "kanıtlanmış materiality girdileri"
        return (
            f"Çifte önemlilik görünümü, finansal etki ve dış paydaş etkisini tek yüzeyde birleştirir; "
            f"bu sürümde {summary_suffix} ile desteklenmiştir.",
            claims[:3]
            or [
                "Önceliklendirme yalnızca normalize edilen fact havuzu ve onaylı kanıtlar ile kurulur.",
            ],
        )

    if section_code == "ENVIRONMENT":
        scope2 = _find_metric(metric_bucket, "E_SCOPE2_TCO2E")
        scope2_prev = _find_metric(metric_bucket, "E_SCOPE2_TCO2E_PREV")
        renewable = _find_metric(metric_bucket, "RENEWABLE_ELECTRICITY_SHARE")
        intensity = _find_metric(metric_bucket, "ENERGY_INTENSITY_REDUCTION")
        yoy = _percentage_change(scope2, scope2_prev)
        summary_parts = []
        if yoy:
            summary_parts.append(f"scope 2 performansında {yoy}")
        if renewable is not None:
            summary_parts.append(f"yenilenebilir elektrik payı {_metric_display_value(renewable)}")
        if intensity is not None:
            summary_parts.append(f"enerji yoğunluğu iyileşmesi {_metric_display_value(intensity)}")
        joined = ", ".join(summary_parts) if summary_parts else "doğrulanmış çevresel KPI paketi"
        return (
            f"Çevresel performans bölümü; emisyon, enerji ve verimlilik metriklerini Türkçe editoryal akışta "
            f"özetler. Bu çevrimde {joined} öne çıkmaktadır.",
            claims[:3]
            or [
                "Tüm çevresel anlatı, ERP kökenli fact paketleri ve PASS claim havuzu ile sınırlandırılmıştır.",
            ],
        )

    if section_code == "SOCIAL":
        ltifr = _find_metric(metric_bucket, "LTIFR")
        ltifr_prev = _find_metric(metric_bucket, "LTIFR_PREV")
        supplier = _find_metric(metric_bucket, "SUPPLIER_COVERAGE")
        screening = _find_metric(metric_bucket, "HIGH_RISK_SUPPLIER_SCREENING")
        yoy = _percentage_change(ltifr, ltifr_prev)
        summary_parts = []
        if yoy:
            summary_parts.append(f"İSG frekansında {yoy}")
        if supplier is not None:
            summary_parts.append(f"tedarikçi kapsamı {_metric_display_value(supplier)}")
        if screening is not None:
            summary_parts.append(f"yüksek riskli tarama oranı {_metric_display_value(screening)}")
        joined = ", ".join(summary_parts) if summary_parts else "doğrulanmış sosyal performans verileri"
        return (
            f"Sosyal performans anlatısı; iş sağlığı güvenliği, çalışan ölçeği ve tedarik zinciri denetimini "
            f"tek bir kurumsal yüzeyde birleştirir. Bu çevrimde {joined}.",
            claims[:3]
            or [
                "İnsan ve tedarik zinciri göstergeleri yalnızca taze ERP snapshot'ları ile beslenir.",
            ],
        )

    fact_summary = ", ".join(_metric_display_value(item) for item in facts[:4])
    summary = (
        f"{company_profile.legal_name}, {title.lower()} alanında raporlama dönemi boyunca "
        f"kanıtla desteklenen KPI setleriyle tutarlı bir performans hikayesi ortaya koymuştur. "
        f"Öne çıkan metrikler: {fact_summary or 'hazır veri yüzeyi'}."
    )
    highlights = claims[:3] if claims else [
        "Bu bölüm yalnızca normalize ERP fact havuzu ve PASS doğrulanmış claim setinden beslenir.",
        "Kanıtsız veya hesaplama refsiz ifade otomatik olarak dışarıda bırakılır.",
    ]
    return summary, highlights


def _build_section_payload(
    *,
    company_profile: CompanyProfile,
    brand: BrandKit,
    section_definition: dict[str, Any],
    metric_bucket: dict[str, list[CanonicalFact]],
    claim_domains: dict[str, list[str]],
) -> dict[str, Any]:
    section_code = str(section_definition.get("section_code", "")).strip().upper()
    title = str(section_definition.get("title", "")).strip() or section_code
    purpose = str(section_definition.get("purpose", "")).strip() or title
    required_metrics = [str(item).strip().upper() for item in section_definition.get("required_metrics", []) if str(item).strip()]
    section_facts = [metric_bucket[metric][0] for metric in required_metrics if metric_bucket.get(metric)]
    section_metrics = [
        {
            "metric_code": fact.metric_code,
            "metric_name": fact.metric_name,
            "period_key": fact.period_key,
            "display_value": _metric_display_value(fact),
        }
        for fact in section_facts
    ]
    visual_slots = [
        str(item).strip()
        for item in section_definition.get("visual_slots", [])
        if str(item).strip()
    ] or ["cover_hero"]
    primary_visual_slot = next(
        (
            slot
            for slot in visual_slots
            if not any(token in slot.lower() for token in ("chart", "matrix", "grid"))
        ),
        "cover_hero",
    )
    chart_values = [
        (fact.period_key, float(fact.value_numeric if fact.value_numeric is not None else index + 1))
        for index, fact in enumerate(section_facts[:4], start=1)
    ]
    group_title, group_color = SECTION_GROUPS.get(section_code, ("Diğer", brand.primary_color))
    summary, highlights = _build_section_copy(
        company_profile=company_profile,
        section_code=section_code,
        title=title,
        facts=section_facts,
        metric_bucket=metric_bucket,
        claims=claim_domains.get(_resolve_section_domain(section_code), []),
    )
    chart_svg = ""
    if section_code == "DOUBLE_MATERIALITY":
        chart_svg = _build_matrix_svg(title=title, metrics=section_metrics, brand=brand)
    elif visual_slots and any("grid" in slot for slot in visual_slots):
        chart_svg = _build_grid_svg(title=title, metrics=section_metrics, brand=brand)
    elif chart_values:
        chart_svg = _build_chart_svg(title=title, values=chart_values, brand=brand)
    return {
        "section_code": section_code,
        "title": title,
        "purpose": purpose,
        "summary": summary,
        "highlights": highlights,
        "metrics": section_metrics,
        "claims": claim_domains.get(_resolve_section_domain(section_code), []),
        "visual_slots": visual_slots,
        "primary_visual_slot": primary_visual_slot,
        "chart_svg": chart_svg,
        "chart_values": chart_values,
        "appendix_refs": [str(item) for item in section_definition.get("appendix_refs", []) if str(item).strip()],
        "required_metrics": required_metrics,
        "group_title": group_title,
        "group_color": group_color,
    }


def _build_toc_cards(section_payloads: list[dict[str, Any]], appendix_start_page: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    page_pointer = 3
    for section in section_payloads:
        group_title = str(section["group_title"])
        card = grouped.setdefault(
            group_title,
            {
                "title": group_title,
                "accent_color": section["group_color"],
                "lines": [],
            },
        )
        card["lines"].append({"label": section["title"], "page_hint": str(page_pointer)})
        page_pointer += 2
    grouped.setdefault(
        "Ekler",
        {
            "title": "Ekler",
            "accent_color": "#f07f13",
            "lines": [],
        },
    )["lines"].append({"label": "Atıf ve hesaplama ekleri", "page_hint": str(appendix_start_page)})
    return list(grouped.values())


def _render_html_report(
    *,
    tenant: Tenant,
    project: Project,
    company_profile: CompanyProfile,
    brand: BrandKit,
    section_payloads: list[dict[str, Any]],
    visual_data_uris: dict[str, str],
    citations: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    assumptions: list[str],
) -> str:
    appendix_start_page = 3 + (len(section_payloads) * 2)
    template = Template(
        """
<!doctype html>
<html lang="tr">
  <head>
    <meta charset="utf-8" />
    <style>
      @page { size: A4 landscape; margin: 0; }
      body { margin: 0; font-family: "{{ brand.font_family_body }}", "Segoe UI", sans-serif; color: #102a43; }
      .page { min-height: 595px; page-break-after: always; position: relative; overflow: hidden; }
      .cover { background: linear-gradient(135deg, {{ brand.primary_color }} 0%, #ff9d00 100%); color: white; }
      .cover img.hero { position: absolute; right: 0; bottom: 0; width: 58%; height: 100%; object-fit: cover; }
      .cover .cover-fade { position: absolute; inset: 0; background: linear-gradient(90deg, rgba(240,127,19,0.94) 0%, rgba(240,127,19,0.84) 38%, rgba(240,127,19,0.16) 74%, rgba(240,127,19,0.02) 100%); }
      .cover .inner { position: relative; z-index: 2; padding: 44px 44px 38px; max-width: 420px; }
      .cover h1 { font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; font-size: 38px; line-height: 1.06; margin: 18px 0 14px; letter-spacing: 0.01em; }
      .cover p { font-size: 15px; line-height: 1.8; max-width: 360px; }
      .cover .meta { position: absolute; left: 44px; bottom: 34px; z-index: 2; font-size: 13px; line-height: 1.7; }
      .contents { background: #f2f2f2; color: #13293d; }
      .contents .rail { position: absolute; left: 0; top: 0; bottom: 0; width: 84px; background: rgba(255,255,255,0.72); border-right: 1px solid #d8dee5; }
      .contents .rail .brand { padding: 18px 12px; font-size: 18px; font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; color: {{ brand.primary_color }}; }
      .contents .inner { padding: 40px 54px 36px 120px; }
      .contents h2 { margin: 0 0 28px; font-size: 34px; color: {{ brand.primary_color }}; font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; }
      .toc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; }
      .toc-card .header { padding: 12px 18px; border-radius: 16px 16px 0 0; color: white; font-size: 18px; font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; }
      .toc-line { display: flex; justify-content: space-between; gap: 14px; padding: 10px 18px; border-bottom: 1px solid #cfd6dc; background: rgba(255,255,255,0.54); font-size: 13px; color: #243b53; }
      .toc-line a { color: inherit; text-decoration: none; }
      .section-opener { color: white; }
      .section-opener .hero-wrap, .section-opener .hero-wrap img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
      .section-opener .hero-wrap::after { content: ""; position: absolute; inset: 0; background: linear-gradient(90deg, rgba(240,127,19,0.86), rgba(12,74,110,0.28)); }
      .section-opener .inner { position: relative; z-index: 2; padding: 76px 58px; max-width: 430px; }
      .section-opener h2 { margin: 0 0 16px; font-size: 46px; line-height: 1.02; font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; }
      .section-opener p { margin: 0; font-size: 18px; line-height: 1.72; }
      .data-page { background: white; padding: 34px 42px 28px; }
      .data-page h2 { margin: 0 0 20px; font-size: 30px; color: {{ brand.primary_color }}; font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; }
      .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
      .metric-card { border-radius: 22px; background: #f8fbfc; padding: 16px; border: 1px solid #dbe7ec; min-height: 96px; }
      .metric-card .eyebrow { color: #61788c; font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; }
      .metric-card .value { margin-top: 10px; font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; font-size: 24px; color: {{ brand.secondary_color }}; }
      .two-col { display: grid; grid-template-columns: 1.14fr 0.86fr; gap: 22px; }
      .summary-box, .sidebar-card, .appendix-card { background: #f8fbfc; border-radius: 24px; padding: 20px 22px; border: 1px solid #dbe7ec; }
      .summary-box p, .appendix-card li { line-height: 1.75; font-size: 14px; }
      .summary-box ul, .sidebar-card ul, .appendix-card ul { padding-left: 18px; margin: 14px 0 0; }
      .sidebar-visual { border-radius: 24px; overflow: hidden; margin-bottom: 14px; background: #edf2f7; }
      .sidebar-visual img { display: block; width: 100%; height: 230px; object-fit: cover; }
      .chart-box { margin-top: 18px; }
      .chart-box img { width: 100%; display: block; }
      table { width: 100%; border-collapse: collapse; font-size: 12px; }
      th, td { padding: 8px 9px; vertical-align: top; border-bottom: 1px solid #d6e2e8; }
      th { text-align: left; color: {{ brand.secondary_color }}; }
      .appendix-page { padding: 28px 34px; background: #f3f5f7; }
      .appendix-page h2 { margin: 0 0 16px; font-size: 28px; color: {{ brand.primary_color }}; font-family: "{{ brand.font_family_headings }}", "Segoe UI", sans-serif; }
      .appendix-page .stack { display: grid; gap: 16px; }
    </style>
  </head>
  <body>
    <section class="page cover">
      <img class="hero" src="{{ visual_data_uris['cover_hero'] }}" alt="Kapak görseli" />
      <div class="cover-fade"></div>
      <div class="inner">
        <div style="width:78px;height:78px;">{{ monogram_svg | safe }}</div>
        <h1>Sürdürülebilirlik Raporu — {{ reporting_year }}</h1>
        <p>{{ company_profile.legal_name }} için ERP verileri, kanıt havuzu ve kontrollü paketleme akışı ile hazırlanan Türkçe sürdürülebilirlik raporu.</p>
        <p>{{ company_profile.sustainability_approach or company_profile.description or "" }}</p>
      </div>
      <div class="meta">
        <div>{{ tenant.name }}</div>
        <div>{{ project.name }}</div>
        <div>{{ company_profile.headquarters or "Türkiye" }}</div>
      </div>
    </section>

    <section class="page contents">
      <div class="rail"><div class="brand">{{ tenant.name }}</div></div>
      <div class="inner">
        <h2>İçindekiler</h2>
        <div class="toc-grid">
          {% for card in toc_cards %}
          <div class="toc-card">
            <div class="header" style="background: {{ card.accent_color }};">{{ card.title }}</div>
            {% for line in card.lines %}
            <div class="toc-line">
              <a href="#section-{{ line.anchor }}">{{ line.label }}</a>
              <span>{{ line.page_hint }}</span>
            </div>
            {% endfor %}
          </div>
          {% endfor %}
        </div>
      </div>
    </section>

    {% for section in section_payloads %}
    <section id="section-{{ section.section_code }}" class="page section-opener">
      <div class="hero-wrap"><img src="{{ visual_data_uris.get(section.primary_visual_slot, visual_data_uris['cover_hero']) }}" alt="{{ section.title }}" /></div>
      <div class="inner"><h2>{{ section.title }}</h2><p>{{ section.purpose }}</p></div>
    </section>
    <section class="page data-page">
      <h2>{{ section.title }}</h2>
      {% if section.metrics %}
      <div class="metric-grid">
        {% for metric in section.metrics[:4] %}
        <div class="metric-card"><div class="eyebrow">{{ metric.metric_code }}</div><div class="value">{{ metric.display_value }}</div><div>{{ metric.metric_name }}</div></div>
        {% endfor %}
      </div>
      {% endif %}
      <div class="two-col">
        <div class="summary-box">
          <p>{{ section.summary }}</p>
          <ul>{% for item in section.highlights %}<li>{{ item }}</li>{% endfor %}</ul>
          {% if section.chart_visual_slot and visual_data_uris.get(section.chart_visual_slot) %}
          <div class="chart-box"><img src="{{ visual_data_uris[section.chart_visual_slot] }}" alt="{{ section.title }} grafiği" /></div>
          {% elif section.chart_svg %}
          <div class="chart-box"><img src="{{ 'data:image/svg+xml;base64,' ~ section.chart_svg_b64 }}" alt="{{ section.title }} grafiği" /></div>
          {% endif %}
        </div>
        <div>
          <div class="sidebar-visual"><img src="{{ visual_data_uris.get(section.primary_visual_slot, visual_data_uris['cover_hero']) }}" alt="{{ section.title }}" /></div>
          <div class="sidebar-card"><strong style="color:{{ brand.secondary_color }};">Kanıt ve İzlenebilirlik</strong><ul>{% for item in section.claims[:3] %}<li>{{ item }}</li>{% endfor %}</ul></div>
        </div>
      </div>
    </section>
    {% endfor %}

    <section id="section-APPENDIX" class="page appendix-page">
      <h2>Ekler ve İzlenebilirlik</h2>
      <div class="stack">
        <div class="appendix-card">
          <strong style="color:{{ brand.secondary_color }};">Atıf Dizini</strong>
          <table><thead><tr><th>Bölüm</th><th>İddia</th><th>Kaynak</th></tr></thead><tbody>{% for item in citations %}<tr><td>{{ item.section_code }}</td><td>{{ item.statement }}</td><td>{{ item.reference }}</td></tr>{% endfor %}</tbody></table>
        </div>
        <div class="appendix-card">
          <strong style="color:{{ brand.secondary_color }};">Hesaplama Ekleri</strong>
          <table><thead><tr><th>Formül</th><th>Çıktı</th><th>Birim</th><th>İz</th></tr></thead><tbody>{% for item in calculations %}<tr><td>{{ item.formula_name }}</td><td>{{ item.output_value }}</td><td>{{ item.output_unit }}</td><td>{{ item.trace_log_ref }}</td></tr>{% endfor %}</tbody></table>
        </div>
        <div class="appendix-card"><strong style="color:{{ brand.secondary_color }};">Varsayım Kaydı</strong><ul>{% for item in assumptions %}<li>{{ item }}</li>{% endfor %}</ul></div>
      </div>
    </section>
  </body>
</html>
        """
    )

    for section in section_payloads:
        section["chart_svg_b64"] = (
            b64encode(section["chart_svg"].encode("utf-8")).decode("ascii")
            if section.get("chart_svg")
            else ""
        )

    toc_cards = _build_toc_cards(section_payloads, appendix_start_page)
    for card in toc_cards:
        for line in card["lines"]:
            if line["label"] == "Atıf ve hesaplama ekleri":
                line["anchor"] = "APPENDIX"
            else:
                line["anchor"] = next(
                    (
                        section["section_code"]
                        for section in section_payloads
                        if section["title"] == line["label"]
                    ),
                    "APPENDIX",
                )

    return template.render(
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand=brand,
        section_payloads=section_payloads,
        visual_data_uris=visual_data_uris,
        citations=citations,
        calculations=calculations,
        assumptions=assumptions,
        monogram_svg=_build_monogram_svg(tenant.name, brand),
        reporting_year=max((metric["period_key"] for section in section_payloads for metric in section["metrics"]), default="2025"),
        toc_cards=toc_cards,
    )


def _ensure_reportlab_fonts() -> tuple[str, str]:
    regular_name = "ReportFactoryVera"
    bold_name = "ReportFactoryVeraBold"
    registered = set(pdfmetrics.getRegisteredFontNames())
    if regular_name in registered and bold_name in registered:
        return regular_name, bold_name

    fonts_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    regular_path = fonts_dir / "Vera.ttf"
    bold_path = fonts_dir / "VeraBd.ttf"
    pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
    pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
    return regular_name, bold_name


def _draw_paragraph(
    pdf: pdf_canvas.Canvas,
    *,
    text: str,
    x: float,
    y_top: float,
    width: float,
    style: ParagraphStyle,
) -> float:
    paragraph = Paragraph(escape(text).replace("\n", "<br/>"), style)
    _, height = paragraph.wrap(width, PAGE_HEIGHT)
    paragraph.drawOn(pdf, x, y_top - height)
    return y_top - height


def _set_fill_alpha_safe(pdf: pdf_canvas.Canvas, alpha: float) -> None:
    try:
        pdf.setFillAlpha(alpha)
    except Exception:
        pass


def _draw_cover_page(
    pdf: pdf_canvas.Canvas,
    *,
    tenant: Tenant,
    project: Project,
    company_profile: CompanyProfile,
    brand: BrandKit,
    hero_bytes: bytes,
    heading_font: str,
    body_font: str,
) -> None:
    primary = _hex_color(brand.primary_color, "#f07f13")
    pdf.setFillColor(primary)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.drawImage(ImageReader(BytesIO(hero_bytes)), 350, 0, width=PAGE_WIDTH - 350, height=PAGE_HEIGHT, mask="auto")
    pdf.saveState()
    _set_fill_alpha_safe(pdf, 0.88)
    pdf.setFillColor(primary)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.restoreState()

    pdf.setFillColor(colors.white)
    pdf.setFont(heading_font, 20)
    pdf.drawString(42, PAGE_HEIGHT - 54, tenant.name)
    pdf.setFont(heading_font, 34)
    pdf.drawString(42, PAGE_HEIGHT - 132, "SÜRDÜRÜLEBİLİRLİK")
    pdf.drawString(42, PAGE_HEIGHT - 176, "RAPORU")
    pdf.drawString(268, PAGE_HEIGHT - 176, "— 2025")

    body_style = ParagraphStyle(
        "cover-body",
        fontName=body_font,
        fontSize=14,
        leading=22,
        textColor=colors.white,
    )
    _draw_paragraph(
        pdf,
        text=(
            f"{company_profile.legal_name} için ERP verileri, kanıt havuzu ve kontrollü paketleme akışı "
            "ile hazırlanan Türkçe sürdürülebilirlik raporu."
        ),
        x=42,
        y_top=PAGE_HEIGHT - 248,
        width=280,
        style=body_style,
    )
    _draw_paragraph(
        pdf,
        text=company_profile.sustainability_approach or company_profile.description or "",
        x=42,
        y_top=PAGE_HEIGHT - 352,
        width=280,
        style=body_style,
    )

    pdf.setFont(body_font, 12)
    pdf.drawString(42, 56, project.name)
    pdf.drawString(42, 38, company_profile.headquarters or "Türkiye")
    pdf.showPage()


def _draw_contents_page(
    pdf: pdf_canvas.Canvas,
    *,
    tenant: Tenant,
    toc_cards: list[dict[str, Any]],
    heading_font: str,
    body_font: str,
) -> None:
    pdf.setFillColor(colors.HexColor("#f2f2f2"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, 84, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#d8dee5"))
    pdf.line(84, 0, 84, PAGE_HEIGHT)

    pdf.setFillColor(colors.HexColor("#13293d"))
    pdf.setFont(heading_font, 18)
    pdf.drawString(18, PAGE_HEIGHT - 34, tenant.name)
    pdf.setFont(heading_font, 32)
    pdf.setFillColor(colors.HexColor("#f07f13"))
    pdf.drawString(120, PAGE_HEIGHT - 62, "İçindekiler")

    card_width = 210
    gap = 20
    start_x = 120
    start_y = PAGE_HEIGHT - 118
    for index, card in enumerate(toc_cards):
        x = start_x + (index % 3) * (card_width + gap)
        y = start_y - (index // 3) * 220
        accent = _hex_color(str(card["accent_color"]), "#f07f13")

        pdf.setFillColor(accent)
        pdf.roundRect(x, y, card_width, 32, 10, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setFont(heading_font, 16)
        pdf.drawString(x + 16, y + 10, str(card["title"]))

        line_y = y - 18
        for line in card["lines"]:
            pdf.setFont(body_font, 11)
            pdf.setFillColor(colors.HexColor("#243b53"))
            pdf.drawString(x + 10, line_y, str(line["label"]))
            pdf.drawRightString(x + card_width - 10, line_y, str(line["page_hint"]))
            pdf.setStrokeColor(colors.HexColor("#cfd6dc"))
            pdf.line(x + 8, line_y - 10, x + card_width - 8, line_y - 10)
            line_y -= 28
    pdf.showPage()


def _draw_chart_on_canvas(
    pdf: pdf_canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    values: list[tuple[str, float]],
    brand: BrandKit,
    body_font: str,
    heading_font: str,
) -> None:
    if not values:
        return
    pdf.setFillColor(colors.HexColor("#f7fafc"))
    pdf.roundRect(x, y, width, height, 22, fill=1, stroke=0)
    pdf.setFont(heading_font, 14)
    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.drawString(x + 18, y + height - 24, "Grafik özeti")

    baseline = y + 32
    max_value = max(value for _, value in values) or 1.0
    slot_width = width / max(1, len(values))
    for index, (label, value) in enumerate(values):
        bar_x = x + 24 + (index * slot_width)
        bar_width = max(18.0, slot_width - 30)
        bar_height = max(12.0, (value / max_value) * (height - 92))
        fill = _hex_color(brand.primary_color if index == len(values) - 1 else brand.secondary_color, "#0c4a6e")
        pdf.setFillColor(fill)
        pdf.roundRect(bar_x, baseline, bar_width, bar_height, 10, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#102a43"))
        pdf.setFont(body_font, 9)
        pdf.drawCentredString(bar_x + (bar_width / 2), baseline - 14, label)
        pdf.drawCentredString(bar_x + (bar_width / 2), baseline + bar_height + 8, f"{value:g}")


def _draw_section_opener_page(
    pdf: pdf_canvas.Canvas,
    *,
    section: dict[str, Any],
    brand: BrandKit,
    hero_bytes: bytes,
    heading_font: str,
    body_font: str,
) -> None:
    pdf.drawImage(ImageReader(BytesIO(hero_bytes)), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, mask="auto")
    pdf.saveState()
    _set_fill_alpha_safe(pdf, 0.84)
    pdf.setFillColor(_hex_color(brand.primary_color, "#f07f13"))
    pdf.rect(0, 0, PAGE_WIDTH * 0.55, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.restoreState()
    pdf.setFillColor(colors.white)
    pdf.setFont(heading_font, 34)
    pdf.drawString(52, PAGE_HEIGHT - 100, str(section["title"]))
    opener_style = ParagraphStyle(
        "opener",
        fontName=body_font,
        fontSize=15,
        leading=24,
        textColor=colors.white,
    )
    _draw_paragraph(
        pdf,
        text=str(section["purpose"]),
        x=52,
        y_top=PAGE_HEIGHT - 148,
        width=320,
        style=opener_style,
    )
    pdf.showPage()


def _draw_section_data_page(
    pdf: pdf_canvas.Canvas,
    *,
    section: dict[str, Any],
    brand: BrandKit,
    hero_bytes: bytes,
    heading_font: str,
    body_font: str,
) -> None:
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(_hex_color(brand.primary_color, "#f07f13"))
    pdf.setFont(heading_font, 26)
    pdf.drawString(36, PAGE_HEIGHT - 48, str(section["title"]))

    metrics = section["metrics"][:4]
    for index, metric in enumerate(metrics):
        x = 36 + (index * 195)
        y = PAGE_HEIGHT - 154
        pdf.setFillColor(colors.HexColor("#f8fbfc"))
        pdf.roundRect(x, y, 176, 88, 18, fill=1, stroke=0)
        pdf.setStrokeColor(colors.HexColor("#dbe7ec"))
        pdf.roundRect(x, y, 176, 88, 18, fill=0, stroke=1)
        pdf.setFillColor(colors.HexColor("#61788c"))
        pdf.setFont(body_font, 8)
        pdf.drawString(x + 14, y + 68, str(metric["metric_code"]))
        pdf.setFillColor(_hex_color(brand.secondary_color, "#0c4a6e"))
        pdf.setFont(heading_font, 18)
        pdf.drawString(x + 14, y + 40, str(metric["display_value"]))
        pdf.setFillColor(colors.HexColor("#243b53"))
        pdf.setFont(body_font, 10)
        pdf.drawString(x + 14, y + 18, str(metric["metric_name"])[:28])

    summary_style = ParagraphStyle(
        "summary",
        fontName=body_font,
        fontSize=12,
        leading=19,
        textColor=colors.HexColor("#243b53"),
    )
    highlight_style = ParagraphStyle(
        "highlight",
        fontName=body_font,
        fontSize=11,
        leading=17,
        textColor=colors.HexColor("#243b53"),
    )

    pdf.setFillColor(colors.HexColor("#f8fbfc"))
    pdf.roundRect(36, 96, 450, 264, 24, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#dbe7ec"))
    pdf.roundRect(36, 96, 450, 264, 24, fill=0, stroke=1)
    current_y = PAGE_HEIGHT - 194
    current_y = _draw_paragraph(
        pdf,
        text=str(section["summary"]),
        x=56,
        y_top=current_y,
        width=410,
        style=summary_style,
    ) - 12
    for item in section["highlights"][:4]:
        current_y = _draw_paragraph(
            pdf,
            text=f"- {item}",
            x=56,
            y_top=current_y,
            width=410,
            style=highlight_style,
        ) - 6

    _draw_chart_on_canvas(
        pdf,
        x=56,
        y=118,
        width=390,
        height=96,
        values=section["chart_values"][:4],
        brand=brand,
        body_font=body_font,
        heading_font=heading_font,
    )

    pdf.drawImage(ImageReader(BytesIO(hero_bytes)), 522, 196, width=264, height=164, mask="auto")
    pdf.setFillColor(colors.HexColor("#f8fbfc"))
    pdf.roundRect(522, 96, 264, 84, 20, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#dbe7ec"))
    pdf.roundRect(522, 96, 264, 84, 20, fill=0, stroke=1)
    pdf.setFillColor(_hex_color(brand.secondary_color, "#0c4a6e"))
    pdf.setFont(heading_font, 13)
    pdf.drawString(540, 154, "Kanıt ve İzlenebilirlik")
    sidebar_y = 136
    pdf.setFont(body_font, 10)
    pdf.setFillColor(colors.HexColor("#243b53"))
    for item in section["claims"][:3]:
        pdf.drawString(540, sidebar_y, f"• {item[:36]}")
        sidebar_y -= 18
    pdf.showPage()


def _chunked(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _draw_appendix_page(
    pdf: pdf_canvas.Canvas,
    *,
    title: str,
    columns: list[str],
    rows: list[list[str]],
    brand: BrandKit,
    heading_font: str,
    body_font: str,
) -> None:
    pdf.setFillColor(colors.HexColor("#f3f5f7"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(_hex_color(brand.primary_color, "#f07f13"))
    pdf.setFont(heading_font, 24)
    pdf.drawString(32, PAGE_HEIGHT - 44, title)
    data = [columns, *rows]
    width_map = {
        2: [220, 520],
        3: [140, 270, 300],
        4: [160, 120, 100, 330],
    }
    table = Table(data, colWidths=width_map.get(len(columns), None))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _hex_color(brand.secondary_color, "#0c4a6e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), heading_font),
                ("FONTNAME", (0, 1), (-1, -1), body_font),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d6e2e8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbfc")]),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    table.wrapOn(pdf, PAGE_WIDTH - 64, PAGE_HEIGHT - 100)
    table.drawOn(pdf, 32, 76)
    pdf.showPage()


def _render_reportlab_pdf(
    *,
    tenant: Tenant,
    project: Project,
    company_profile: CompanyProfile,
    brand: BrandKit,
    section_payloads: list[dict[str, Any]],
    visual_data: dict[str, tuple[bytes, str]],
    citations: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    assumptions: list[str],
) -> bytes:
    body_font, heading_font = _ensure_reportlab_fonts()
    buffer = BytesIO()
    pdf = pdf_canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    pdf.setTitle(f"{project.name} Sürdürülebilirlik Raporu")
    pdf.setAuthor("Veni AI Sustainability Cockpit")
    pdf.setSubject(f"{project.name} sürdürülebilirlik raporu")
    pdf.setCreator(tenant.name)

    cover_hero = visual_data.get("cover_hero")
    cover_bytes = cover_hero[0] if cover_hero else _generate_fallback_visual(title="Kapak", brand=brand, accent_label="COVER")
    _draw_cover_page(
        pdf,
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand=brand,
        hero_bytes=cover_bytes,
        heading_font=heading_font,
        body_font=body_font,
    )

    appendix_start_page = 3 + (len(section_payloads) * 2)
    toc_cards = _build_toc_cards(section_payloads, appendix_start_page)
    _draw_contents_page(
        pdf,
        tenant=tenant,
        toc_cards=toc_cards,
        heading_font=heading_font,
        body_font=body_font,
    )

    for section in section_payloads:
        hero_slot = section["primary_visual_slot"]
        hero_bytes = visual_data.get(hero_slot, (cover_bytes, "image/png"))[0]
        _draw_section_opener_page(
            pdf,
            section=section,
            brand=brand,
            hero_bytes=hero_bytes,
            heading_font=heading_font,
            body_font=body_font,
        )
        _draw_section_data_page(
            pdf,
            section=section,
            brand=brand,
            hero_bytes=hero_bytes,
            heading_font=heading_font,
            body_font=body_font,
        )

    citation_rows = [
        [
            str(item["section_code"]),
            str(item["statement"])[:90],
            str(item["reference"])[:120],
        ]
        for item in citations
    ] or [["-", "Atıf bulunamadı", "-"]]
    for chunk in _chunked(
        [{"col1": row[0], "col2": row[1], "col3": row[2]} for row in citation_rows],
        12,
    ):
        rows = [[item["col1"], item["col2"], item["col3"]] for item in chunk]
        _draw_appendix_page(
            pdf,
            title="Atıf Dizini",
            columns=["Bölüm", "İddia", "Kaynak"],
            rows=rows,
            brand=brand,
            heading_font=heading_font,
            body_font=body_font,
        )

    calculation_rows = [
        [
            str(item["formula_name"]),
            str(item["output_value"]),
            f"{item['output_unit']} | {item['trace_log_ref']}",
        ]
        for item in calculations
    ] or [["-", "-", "Hesaplama ek kaydı yok"]]
    for chunk in _chunked(
        [{"col1": row[0], "col2": row[1], "col3": row[2]} for row in calculation_rows],
        12,
    ):
        rows = [[item["col1"], item["col2"], item["col3"]] for item in chunk]
        _draw_appendix_page(
            pdf,
            title="Hesaplama Ekleri",
            columns=["Formül", "Çıktı", "İz"],
            rows=rows,
            brand=brand,
            heading_font=heading_font,
            body_font=body_font,
        )

    assumption_rows = [["Varsayım", item, "-"] for item in assumptions] or [["-", "-", "-"]]
    _draw_appendix_page(
        pdf,
        title="Varsayım Kaydı",
        columns=["Tür", "Açıklama", "Not"],
        rows=assumption_rows,
        brand=brand,
        heading_font=heading_font,
        body_font=body_font,
    )

    pdf.save()
    return buffer.getvalue()


def _outline_entries(section_payloads: list[dict[str, Any]], appendix_start_page: int) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = [("Kapak", 0), ("İçindekiler", 1)]
    page_index = 2
    for section in section_payloads:
        entries.append((str(section["title"]), page_index))
        page_index += 2
    entries.append(("Ekler ve İzlenebilirlik", appendix_start_page - 1))
    return entries


def _with_pdf_metadata_and_outline(
    payload: bytes,
    *,
    tenant: Tenant,
    project: Project,
    title: str,
    outline_entries: list[tuple[str, int]],
) -> bytes:
    reader = PdfReader(BytesIO(payload))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": title,
            "/Author": "Veni AI Sustainability Cockpit",
            "/Subject": f"{project.name} sustainability report",
            "/Creator": tenant.name,
        }
    )
    for outline_title, page_index in outline_entries:
        if page_index < 0 or page_index >= len(reader.pages):
            continue
        try:
            writer.add_outline_item(outline_title, page_index)
        except Exception:
            continue
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _render_pdf_document(
    *,
    tenant: Tenant,
    project: Project,
    company_profile: CompanyProfile,
    brand: BrandKit,
    section_payloads: list[dict[str, Any]],
    visual_data: dict[str, tuple[bytes, str]],
    visual_data_uris: dict[str, str],
    citations: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    assumptions: list[str],
) -> RenderedPdf:
    appendix_start_page = 3 + (len(section_payloads) * 2)
    outline_entries = _outline_entries(section_payloads, appendix_start_page)
    HTML = _load_weasyprint_html()
    if HTML is not None:
        try:
            html = _render_html_report(
                tenant=tenant,
                project=project,
                company_profile=company_profile,
                brand=brand,
                section_payloads=section_payloads,
                visual_data_uris=visual_data_uris,
                citations=citations,
                calculations=calculations,
                assumptions=assumptions,
            )
            pdf_bytes = HTML(string=html, base_url=str(settings.repo_root)).write_pdf()
            pdf_bytes = _with_pdf_metadata_and_outline(
                pdf_bytes,
                tenant=tenant,
                project=project,
                title=f"{project.name} Sürdürülebilirlik Raporu",
                outline_entries=outline_entries,
            )
            return RenderedPdf(
                payload=pdf_bytes,
                renderer="weasyprint",
                page_count=len(PdfReader(BytesIO(pdf_bytes)).pages),
            )
        except Exception:
            pass

    fallback_bytes = _render_reportlab_pdf(
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand=brand,
        section_payloads=section_payloads,
        visual_data=visual_data,
        citations=citations,
        calculations=calculations,
        assumptions=assumptions,
    )
    fallback_bytes = _with_pdf_metadata_and_outline(
        fallback_bytes,
        tenant=tenant,
        project=project,
        title=f"{project.name} Sürdürülebilirlik Raporu",
        outline_entries=outline_entries,
    )
    return RenderedPdf(
        payload=fallback_bytes,
        renderer="reportlab_fallback",
        page_count=len(PdfReader(BytesIO(fallback_bytes)).pages),
    )


def _upsert_artifact(
    *,
    db: Session,
    blob_storage: BlobStorageService,
    package: ReportPackage,
    report_run: ReportRun,
    artifact_type: str,
    content_type: str,
    payload: bytes,
    filename: str,
    metadata: dict[str, Any] | None = None,
) -> ReportArtifact:
    storage_uri = blob_storage.upload_bytes(
        payload=payload,
        blob_name=f"{package.tenant_id}/{package.project_id}/packages/{package.id}/{filename}",
        content_type=content_type,
        container=settings.azure_storage_container_artifacts,
    )
    artifact = db.scalar(
        select(ReportArtifact).where(
            ReportArtifact.report_run_id == report_run.id,
            ReportArtifact.artifact_type == artifact_type,
        )
    )
    checksum = f"sha256:{sha256(payload).hexdigest()}"
    if artifact is None:
        artifact = ReportArtifact(
            tenant_id=report_run.tenant_id,
            project_id=report_run.project_id,
            report_run_id=report_run.id,
            report_package_id=package.id,
            artifact_type=artifact_type,
            filename=filename,
            content_type=content_type,
            storage_uri=storage_uri,
            size_bytes=len(payload),
            checksum=checksum,
            artifact_metadata_json=metadata or {},
        )
        db.add(artifact)
        db.flush()
        return artifact
    artifact.report_package_id = package.id
    artifact.filename = filename
    artifact.content_type = content_type
    artifact.storage_uri = storage_uri
    artifact.size_bytes = len(payload)
    artifact.checksum = checksum
    artifact.artifact_metadata_json = metadata or {}
    db.flush()
    return artifact


def build_package_status_payload(*, db: Session, report_run: ReportRun) -> dict[str, Any]:
    package = get_report_package(db=db, report_run_id=report_run.id)
    return {
        "run_id": report_run.id,
        "package_job_id": package.id if package else None,
        "package_status": package.status if package else report_run.package_status,
        "current_stage": package.current_stage if package else None,
        "report_quality_score": report_run.report_quality_score,
        "visual_generation_status": report_run.visual_generation_status,
        "artifacts": [_to_artifact_response_payload(item) for item in list_run_artifacts(db=db, report_run_id=report_run.id)],
        "stage_history": _serialize_stage_history(package) if package else [],
        "generated_at_utc": _utcnow().isoformat(),
    }


def _resolve_report_context(
    *,
    db: Session,
    report_run: ReportRun,
    tenant: Tenant,
    project: Project,
) -> tuple[CompanyProfile, BrandKit, ReportBlueprint]:
    company_profile = db.get(CompanyProfile, report_run.company_profile_id) if report_run.company_profile_id else None
    brand = db.get(BrandKit, report_run.brand_kit_id) if report_run.brand_kit_id else None
    blueprint = db.scalar(
        select(ReportBlueprint).where(
            ReportBlueprint.project_id == report_run.project_id,
            ReportBlueprint.version == (report_run.report_blueprint_version or settings.report_factory_default_blueprint_version),
        )
    )

    if company_profile is not None and brand is not None and blueprint is not None:
        return company_profile, brand, blueprint

    company_profile, brand, blueprint, _ = ensure_project_report_context(
        db=db,
        tenant=tenant,
        project=project,
    )
    report_run.company_profile_id = company_profile.id
    report_run.brand_kit_id = brand.id
    report_run.report_blueprint_version = blueprint.version
    db.flush()
    return company_profile, brand, blueprint


def _resolve_selected_integrations(
    *,
    db: Session,
    report_run: ReportRun,
) -> list[IntegrationConfig]:
    connector_scope = report_run.connector_scope or []
    query = select(IntegrationConfig).where(
        IntegrationConfig.project_id == report_run.project_id,
        IntegrationConfig.tenant_id == report_run.tenant_id,
        IntegrationConfig.status == "active",
    )
    if connector_scope:
        query = query.where(IntegrationConfig.connector_type.in_(connector_scope))
    integrations = db.scalars(query.order_by(IntegrationConfig.connector_type.asc())).all()
    if not integrations:
        raise ReportPackageGenerationError("Run için aktif entegrasyon kapsamı bulunamadı.")
    return integrations


def ensure_report_package(
    *,
    db: Session,
    report_run: ReportRun,
    blob_storage: BlobStorageService | None = None,
) -> PackageArtifacts:
    tenant = db.get(Tenant, report_run.tenant_id)
    project = db.get(Project, report_run.project_id)
    if tenant is None or project is None:
        raise ReportPackageGenerationError("Run tenant/project bağlantıları eksik.")

    company_profile, brand, blueprint = _resolve_report_context(
        db=db,
        report_run=report_run,
        tenant=tenant,
        project=project,
    )
    blob = blob_storage or get_blob_storage_service()
    package = get_report_package(db=db, report_run_id=report_run.id)
    if package is None:
        package = ReportPackage(
            tenant_id=report_run.tenant_id,
            project_id=report_run.project_id,
            report_run_id=report_run.id,
            status="queued",
            current_stage="queued",
            stage_history_json=[],
            started_at=_utcnow(),
        )
        db.add(package)
        db.flush()

    if package.status == "completed":
        return PackageArtifacts(package=package, artifacts=list_run_artifacts(db=db, report_run_id=report_run.id))

    blueprint_sections = blueprint.blueprint_json.get("sections", []) if isinstance(blueprint.blueprint_json, dict) else []
    if not isinstance(blueprint_sections, list) or not blueprint_sections:
        raise ReportPackageGenerationError("Blueprint section tanımı bulunamadı.")

    integrations = _resolve_selected_integrations(db=db, report_run=report_run)
    latest_jobs: dict[str, ConnectorSyncJob] = {}
    for integration in integrations:
        job = db.scalar(
            select(ConnectorSyncJob)
            .where(
                ConnectorSyncJob.integration_config_id == integration.id,
                ConnectorSyncJob.project_id == report_run.project_id,
            )
            .order_by(ConnectorSyncJob.completed_at.desc(), ConnectorSyncJob.created_at.desc())
        )
        if job is None or job.status != "completed":
            raise ReportPackageGenerationError(
                f"{integration.display_name} için başarılı sync işi bulunamadı. Publish öncesi senkronizasyon gerekli."
            )
        latest_jobs[integration.connector_type] = job

    latest_completed_jobs = [job for job in latest_jobs.values() if job.completed_at is not None]
    if not latest_completed_jobs:
        raise ReportPackageGenerationError("Başarılı connector sync işi bulunamadı.")
    latest_sync_job = max(latest_completed_jobs, key=lambda job: job.completed_at or job.created_at)
    package.latest_sync_job_id = latest_sync_job.id
    report_run.latest_sync_at = max(job.completed_at for job in latest_completed_jobs if job.completed_at is not None)

    fact_query = select(CanonicalFact).where(CanonicalFact.project_id == report_run.project_id)
    if report_run.connector_scope:
        fact_query = fact_query.where(CanonicalFact.source_system.in_(report_run.connector_scope))
    facts = db.scalars(fact_query.order_by(CanonicalFact.metric_code.asc(), CanonicalFact.period_key.desc())).all()
    if not facts:
        raise ReportPackageGenerationError("Canonical fact havuzu boş. Publish öncesi connector sync gerekli.")

    package.status = "running"
    report_run.package_status = "running"
    db.flush()

    current_stage = "sync"
    try:
        metric_bucket = _metric_bucket(facts)
        section_payloads: list[dict[str, Any]] = []
        claim_domains: dict[str, list[str]] = {}
        citation_index: list[dict[str, Any]] = []
        calculations: list[dict[str, Any]] = []
        visual_data: dict[str, tuple[bytes, str]] = {}
        visual_data_uris: dict[str, str] = {}
        assumptions = [
            "AI görseller yalnızca dekoratif veya konsept kullanım içindir; performans iddiası taşımaz.",
            "Canlı ERP verisi bulunmayan alanlarda proje bootstrap profili ve seçili connector scope kullanılmıştır.",
            "Anlatı yalnızca canonical fact, company profile ve PASS claim havuzundan türetilmiştir.",
        ]

        for current_stage in PACKAGE_STAGES:
            _append_stage(package, current_stage, "running")

            if current_stage == "normalize":
                _ensure_snapshot_rows(db=db, report_run=report_run, facts=facts)

            elif current_stage == "outline":
                claim_domains, citation_index, calculations = _build_claim_domains(
                    db=db,
                    report_run_id=report_run.id,
                )
                section_payloads = [
                    _build_section_payload(
                        company_profile=company_profile,
                        brand=brand,
                        section_definition=section_definition,
                        metric_bucket=metric_bucket,
                        claim_domains=claim_domains,
                    )
                    for section_definition in blueprint_sections
                ]

            elif current_stage == "charts_images":
                report_run.visual_generation_status = "running"
                for section in section_payloads:
                    for visual_slot in section["visual_slots"]:
                        if visual_slot in visual_data:
                            continue
                        lower_slot = visual_slot.lower()
                        if any(token in lower_slot for token in ("chart", "matrix", "grid")):
                            if "matrix" in lower_slot:
                                svg = _build_matrix_svg(title=section["title"], metrics=section["metrics"], brand=brand)
                            elif "grid" in lower_slot:
                                svg = _build_grid_svg(title=section["title"], metrics=section["metrics"], brand=brand)
                            else:
                                svg = section["chart_svg"] or _build_chart_svg(
                                    title=section["title"],
                                    values=section["chart_values"],
                                    brand=brand,
                                )
                            payload, content_type = _upload_visual_svg_asset(
                                db=db,
                                blob_storage=blob,
                                package=package,
                                visual_slot=visual_slot,
                                title=section["title"],
                                svg=svg,
                            )
                        else:
                            payload, content_type = _upload_visual_image_asset(
                                db=db,
                                blob_storage=blob,
                                package=package,
                                brand=brand,
                                visual_slot=visual_slot,
                                title=section["title"],
                                prompt_text=(
                                    f"Dekoratif kurumsal sürdürülebilirlik görseli; {section['title']} bölümü için, "
                                    "temsilî, profesyonel ve marka uyumlu; gerçek operasyon kanıtı gibi görünmeyen."
                                ),
                            )
                        visual_data[visual_slot] = (payload, content_type)
                        visual_data_uris[visual_slot] = _to_data_uri(payload, content_type)

                if "cover_hero" not in visual_data:
                    payload, content_type = _upload_visual_image_asset(
                        db=db,
                        blob_storage=blob,
                        package=package,
                        brand=brand,
                        visual_slot="cover_hero",
                        title="Kurumsal Sürdürülebilirlik",
                        prompt_text=(
                            "Dekoratif kurumsal kapak görseli, turuncu ve mavi tonlarda, "
                            "endüstriyel sürdürülebilirlik temalı, gerçek kanıt iddiası taşımayan."
                        ),
                    )
                    visual_data["cover_hero"] = (payload, content_type)
                    visual_data_uris["cover_hero"] = _to_data_uri(payload, content_type)
                report_run.visual_generation_status = "completed"

                for section in section_payloads:
                    section["chart_visual_slot"] = next(
                        (slot for slot in section["visual_slots"] if any(token in slot.lower() for token in ("chart", "matrix", "grid"))),
                        None,
                    )

            elif current_stage == "compose":
                rendered_pdf = _render_pdf_document(
                    tenant=tenant,
                    project=project,
                    company_profile=company_profile,
                    brand=brand,
                    section_payloads=section_payloads,
                    visual_data=visual_data,
                    visual_data_uris=visual_data_uris,
                    citations=citation_index,
                    calculations=calculations,
                    assumptions=assumptions,
                )

            _update_stage(package, current_stage, "completed")

        coverage_matrix = [
            {
                "section_code": section["section_code"],
                "title": section["title"],
                "required_metrics": section["required_metrics"],
                "metric_count": len(section["metrics"]),
                "claim_count": len(section["claims"]),
                "appendix_refs": section["appendix_refs"],
            }
            for section in section_payloads
        ]
        visual_manifest = [
            {
                "visual_slot": row.visual_slot,
                "source_type": row.source_type,
                "decorative_ai_generated": row.decorative_ai_generated,
                "storage_uri": row.storage_uri,
                "status": row.status,
                "content_type": row.content_type,
            }
            for row in db.scalars(
                select(ReportVisualAsset).where(ReportVisualAsset.report_package_id == package.id)
            ).all()
        ]

        confidence_values = [fact.confidence_score or 0.9 for fact in facts]
        report_quality_score = round(
            min(
                100.0,
                ((sum(confidence_values) / len(confidence_values)) * 55)
                + (min(1.0, len(citation_index) / max(1, len(section_payloads) * 2)) * 25)
                + (min(1.0, len({fact.metric_code for fact in facts}) / max(1, len(section_payloads) * 2)) * 20),
            ),
            2,
        )

        report_run.report_quality_score = report_quality_score
        report_run.package_status = "completed"
        package.status = "completed"
        package.current_stage = "controlled_publish"
        package.package_quality_score = report_quality_score
        package.summary_json = {
            "section_count": len(section_payloads),
            "citation_count": len(citation_index),
            "visual_count": len(visual_manifest),
            "renderer": rendered_pdf.renderer,
            "page_count": rendered_pdf.page_count,
        }
        package.completed_at = _utcnow()

        artifact_metadata = {
            "package_id": package.id,
            "report_quality_score": report_quality_score,
            "page_count": rendered_pdf.page_count,
            "renderer": rendered_pdf.renderer,
            "blueprint_version": blueprint.version,
        }

        artifacts = [
            _upsert_artifact(
                db=db,
                blob_storage=blob,
                package=package,
                report_run=report_run,
                artifact_type=artifact_type,
                content_type=content_type,
                payload=payload,
                filename=_artifact_filename(project, report_run, artifact_type, extension),
                metadata=metadata,
            )
            for artifact_type, content_type, payload, extension, metadata in [
                (
                    REPORT_PDF_ARTIFACT_TYPE,
                    "application/pdf",
                    rendered_pdf.payload,
                    "pdf",
                    artifact_metadata,
                ),
                (
                    VISUAL_MANIFEST_ARTIFACT_TYPE,
                    "application/json",
                    json.dumps(visual_manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                    "json",
                    {"package_id": package.id, "visual_count": len(visual_manifest)},
                ),
                (
                    CITATION_INDEX_ARTIFACT_TYPE,
                    "application/json",
                    json.dumps(citation_index, ensure_ascii=False, indent=2).encode("utf-8"),
                    "json",
                    {"package_id": package.id, "citation_count": len(citation_index)},
                ),
                (
                    CALCULATION_APPENDIX_ARTIFACT_TYPE,
                    "application/json",
                    json.dumps(calculations, ensure_ascii=False, indent=2).encode("utf-8"),
                    "json",
                    {"package_id": package.id, "calculation_count": len(calculations)},
                ),
                (
                    COVERAGE_MATRIX_ARTIFACT_TYPE,
                    "application/json",
                    json.dumps(coverage_matrix, ensure_ascii=False, indent=2).encode("utf-8"),
                    "json",
                    {"package_id": package.id, "section_count": len(section_payloads)},
                ),
                (
                    ASSUMPTION_REGISTER_ARTIFACT_TYPE,
                    "application/json",
                    json.dumps(assumptions, ensure_ascii=False, indent=2).encode("utf-8"),
                    "json",
                    {"package_id": package.id, "assumption_count": len(assumptions)},
                ),
            ]
        ]
        db.flush()
        return PackageArtifacts(package=package, artifacts=artifacts)

    except Exception as exc:
        package.error_message = str(exc)
        package.completed_at = _utcnow()
        report_run.package_status = "failed"
        report_run.visual_generation_status = (
            report_run.visual_generation_status if report_run.visual_generation_status != "running" else "failed"
        )
        _update_stage(package, current_stage, "failed", str(exc))
        db.flush()
        raise
