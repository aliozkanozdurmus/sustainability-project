# Bu servis, report_factory akisindaki uygulama mantigini tek yerde toplar.

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
from app.services.report_context import build_report_factory_readiness, ensure_project_report_context


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

CONNECTOR_LABELS_TR = {
    "sap_odata": "SAP / OData",
    "logo_tiger_sql_view": "Logo Tiger / SQL View",
    "netsis_rest": "Netsis / REST",
}

METRIC_NAME_OVERRIDES = {
    "BOARD_OVERSIGHT_COVERAGE": "Yönetim Kurulu Gözetim Kapsamı",
    "E_SCOPE2_TCO2E": "Scope 2 Emisyonu",
    "E_SCOPE2_TCO2E_PREV": "Önceki Yıl Scope 2 Emisyonu",
    "ENERGY_INTENSITY_REDUCTION": "Enerji Yoğunluğu İyileşmesi",
    "HIGH_RISK_SUPPLIER_SCREENING": "Yüksek Riskli Tedarikçi Taraması",
    "LTIFR": "Kayıp Günlü İş Kazası Frekansı",
    "LTIFR_PREV": "Önceki Yıl Kayıp Günlü İş Kazası Frekansı",
    "MATERIAL_TOPIC_COUNT": "Öncelikli Konu Sayısı",
    "RENEWABLE_ELECTRICITY_SHARE": "Yenilenebilir Elektrik Payı",
    "STAKEHOLDER_ENGAGEMENT_TOUCHPOINTS": "Paydaş Etkileşim Teması",
    "SUPPLIER_COVERAGE": "Tedarikçi Kod Kapsamı",
    "SUSTAINABILITY_COMMITTEE_MEETINGS": "Sürdürülebilirlik Komitesi Toplantıları",
    "WORKFORCE_HEADCOUNT": "Çalışan Sayısı",
}

UNIT_LABEL_OVERRIDES = {
    "employee": "kişi",
    "count": "adet",
    "rate": "oran",
    "tCO2e": "tCO2e",
    "%": "%",
}

EVIDENCE_LABELS = {
    "company_profile": "Kurumsal profil girdileri",
    "energy_report": "Enerji ve emisyon kanıt paketi",
    "governance_pack": "Yönetişim ve risk kanıt paketi",
    "materiality_summary": "Çifte önemlilik ve paydaş çıktıları",
    "social_report": "Sosyal performans ve tedarik zinciri çıktıları",
}

SECTION_TOPIC_LINES = {
    "CEO_MESSAGE": ["Yönetim perspektifi", "Raporlama yaklaşımı", "Kontrollü yayın ilkeleri"],
    "COMPANY_PROFILE": ["Operasyon ölçeği", "Kurumsal konum", "Faaliyet ağı"],
    "GOVERNANCE": ["Kurul gözetimi", "Komite ritmi", "Risk entegrasyonu"],
    "DOUBLE_MATERIALITY": ["Etki önemliliği", "Finansal önemlilik", "Paydaş diyaloğu"],
    "ENVIRONMENT": ["Emisyon takibi", "Enerji verimliliği", "Yenilenebilir payı"],
    "SOCIAL": ["İSG performansı", "Çalışan ölçeği", "Tedarik zinciri kontrolleri"],
}

VISUAL_SCENE_LABELS = {
    "cover": "Kurumsal sürdürülebilirlik kapağı",
    "company": "Şirket profili ve operasyon ağı",
    "governance": "Yönetişim ve karar mimarisi",
    "materiality": "Çifte önemlilik matrisi",
    "environment": "Enerji ve emisyon performansı",
    "social": "İnsan, güvenlik ve tedarik zinciri",
    "default": "Sürdürülebilirlik rapor görseli",
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


@dataclass(frozen=True)
class ImageGenerationPayload:
    payload: bytes
    deployment: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "report"


def _to_data_uri(payload: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{b64encode(payload).decode('ascii')}"


def _resolve_brand_mark_uri(tenant: Tenant, brand: BrandKit) -> str:
    logo_uri = (brand.logo_uri or "").strip()
    if logo_uri:
        return logo_uri
    return _to_data_uri(
        _build_monogram_svg(tenant.name, brand).encode("utf-8"),
        "image/svg+xml",
    )


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


def ensure_report_package_record(
    *,
    db: Session,
    report_run: ReportRun,
    reset_failed: bool = True,
) -> ReportPackage:
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
        _append_stage(package, "queued", "queued", "Report package queued for controlled publish.")
        report_run.package_status = "queued"
        if report_run.visual_generation_status == "failed":
            report_run.visual_generation_status = "not_started"
        db.flush()
        return package

    if package.status == "completed":
        report_run.package_status = "completed"
        db.flush()
        return package

    if package.status == "failed" and reset_failed:
        package.status = "queued"
        package.current_stage = "queued"
        package.error_message = None
        package.completed_at = None
        package.started_at = _utcnow()
        _append_stage(package, "queued", "queued", "Retry requested for report package.")
        report_run.package_status = "queued"
        if report_run.visual_generation_status == "failed":
            report_run.visual_generation_status = "not_started"
        db.flush()
        return package

    if package.status not in {"queued", "running"}:
        package.status = "queued"
        package.current_stage = "queued"
        _append_stage(package, "queued", "queued", "Report package queued for controlled publish.")

    report_run.package_status = package.status
    db.flush()
    return package


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


def _hex_to_rgb(value: str, fallback: str) -> tuple[int, int, int]:
    normalized = value.strip().lstrip("#")
    fallback_normalized = fallback.strip().lstrip("#")
    if len(normalized) != 6:
        normalized = fallback_normalized if len(fallback_normalized) == 6 else "f07f13"
    return tuple(int(normalized[index:index + 2], 16) for index in (0, 2, 4))


def _blend_rgb(start: tuple[int, int, int], end: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    clamped = max(0.0, min(1.0, factor))
    return tuple(
        int(round(start[index] + ((end[index] - start[index]) * clamped)))
        for index in range(3)
    )


def _format_number_tr(value: float | int | None) -> str:
    if value is None:
        return "-"
    number = float(value)
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number)):,}".replace(",", ".")

    formatted = f"{number:,.2f}"
    formatted = formatted.replace(",", "_").replace(".", ",").replace("_", ".")
    return formatted.rstrip("0").rstrip(",")


def _translate_metric_name(metric_code: str, fallback_name: str) -> str:
    return METRIC_NAME_OVERRIDES.get(metric_code, fallback_name)


def _localized_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    normalized = unit.strip()
    if not normalized:
        return None
    return UNIT_LABEL_OVERRIDES.get(normalized, normalized)


def _connector_label(source_system: str) -> str:
    return CONNECTOR_LABELS_TR.get(source_system, source_system.replace("_", " ").title())


def _evidence_label(code: str) -> str:
    return EVIDENCE_LABELS.get(code, code.replace("_", " ").title())


def _visual_scene_for_slot(visual_slot: str) -> str:
    slot = visual_slot.lower()
    if "cover" in slot:
        return "cover"
    if "profile" in slot:
        return "company"
    if "governance" in slot:
        return "governance"
    if "materiality" in slot or "matrix" in slot:
        return "materiality"
    if "environment" in slot or "scope2" in slot:
        return "environment"
    if "social" in slot or "supplier" in slot:
        return "social"
    return "default"


def _build_monogram_svg(brand_name: str, brand: BrandKit) -> str:
    letter = (brand_name.strip() or "V")[0].upper()
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="220" height="220" viewBox="0 0 220 220">
      <rect width="220" height="220" rx="28" fill="{brand.primary_color}"/>
      <rect x="16" y="16" width="188" height="188" rx="24" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.28)" stroke-width="4"/>
      <text x="110" y="136" font-size="104" font-family="{brand.font_family_headings}" text-anchor="middle" fill="white">{letter}</text>
    </svg>
    """.strip()


def _call_image_generation(prompt: str) -> ImageGenerationPayload | None:
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
                "output_format": "png",
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
                return ImageGenerationPayload(
                    payload=b64decode(item["b64_json"]),
                    deployment=deployment,
                )
            if isinstance(item, dict) and item.get("url"):
                with request.urlopen(item["url"], timeout=45) as image_response:
                    return ImageGenerationPayload(
                        payload=image_response.read(),
                        deployment=deployment,
                    )
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, ValueError):
            continue
    return None


def _draw_gradient_background(
    image: Image.Image,
    *,
    start: tuple[int, int, int],
    mid: tuple[int, int, int],
    end: tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    for y in range(height):
        factor = y / max(1, height - 1)
        if factor <= 0.58:
            color = _blend_rgb(start, mid, factor / 0.58)
        else:
            color = _blend_rgb(mid, end, (factor - 0.58) / 0.42)
        draw.line((0, y, width, y), fill=color)


def _draw_grid_overlay(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    color: tuple[int, int, int, int],
    spacing: int = 96,
) -> None:
    for x in range(0, width, spacing):
        draw.line((x, 0, x, height), fill=color, width=1)
    for y in range(0, height, spacing):
        draw.line((0, y, width, y), fill=color, width=1)


def _draw_metric_panels(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    primary: tuple[int, int, int, int],
) -> None:
    panel_specs = (
        (int(width * 0.08), int(height * 0.10), int(width * 0.25), int(height * 0.13)),
        (int(width * 0.08), int(height * 0.27), int(width * 0.19), int(height * 0.1)),
        (int(width * 0.72), int(height * 0.14), int(width * 0.18), int(height * 0.11)),
    )
    for x, y, panel_width, panel_height in panel_specs:
        draw.rounded_rectangle(
            (x, y, x + panel_width, y + panel_height),
            radius=28,
            fill=(255, 255, 255, 54),
            outline=(255, 255, 255, 88),
            width=2,
        )
        draw.line(
            (x + 28, y + panel_height - 34, x + panel_width - 28, y + panel_height - 34),
            fill=primary,
            width=6,
        )


def _draw_factory_scene(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    primary: tuple[int, int, int, int],
    secondary: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> None:
    ground_y = int(height * 0.74)
    draw.polygon(
        [
            (0, ground_y),
            (int(width * 0.36), int(height * 0.61)),
            (width, int(height * 0.66)),
            (width, height),
            (0, height),
        ],
        fill=(255, 255, 255, 34),
    )
    campus_specs = (
        (int(width * 0.44), int(height * 0.52), int(width * 0.18), int(height * 0.18)),
        (int(width * 0.63), int(height * 0.47), int(width * 0.2), int(height * 0.23)),
        (int(width * 0.28), int(height * 0.58), int(width * 0.15), int(height * 0.14)),
    )
    for x, y, block_width, block_height in campus_specs:
        draw.rounded_rectangle(
            (x, y, x + block_width, y + block_height),
            radius=26,
            fill=(255, 255, 255, 198),
            outline=(255, 255, 255, 225),
            width=2,
        )
        draw.rectangle(
            (x + 20, y + 18, x + block_width - 20, y + 36),
            fill=primary,
        )
        for index in range(4):
            inset_x = x + 28 + (index * 42)
            draw.rectangle(
                (inset_x, y + 58, inset_x + 24, y + 86),
                fill=secondary,
            )
    draw.line(
        (
            int(width * 0.42),
            int(height * 0.72),
            int(width * 0.92),
            int(height * 0.72),
        ),
        fill=accent,
        width=8,
    )
    for offset in (0.48, 0.61, 0.76):
        x = int(width * offset)
        draw.line((x, int(height * 0.44), x, int(height * 0.28)), fill=secondary, width=10)
        draw.ellipse((x - 18, int(height * 0.24), x + 18, int(height * 0.28)), fill=primary)


def _draw_governance_scene(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    primary: tuple[int, int, int, int],
    secondary: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> None:
    card_positions = (
        (int(width * 0.14), int(height * 0.46), int(width * 0.22), int(height * 0.16)),
        (int(width * 0.42), int(height * 0.34), int(width * 0.22), int(height * 0.16)),
        (int(width * 0.70), int(height * 0.50), int(width * 0.18), int(height * 0.14)),
    )
    nodes: list[tuple[int, int]] = []
    for x, y, card_width, card_height in card_positions:
        draw.rounded_rectangle(
            (x, y, x + card_width, y + card_height),
            radius=30,
            fill=(255, 255, 255, 190),
            outline=(255, 255, 255, 235),
            width=2,
        )
        draw.rectangle((x + 22, y + 18, x + card_width - 22, y + 34), fill=primary)
        nodes.append((x + (card_width // 2), y + (card_height // 2)))
    if len(nodes) >= 3:
        draw.line((*nodes[0], *nodes[1]), fill=accent, width=8)
        draw.line((*nodes[1], *nodes[2]), fill=secondary, width=8)
        for x, y in nodes:
            draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=secondary)
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(255, 255, 255, 220))


def _draw_materiality_scene(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    primary: tuple[int, int, int, int],
    secondary: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> None:
    origin_x = int(width * 0.2)
    origin_y = int(height * 0.78)
    axis_width = int(width * 0.54)
    axis_height = int(height * 0.42)
    draw.rounded_rectangle(
        (
            int(width * 0.56),
            int(height * 0.18),
            int(width * 0.88),
            int(height * 0.42),
        ),
        radius=34,
        fill=(255, 255, 255, 72),
        outline=(255, 255, 255, 138),
        width=2,
    )
    draw.line((origin_x, origin_y, origin_x + axis_width, origin_y), fill=(255, 255, 255, 210), width=4)
    draw.line((origin_x, origin_y, origin_x, origin_y - axis_height), fill=(255, 255, 255, 210), width=4)
    draw.rectangle(
        (
            origin_x + int(axis_width * 0.45),
            origin_y - int(axis_height * 0.55),
            origin_x + axis_width - 20,
            origin_y - 18,
        ),
        fill=(255, 255, 255, 42),
    )
    points = (
        (0.38, 0.28, primary),
        (0.55, 0.36, accent),
        (0.69, 0.22, secondary),
        (0.78, 0.42, primary),
        (0.62, 0.58, accent),
    )
    for x_factor, y_factor, fill in points:
        x = origin_x + int(axis_width * x_factor)
        y = origin_y - int(axis_height * y_factor)
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=fill)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(255, 255, 255, 220))


def _draw_environment_scene(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    primary: tuple[int, int, int, int],
    secondary: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> None:
    ground_y = int(height * 0.76)
    draw.polygon(
        [(0, ground_y), (int(width * 0.24), int(height * 0.64)), (width, int(height * 0.7)), (width, height), (0, height)],
        fill=(255, 255, 255, 34),
    )
    for index, x in enumerate((0.58, 0.72, 0.84)):
        tower_x = int(width * x)
        mast_height = int(height * (0.24 + (index * 0.04)))
        top_y = ground_y - mast_height
        draw.line((tower_x, ground_y, tower_x, top_y), fill=(255, 255, 255, 220), width=8)
        draw.line((tower_x, top_y, tower_x - 38, top_y + 12), fill=accent, width=6)
        draw.line((tower_x, top_y, tower_x + 32, top_y - 28), fill=accent, width=6)
        draw.line((tower_x, top_y, tower_x + 14, top_y + 44), fill=accent, width=6)
    panel_y = int(height * 0.66)
    for index in range(4):
        left = int(width * 0.18) + (index * 110)
        draw.polygon(
            [
                (left, panel_y + 70),
                (left + 84, panel_y + 52),
                (left + 126, panel_y + 108),
                (left + 42, panel_y + 128),
            ],
            fill=secondary,
        )
    draw.ellipse(
        (
            int(width * 0.08),
            int(height * 0.14),
            int(width * 0.36),
            int(height * 0.56),
        ),
        fill=(accent[0], accent[1], accent[2], 90),
    )
    draw.arc(
        (
            int(width * 0.04),
            int(height * 0.08),
            int(width * 0.42),
            int(height * 0.72),
        ),
        start=300,
        end=82,
        fill=(255, 255, 255, 210),
        width=6,
    )


def _draw_social_scene(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    primary: tuple[int, int, int, int],
    secondary: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> None:
    person_positions = (
        (int(width * 0.58), int(height * 0.38)),
        (int(width * 0.72), int(height * 0.46)),
        (int(width * 0.84), int(height * 0.34)),
    )
    for x, y in person_positions:
        draw.ellipse((x - 34, y - 78, x + 34, y - 10), fill=(255, 255, 255, 216))
        draw.rounded_rectangle((x - 54, y, x + 54, y + 136), radius=34, fill=secondary)
        draw.rounded_rectangle((x - 72, y + 30, x + 72, y + 66), radius=18, fill=accent)
    draw.line((*person_positions[0], *person_positions[1]), fill=primary, width=8)
    draw.line((*person_positions[1], *person_positions[2]), fill=primary, width=8)
    for x, y in ((int(width * 0.2), int(height * 0.58)), (int(width * 0.34), int(height * 0.48))):
        draw.rounded_rectangle(
            (x, y, x + 210, y + 108),
            radius=28,
            fill=(255, 255, 255, 186),
            outline=(255, 255, 255, 230),
            width=2,
        )
        draw.rectangle((x + 22, y + 20, x + 154, y + 36), fill=accent)
        draw.rectangle((x + 22, y + 54, x + 182, y + 64), fill=primary)
        draw.rectangle((x + 22, y + 74, x + 126, y + 84), fill=secondary)


def _draw_default_scene(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    primary: tuple[int, int, int, int],
    secondary: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
) -> None:
    _draw_factory_scene(draw, width=width, height=height, primary=primary, secondary=secondary, accent=accent)
    draw.ellipse((int(width * 0.7), int(height * 0.14), int(width * 0.94), int(height * 0.38)), fill=(accent[0], accent[1], accent[2], 108))
    draw.arc((int(width * 0.62), int(height * 0.08), int(width * 0.96), int(height * 0.42)), start=180, end=360, fill=secondary, width=7)


def _generate_fallback_visual(*, title: str, brand: BrandKit, accent_label: str, visual_slot: str) -> bytes:
    del title, accent_label
    width = 1600
    height = 1000
    scene = _visual_scene_for_slot(visual_slot)

    primary_rgb = _hex_to_rgb(brand.primary_color, "#f07f13")
    secondary_rgb = _hex_to_rgb(brand.secondary_color, "#0c4a6e")
    accent_rgb = _hex_to_rgb(brand.accent_color, "#7ab648")

    scene_backgrounds = {
        "cover": (_blend_rgb(primary_rgb, (255, 190, 120), 0.22), _blend_rgb(primary_rgb, secondary_rgb, 0.26), _blend_rgb(secondary_rgb, (18, 35, 55), 0.48)),
        "company": (_blend_rgb((255, 255, 255), secondary_rgb, 0.14), _blend_rgb(secondary_rgb, primary_rgb, 0.18), _blend_rgb(secondary_rgb, (10, 21, 34), 0.55)),
        "governance": (_blend_rgb(secondary_rgb, (255, 255, 255), 0.12), _blend_rgb(secondary_rgb, primary_rgb, 0.14), _blend_rgb((18, 34, 51), secondary_rgb, 0.22)),
        "materiality": (_blend_rgb(accent_rgb, (255, 255, 255), 0.18), _blend_rgb(secondary_rgb, accent_rgb, 0.24), _blend_rgb(secondary_rgb, (17, 32, 48), 0.46)),
        "environment": (_blend_rgb(accent_rgb, (255, 255, 255), 0.2), _blend_rgb(secondary_rgb, accent_rgb, 0.18), _blend_rgb(secondary_rgb, (15, 32, 46), 0.44)),
        "social": (_blend_rgb(primary_rgb, (255, 255, 255), 0.18), _blend_rgb(secondary_rgb, primary_rgb, 0.16), _blend_rgb(secondary_rgb, (16, 28, 42), 0.45)),
        "default": (_blend_rgb(primary_rgb, (255, 255, 255), 0.16), _blend_rgb(primary_rgb, secondary_rgb, 0.22), _blend_rgb(secondary_rgb, (15, 27, 39), 0.42)),
    }
    start, mid, end = scene_backgrounds.get(scene, scene_backgrounds["default"])

    base = Image.new("RGB", (width, height), start)
    _draw_gradient_background(base, start=start, mid=mid, end=end)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw.ellipse((int(width * 0.62), int(height * 0.06), int(width * 0.96), int(height * 0.44)), fill=(*primary_rgb, 84))
    draw.ellipse((int(width * 0.02), int(height * 0.44), int(width * 0.34), int(height * 0.9)), fill=(*accent_rgb, 74))
    draw.rounded_rectangle((int(width * 0.06), int(height * 0.12), int(width * 0.42), int(height * 0.34)), radius=64, fill=(255, 255, 255, 34))
    draw.rounded_rectangle((int(width * 0.12), int(height * 0.18), int(width * 0.26), int(height * 0.26)), radius=18, fill=(*accent_rgb, 178))
    _draw_grid_overlay(draw, width=width, height=height, color=(255, 255, 255, 24))
    _draw_metric_panels(draw, width=width, height=height, primary=(*accent_rgb, 226))

    scene_kwargs = {
        "draw": draw,
        "width": width,
        "height": height,
        "primary": (*primary_rgb, 222),
        "secondary": (*secondary_rgb, 218),
        "accent": (*accent_rgb, 226),
    }
    if scene == "cover" or scene == "company":
        _draw_factory_scene(**scene_kwargs)
    elif scene == "governance":
        _draw_governance_scene(**scene_kwargs)
    elif scene == "materiality":
        _draw_materiality_scene(**scene_kwargs)
    elif scene == "environment":
        _draw_environment_scene(**scene_kwargs)
    elif scene == "social":
        _draw_social_scene(**scene_kwargs)
    else:
        _draw_default_scene(**scene_kwargs)

    draw.arc(
        (int(width * -0.06), int(height * 0.48), int(width * 0.54), int(height * 1.02)),
        start=300,
        end=38,
        fill=(255, 255, 255, 126),
        width=9,
    )
    draw.line(
        (int(width * 0.04), int(height * 0.9), int(width * 0.94), int(height * 0.58)),
        fill=(255, 255, 255, 56),
        width=4,
    )

    composite = Image.alpha_composite(base.convert("RGBA"), overlay.filter(ImageFilter.GaussianBlur(radius=3)))
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
    generation = _call_image_generation(prompt_text)
    source_type = "azure_openai_image" if generation is not None else "deterministic_editorial_fallback"
    decorative_ai_generated = generation is not None
    payload = generation.payload if generation is not None else None
    if payload is None:
        payload = _generate_fallback_visual(
            title=title,
            brand=brand,
            accent_label=visual_slot.replace("_", " ").upper(),
            visual_slot=visual_slot,
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
        metadata={
            "title": title,
            "visual_slot": visual_slot,
            "image_policy": "decorative_only_no_claims",
            "generation_mode": "azure_openai_image" if generation is not None else "deterministic_fallback",
            "azure_openai_deployment": generation.deployment if generation is not None else None,
            "fallback_reason": None if generation is not None else "image_generation_unavailable_or_failed",
        },
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
        metadata={
            "title": title,
            "visual_slot": visual_slot,
            "image_policy": "deterministic_data_visualization",
        },
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
        unit = _localized_unit(fact.unit)
        value = _format_number_tr(fact.value_numeric)
        if unit == "%":
            return f"%{value}"
        if unit == "oran":
            return value
        if unit:
            return f"{value} {unit}"
        return value
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
    return f"%{_format_number_tr(abs(delta))} {direction}"


def _section_source_labels(facts: list[CanonicalFact]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        label = _connector_label(fact.source_system)
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def _latest_freshness_label(facts: list[CanonicalFact]) -> str | None:
    freshness_values = [fact.freshness_at for fact in facts if fact.freshness_at is not None]
    if not freshness_values:
        return None
    latest = max(freshness_values)
    return latest.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")


def _build_section_copy(
    *,
    company_profile: CompanyProfile,
    section_code: str,
    title: str,
    facts: list[CanonicalFact],
    metric_bucket: dict[str, list[CanonicalFact]],
    claims: list[str],
) -> tuple[str, list[str]]:
    source_labels = _section_source_labels(facts)
    source_note = ", ".join(source_labels) if source_labels else "seçili ERP kaynakları"

    if section_code == "CEO_MESSAGE":
        highlights = [
            "ERP, kanıt havuzu ve controlled publish hattı tek rapor paketi içinde birleştirilir.",
            "Sayısal ifadeler yalnızca hesaplama ekleri ile, metinsel ifadeler ise atıf dizini ile yayınlanır.",
            company_profile.sustainability_approach
            or "Kurumsal sürdürülebilirlik yaklaşımı veri bütünlüğü ve denetlenebilirlik üzerine kuruludur.",
        ]
        return (
            company_profile.ceo_message
            or (
                f"{company_profile.legal_name}, sürdürülebilirlik gündemini {source_note} üzerinden beslenen "
                "ölçülebilir KPI setleri, kanıt havuzu ve kontrollü yayın akışı ile kurumsal karar alma "
                "süreçlerine bağlamaktadır."
            ),
            highlights[:3],
        )

    if section_code == "COMPANY_PROFILE":
        workforce = _find_metric(metric_bucket, "WORKFORCE_HEADCOUNT")
        supplier = _find_metric(metric_bucket, "SUPPLIER_COVERAGE")
        facts_text = ", ".join(_metric_display_value(item) for item in facts[:2])
        return (
            f"{company_profile.legal_name}; {company_profile.sector or 'çok sektörlü üretim'} odağında, "
            f"{company_profile.headquarters or 'Türkiye'} merkezli operasyonlarını veriyle izlenen bir "
            f"sürdürülebilirlik dönüşüm programı ile yönetmektedir. Ölçek göstergeleri: {facts_text}.",
            [
                f"Çalışan ölçeği {_metric_display_value(workforce)} olarak izlenmektedir."
                if workforce
                else "",
                f"Tedarikçi davranış kodu kapsamı {_metric_display_value(supplier)} seviyesindedir."
                if supplier
                else "",
                f"Kurumsal profil ve operasyonel ayak izi {source_note} ile desteklenir.",
            ],
        )

    if section_code == "GOVERNANCE":
        board = _find_metric(metric_bucket, "BOARD_OVERSIGHT_COVERAGE")
        meetings = _find_metric(metric_bucket, "SUSTAINABILITY_COMMITTEE_MEETINGS")
        return (
            "Yönetişim yapısı, sürdürülebilirlik komitesi, yönetim kurulu gözetimi ve karar mekanizmalarının "
            "izlenebilirliğini güçlendirecek şekilde yapılandırılmıştır.",
            [
                (
                    f"Yönetim kurulu gözetim kapsamı {_metric_display_value(board)} seviyesinde sürdürülmüştür."
                    if board
                    else ""
                ),
                (
                    f"Sürdürülebilirlik komitesi {_metric_display_value(meetings)} frekansta toplanmıştır."
                    if meetings
                    else ""
                ),
                "Politika, risk ve onay akışı yalnızca doğrulanmış kanıtlardan türetilir.",
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
            [
                f"Önceliklendirme çıktıları {source_note} üzerinden normalleştirilen fact havuzundan beslenir.",
                "Matris, etki önemliliği ile finansal önemliliği aynı karar yüzeyinde birleştirir.",
                "Paydaş etkileşimleri ve konu sayısı appendix ve coverage çıktıları ile korunur.",
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
            [
                f"Çevresel KPI yüzeyi {source_note} ile güncellenmiştir.",
                "Tüm çevresel anlatı yalnızca taze KPI snapshot'ları ve hesaplama artefaktları ile desteklenir.",
                (
                    f"Scope 2 emisyon trendinde {yoy} kaydedilmiştir."
                    if yoy
                    else "Karşılaştırmalı emisyon trendi mevcut veri dönemi ile korunmuştur."
                ),
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
            [
                f"İnsan ve tedarik zinciri göstergeleri {source_note} ile güncellenmiştir.",
                (
                    f"İSG frekansında {yoy} sağlanmıştır."
                    if yoy
                    else "İSG frekansı ve çalışan göstergeleri rapor dönemine ait snapshot ile izlenmiştir."
                ),
                "Sosyal performans, yüksek riskli tedarikçi taramaları ve çalışan güvenliği çıktılarıyla birlikte ele alınır.",
            ],
        )

    fact_summary = ", ".join(_metric_display_value(item) for item in facts[:4])
    summary = (
        f"{company_profile.legal_name}, {title.lower()} alanında raporlama dönemi boyunca "
        f"kanıtla desteklenen KPI setleriyle tutarlı bir performans hikayesi ortaya koymuştur. "
        f"Öne çıkan metrikler: {fact_summary or 'hazır veri yüzeyi'}."
    )
    highlights = [
        f"Bu bölüm {source_note} üzerinden gelen normalize edilmiş fact havuzu ile beslenir.",
        "Kanıtsız veya hesaplama refsiz ifade otomatik olarak dışarıda bırakılır.",
        f"Doğrulanmış iddia adedi: {len(claims)}." if claims else "Doğrulanmış iddia seti eklerde korunur.",
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
    section_claims = claim_domains.get(_resolve_section_domain(section_code), [])
    section_metrics = [
        {
            "metric_code": fact.metric_code,
            "metric_name": _translate_metric_name(fact.metric_code, fact.metric_name),
            "period_key": fact.period_key,
            "display_value": _metric_display_value(fact),
            "source_system": fact.source_system,
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
        claims=section_claims,
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
        "claims": section_claims,
        "visual_slots": visual_slots,
        "primary_visual_slot": primary_visual_slot,
        "chart_svg": chart_svg,
        "chart_values": chart_values,
        "required_evidence": [
            str(item)
            for item in section_definition.get("required_evidence", [])
            if str(item).strip()
        ],
        "allowed_claim_types": [
            str(item)
            for item in section_definition.get("allowed_claim_types", [])
            if str(item).strip()
        ],
        "appendix_refs": [str(item) for item in section_definition.get("appendix_refs", []) if str(item).strip()],
        "required_metrics": required_metrics,
        "group_title": group_title,
        "group_color": group_color,
        "source_labels": _section_source_labels(section_facts),
        "freshness_label": _latest_freshness_label(section_facts),
        "claim_count": len(section_claims),
        "section_topics": SECTION_TOPIC_LINES.get(section_code, [title]),
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
                "summary_parts": [],
            },
        )
        card["lines"].append(
            {
                "label": section["title"],
                "page_hint": str(page_pointer),
                "page_range": f"{page_pointer:02d}-{page_pointer + 1:02d}",
            }
        )
        summary_part = " / ".join(section.get("section_topics", [])[:2])
        if summary_part:
            card["summary_parts"].append(summary_part)
        page_pointer += 2

    appendix_card = grouped.setdefault(
        "Ekler",
        {
            "title": "Ekler",
            "accent_color": "#f07f13",
            "lines": [],
            "summary_parts": ["Atıf dizini, hesaplama ekleri ve varsayım kaydı"],
        },
    )
    appendix_card["lines"].append(
        {
            "label": "Atıf ve hesaplama ekleri",
            "page_hint": str(appendix_start_page),
            "page_range": f"{appendix_start_page:02d}+",
        }
    )

    cards = list(grouped.values())
    for card in cards:
        card["summary"] = " • ".join(card.pop("summary_parts", [])[:2])
    return cards


def _appendix_label(reference: str) -> str:
    labels = {
        "assumption_register": "Varsayım kaydı",
        "citation_index": "Atıf dizini",
        "calculation_appendix": "Hesaplama ekleri",
        "coverage_matrix": "Kapsama matrisi",
    }
    return labels.get(reference, reference.replace("_", " ").title())


def _chunk_records(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if not items:
        return [[]]
    return [items[index:index + size] for index in range(0, len(items), size)]


def _build_cover_metrics(
    *,
    company_profile: CompanyProfile,
    section_payloads: list[dict[str, Any]],
) -> list[dict[str, str]]:
    metrics: list[dict[str, str]] = []
    if company_profile.employee_count:
        metrics.append({"label": "Çalışan Ölçeği", "value": _format_number_tr(company_profile.employee_count)})
    if company_profile.sector:
        metrics.append({"label": "Sektör", "value": company_profile.sector})
    if company_profile.headquarters:
        metrics.append({"label": "Merkez", "value": company_profile.headquarters})

    seen_codes: set[str] = set()
    for section in section_payloads:
        for metric in section.get("metrics", []):
            metric_code = str(metric.get("metric_code", "")).strip()
            if not metric_code or metric_code in seen_codes:
                continue
            seen_codes.add(metric_code)
            metrics.append(
                {
                    "label": str(metric.get("metric_name", metric_code)),
                    "value": str(metric.get("display_value", "-")),
                }
            )
            if len(metrics) >= 6:
                return metrics[:6]
    return metrics[:6]


def _build_story_paragraphs(
    *,
    section: dict[str, Any],
    company_profile: CompanyProfile,
) -> list[str]:
    section_code = str(section.get("section_code", "")).strip().upper()
    metrics_by_code = {
        str(item.get("metric_code", "")).strip().upper(): item
        for item in section.get("metrics", [])
        if str(item.get("metric_code", "")).strip()
    }
    source_note = ", ".join(section.get("source_labels", [])) or "seçili ERP kaynakları"
    freshness_note = str(section.get("freshness_label", "")).strip()

    def metric_value(metric_code: str) -> str | None:
        item = metrics_by_code.get(metric_code)
        if item is None:
            return None
        value = str(item.get("display_value", "")).strip()
        return value or None

    paragraphs: list[str] = [str(section.get("summary", "")).strip()]
    if section_code == "CEO_MESSAGE":
        if company_profile.ceo_message:
            paragraphs = [company_profile.ceo_message.strip()]
        if company_profile.sustainability_approach:
            paragraphs.append(company_profile.sustainability_approach.strip())
        paragraphs.append(
            f"Bu yayın akışı; {source_note} hatlarından normalleştirilen KPI snapshot'larını, kanıt havuzunu ve "
            "controlled publish zincirini aynı paket içinde birleştirir."
        )
        paragraphs.append(
            "Bu nedenle sayısal iddialar hesaplama eklerine, metinsel dayanaklar ise atıf dizinine bağlanarak yayınlanır."
        )
    elif section_code == "COMPANY_PROFILE":
        workforce = metric_value("WORKFORCE_HEADCOUNT")
        supplier = metric_value("SUPPLIER_COVERAGE")
        paragraphs.append(
            f"{company_profile.legal_name}, {company_profile.sector or 'kurumsal üretim'} odağında "
            f"{company_profile.headquarters or 'Türkiye'} merkezli operasyonlarını veriyle yönetilen bir yapı içinde sürdürmektedir."
        )
        if workforce or supplier:
            paragraphs.append(
                f"Raporlama döneminde çalışan ölçeği {workforce or '-'}; tedarikçi kod kapsamı ise {supplier or '-'} olarak izlenmiştir."
            )
        paragraphs.append(
            f"Kurumsal profil yüzeyi, marka kimliği ile operasyonel ölçek bilgisini {source_note} üzerinden beslenen fact katmanıyla bir araya getirir."
        )
    elif section_code == "GOVERNANCE":
        board = metric_value("BOARD_OVERSIGHT_COVERAGE")
        meetings = metric_value("SUSTAINABILITY_COMMITTEE_MEETINGS")
        paragraphs.append(
            f"Yönetim ve risk mimarisi, kurul gözetimi {board or '-'} ve komite ritmi {meetings or '-'} seviyesinde izlenebilir olacak şekilde tasarlanmıştır."
        )
        paragraphs.append(
            "Risk, strateji ve sermaye tahsisi kararları sürdürülebilirlik başlıklarıyla ilişkilendirilmiş; publish öncesi kontrol zinciri korunmuştur."
        )
        paragraphs.append(
            "Bu bölümde yalnızca doğrulanmış yönetişim iddiaları ve kanıt paketleri editoryal akışa alınır."
        )
    elif section_code == "DOUBLE_MATERIALITY":
        topic_count = metric_value("MATERIAL_TOPIC_COUNT")
        touchpoints = metric_value("STAKEHOLDER_ENGAGEMENT_TOUCHPOINTS")
        paragraphs.append(
            f"Çifte önemlilik görünümü, {topic_count or '-'} öncelikli konu ve {touchpoints or '-'} paydaş etkileşim teması üzerinden şekillenen karar setini tek yüzeyde toplar."
        )
        paragraphs.append(
            "Matris; dış etki ile finansal önemi aynı koordinat sisteminde okuyarak yönetişim, çevre ve sosyal programlar arasındaki öncelik gerilimini görünür kılar."
        )
        paragraphs.append(
            f"Önceliklendirme girdileri {source_note} ve onaylı kanıt paketi ile sınırlı tutulmuştur."
        )
    elif section_code == "ENVIRONMENT":
        scope2 = metric_value("E_SCOPE2_TCO2E")
        renewable = metric_value("RENEWABLE_ELECTRICITY_SHARE")
        intensity = metric_value("ENERGY_INTENSITY_REDUCTION")
        paragraphs.append(
            f"Çevresel performans omurgası, scope 2 emisyonu {scope2 or '-'} düzeyi ile yenilenebilir elektrik payı {renewable or '-'} çıktısını aynı stratejik hikâyede birleştirir."
        )
        paragraphs.append(
            f"Enerji yoğunluğu iyileşmesi {intensity or '-'} olarak izlenmiş; anlatı yalnızca taze snapshot ve hesaplama artefaktları ile beslenmiştir."
        )
        paragraphs.append(
            f"Veri tazeliği {freshness_note or 'mevcut dönem'} itibarıyla korunmuş; çevresel bölüm {source_note} kaynaklarıyla güncellenmiştir."
        )
    elif section_code == "SOCIAL":
        workforce = metric_value("WORKFORCE_HEADCOUNT")
        ltifr = metric_value("LTIFR")
        supplier = metric_value("SUPPLIER_COVERAGE")
        screening = metric_value("HIGH_RISK_SUPPLIER_SCREENING")
        paragraphs.append(
            f"Sosyal performans yüzeyi, {workforce or '-'} çalışan ölçeğini iş sağlığı güvenliği çıktıları ve tedarik zinciri kontrol sinyalleriyle birlikte ele alır."
        )
        paragraphs.append(
            f"Kayıp günlü iş kazası frekansı {ltifr or '-'}; tedarikçi kod kapsamı {supplier or '-'} ve yüksek riskli tarama oranı {screening or '-'} olarak izlenmiştir."
        )
        paragraphs.append(
            f"Sosyal veri seti {source_note} üzerinden normalleştirilmiş ve yayımlama öncesi izlenebilirlik ekleriyle korunmuştur."
        )
    else:
        paragraphs.extend(str(item).strip() for item in section.get("highlights", [])[:2] if str(item).strip())

    cleaned: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        if not paragraph or paragraph in seen:
            continue
        seen.add(paragraph)
        cleaned.append(paragraph)
    return cleaned[:4]


def _build_section_opener_lines(section: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.extend(str(item).strip() for item in section.get("section_topics", [])[:3] if str(item).strip())
    lines.extend(
        str(metric.get("metric_name", metric.get("metric_code", ""))).strip()
        for metric in section.get("metrics", [])[:1]
        if str(metric.get("metric_name", metric.get("metric_code", ""))).strip()
    )
    lines.extend(str(item).strip() for item in section.get("highlights", [])[:2] if str(item).strip())
    lines.extend(_appendix_label(str(item)) for item in section.get("appendix_refs", [])[:1] if str(item).strip())

    cleaned: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not line or line in seen:
            continue
        seen.add(line)
        cleaned.append(line)
    return cleaned[:4]


def _build_metric_rows(section: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for metric in section.get("metrics", []):
        rows.append(
            {
                "code": str(metric.get("metric_code", "")),
                "name": str(metric.get("metric_name", "")),
                "value": str(metric.get("display_value", "-")),
                "period": str(metric.get("period_key", "")),
                "source": _connector_label(str(metric.get("source_system", ""))),
            }
        )
    return rows


def _build_toc_rail_items(toc_cards: list[dict[str, Any]]) -> list[dict[str, str]]:
    icons = ["01", "02", "03", "04", "05", "06", "07"]
    items: list[dict[str, str]] = []
    for index, card in enumerate(toc_cards):
        items.append(
            {
                "icon": icons[index] if index < len(icons) else f"{index + 1:02d}",
                "label": str(card.get("title", "")),
                "accent_color": str(card.get("accent_color", "#f07f13")),
            }
        )
    return items


def _build_profile_facts(
    *,
    company_profile: CompanyProfile,
    section_payloads: list[dict[str, Any]],
) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    if company_profile.founded_year:
        facts.append({"label": "Kuruluş", "value": str(company_profile.founded_year)})
    if company_profile.employee_count:
        facts.append(
            {
                "label": "Çalışan",
                "value": _format_number_tr(company_profile.employee_count),
            }
        )
    if company_profile.headquarters:
        facts.append({"label": "Merkez", "value": company_profile.headquarters})
    if company_profile.sector:
        facts.append({"label": "Sektör", "value": company_profile.sector})
    facts.extend(_build_cover_metrics(company_profile=company_profile, section_payloads=section_payloads))

    cleaned: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    for item in facts:
        label = item["label"]
        if label in seen_labels:
            continue
        seen_labels.add(label)
        cleaned.append(item)
    return cleaned[:4]


def _build_evidence_points(section: dict[str, Any]) -> list[str]:
    evidence_points: list[str] = [
        _evidence_label(str(item))
        for item in section.get("required_evidence", [])[:2]
        if str(item).strip()
    ]
    if section.get("source_labels"):
        evidence_points.append(f"Girdi kaynakları: {', '.join(section['source_labels'])}")
    if section.get("freshness_label"):
        evidence_points.append(f"Son senkron tazeliği: {section['freshness_label']}")
    evidence_points.append(f"Doğrulanmış iddia adedi: {int(section.get('claim_count', 0))}")
    evidence_points.append("Sayısal ifadeler appendix ve atıf ekleri ile korunur.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in evidence_points:
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned[:4]


def _build_insight_chips(section: dict[str, Any]) -> list[str]:
    chips: list[str] = []
    for row in section.get("metric_rows", [])[:3]:
        chips.append(f"{row['name']}: {row['value']}")
    if section.get("freshness_label"):
        chips.append(f"Güncellik: {section['freshness_label']}")
    if section.get("source_labels"):
        chips.append(f"Kaynaklar: {', '.join(section['source_labels'])}")
    return chips[:4]


def _build_hero_caption(section: dict[str, Any], company_profile: CompanyProfile) -> str:
    scene = VISUAL_SCENE_LABELS.get(_visual_scene_for_slot(str(section.get("primary_visual_slot", ""))), VISUAL_SCENE_LABELS["default"])
    return (
        f"{company_profile.legal_name} için {scene.lower()} katmanı, bu bölümün KPI ve kanıt omurgasını "
        "tamamlayan dekoratif görsel yüzeyi temsil eder."
    )


def _resolve_layout_variant(section_code: str) -> str:
    if section_code == "CEO_MESSAGE":
        return "message"
    if section_code == "COMPANY_PROFILE":
        return "profile"
    if section_code == "DOUBLE_MATERIALITY":
        return "materiality"
    return "standard"


def _prepare_section_payloads_for_render(
    *,
    section_payloads: list[dict[str, Any]],
    company_profile: CompanyProfile,
) -> str:
    reporting_year = max(
        (
            metric["period_key"]
            for section in section_payloads
            for metric in section["metrics"]
            if str(metric.get("period_key", "")).strip()
        ),
        default="2025",
    )
    for index, section in enumerate(section_payloads, start=1):
        section["chart_svg_b64"] = (
            b64encode(section["chart_svg"].encode("utf-8")).decode("ascii")
            if section.get("chart_svg")
            else ""
        )
        section["layout_variant"] = _resolve_layout_variant(str(section.get("section_code", "")))
        section["metric_rows"] = _build_metric_rows(section)
        section["story_paragraphs"] = _build_story_paragraphs(
            section=section,
            company_profile=company_profile,
        )
        section["opener_lines"] = _build_section_opener_lines(section)
        section["appendix_labels"] = [
            _appendix_label(str(reference))
            for reference in section.get("appendix_refs", [])
            if str(reference).strip()
        ]
        section["evidence_points"] = _build_evidence_points(section)
        section["insight_chips"] = _build_insight_chips(section)
        section["hero_caption"] = _build_hero_caption(section, company_profile)
        section["opener_page_number"] = 3 + ((index - 1) * 2)
        section["data_page_number"] = section["opener_page_number"] + 1
    return reporting_year


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
    template_path = Path(__file__).with_name("report_factory_template.html.jinja")
    template = Template(template_path.read_text(encoding="utf-8"))
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

    reporting_year = _prepare_section_payloads_for_render(
        section_payloads=section_payloads,
        company_profile=company_profile,
    )

    cover_metrics = _build_cover_metrics(
        company_profile=company_profile,
        section_payloads=section_payloads,
    )
    profile_facts = _build_profile_facts(
        company_profile=company_profile,
        section_payloads=section_payloads,
    )
    toc_rail_items = _build_toc_rail_items(toc_cards)
    citation_chunks = _chunk_records(citations, 12)
    calculation_chunks = _chunk_records(calculations, 14)
    citation_page_start = appendix_start_page
    calculation_page_start = citation_page_start + len(citation_chunks)
    assumption_page_number = calculation_page_start + len(calculation_chunks)

    return template.render(
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand=brand,
        section_payloads=section_payloads,
        visual_data_uris=visual_data_uris,
        citation_chunks=citation_chunks,
        calculation_chunks=calculation_chunks,
        assumptions=assumptions,
        brand_mark_uri=_resolve_brand_mark_uri(tenant, brand),
        reporting_year=reporting_year,
        cover_metrics=cover_metrics,
        profile_facts=profile_facts,
        toc_cards=toc_cards,
        toc_rail_items=toc_rail_items,
        citation_page_start=citation_page_start,
        calculation_page_start=calculation_page_start,
        assumption_page_number=assumption_page_number,
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


def _draw_round_box(
    pdf: pdf_canvas.Canvas,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    radius: float,
    fill_color: colors.Color,
    stroke_color: colors.Color | None = None,
    stroke_width: float = 1,
    fill_alpha: float | None = None,
) -> None:
    pdf.saveState()
    if fill_alpha is not None:
        _set_fill_alpha_safe(pdf, fill_alpha)
    pdf.setFillColor(fill_color)
    if stroke_color is not None:
        pdf.setStrokeColor(stroke_color)
        pdf.setLineWidth(stroke_width)
        pdf.roundRect(x, y, width, height, radius, fill=1, stroke=1)
    else:
        pdf.roundRect(x, y, width, height, radius, fill=1, stroke=0)
    pdf.restoreState()


def _draw_cover_page(
    pdf: pdf_canvas.Canvas,
    *,
    tenant: Tenant,
    project: Project,
    company_profile: CompanyProfile,
    brand: BrandKit,
    hero_bytes: bytes,
    reporting_year: str,
    cover_metrics: list[dict[str, str]],
    heading_font: str,
    body_font: str,
) -> None:
    primary = _hex_color(brand.primary_color, "#f07f13")
    secondary = _hex_color(brand.secondary_color, "#0c4a6e")
    pdf.drawImage(ImageReader(BytesIO(hero_bytes)), 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, mask="auto")
    _draw_round_box(
        pdf,
        x=0,
        y=0,
        width=PAGE_WIDTH * 0.5,
        height=PAGE_HEIGHT,
        radius=0,
        fill_color=colors.HexColor("#081726"),
        fill_alpha=0.82,
    )
    _draw_round_box(
        pdf,
        x=PAGE_WIDTH * 0.5,
        y=0,
        width=PAGE_WIDTH * 0.5,
        height=PAGE_HEIGHT,
        radius=0,
        fill_color=primary,
        fill_alpha=0.16,
    )

    pdf.setFillColor(colors.white)
    pdf.setFont(heading_font, 20)
    pdf.drawString(42, PAGE_HEIGHT - 54, tenant.name)
    pdf.setFont(heading_font, 34)
    pdf.drawString(42, PAGE_HEIGHT - 132, "SÜRDÜRÜLEBİLİRLİK")
    pdf.drawString(42, PAGE_HEIGHT - 176, "RAPORU")
    pdf.drawString(268, PAGE_HEIGHT - 176, f"— {reporting_year}")

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
    current_y = _draw_paragraph(
        pdf,
        text=company_profile.sustainability_approach or company_profile.description or "",
        x=42,
        y_top=PAGE_HEIGHT - 352,
        width=280,
        style=body_style,
    )

    chip_width = 158
    chip_height = 62
    chip_y = 54
    for index, item in enumerate(cover_metrics[:4]):
        x = 42 + ((index % 2) * (chip_width + 12))
        y = chip_y + ((1 - (index // 2)) * (chip_height + 12))
        _draw_round_box(
            pdf,
            x=x,
            y=y,
            width=chip_width,
            height=chip_height,
            radius=18,
            fill_color=colors.white,
            fill_alpha=0.12,
            stroke_color=colors.white,
        )
        pdf.setFillColor(colors.white)
        pdf.setFont(body_font, 8)
        pdf.drawString(x + 14, y + chip_height - 18, str(item["label"]).upper()[:22])
        pdf.setFont(heading_font, 12)
        pdf.drawString(x + 14, y + 20, str(item["value"])[:24])

    card_x = PAGE_WIDTH - 280
    card_y = 52
    _draw_round_box(
        pdf,
        x=card_x,
        y=card_y,
        width=238,
        height=126,
        radius=24,
        fill_color=secondary,
        fill_alpha=0.62,
        stroke_color=colors.white,
    )
    pdf.setFillColor(colors.white)
    pdf.setFont(heading_font, 14)
    pdf.drawString(card_x + 18, card_y + 96, "Factory Çerçevesi")
    factory_style = ParagraphStyle(
        "cover-factory",
        fontName=body_font,
        fontSize=10,
        leading=14,
        textColor=colors.white,
    )
    _draw_paragraph(
        pdf,
        text=(
            "Sync, normalize, write, verify ve controlled publish adımları "
            "tek pakette korunur."
        ),
        x=card_x + 18,
        y_top=card_y + 80,
        width=200,
        style=factory_style,
    )
    pdf.setFont(body_font, 11)
    pdf.drawString(42, 26, project.name)
    pdf.drawString(42, 12, company_profile.headquarters or "Türkiye")
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
    _draw_round_box(
        pdf,
        x=0,
        y=0,
        width=PAGE_WIDTH * 0.56,
        height=PAGE_HEIGHT,
        radius=0,
        fill_color=_hex_color(brand.primary_color, "#f07f13"),
        fill_alpha=0.82,
    )
    pdf.setFillColor(colors.white)
    pdf.setFont(body_font, 11)
    pdf.drawString(52, PAGE_HEIGHT - 54, str(section.get("group_title", "Bölüm")).upper())
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
    chip_x = 52
    chip_y = PAGE_HEIGHT - 250
    chips = [
        f"{len(section.get('metric_rows', []))} KPI satırı",
        f"{int(section.get('claim_count', 0))} PASS iddia",
    ]
    if section.get("freshness_label"):
        chips.append(str(section["freshness_label"]))
    if section.get("source_labels"):
        chips.append(", ".join(section["source_labels"][:2]))
    for index, chip in enumerate(chips[:4]):
        _draw_round_box(
            pdf,
            x=chip_x,
            y=chip_y - (index * 34),
            width=228,
            height=24,
            radius=12,
            fill_color=colors.white,
            fill_alpha=0.14,
            stroke_color=colors.white,
        )
        pdf.setFillColor(colors.white)
        pdf.setFont(body_font, 9)
        pdf.drawString(chip_x + 12, chip_y - (index * 34) + 8, chip[:44])

    card_x = PAGE_WIDTH - 310
    card_y = 72
    _draw_round_box(
        pdf,
        x=card_x,
        y=card_y,
        width=258,
        height=170,
        radius=24,
        fill_color=colors.white,
        fill_alpha=0.12,
        stroke_color=colors.white,
    )
    pdf.setFillColor(colors.white)
    pdf.setFont(heading_font, 15)
    pdf.drawString(card_x + 18, card_y + 140, "Bölüm Çerçevesi")
    pdf.setFont(body_font, 11)
    line_y = card_y + 116
    for line in section.get("opener_lines", [])[:4]:
        pdf.drawString(card_x + 18, line_y, f"• {str(line)[:38]}")
        line_y -= 24
    pdf.showPage()


def _draw_section_data_page(
    pdf: pdf_canvas.Canvas,
    *,
    section: dict[str, Any],
    company_profile: CompanyProfile,
    brand: BrandKit,
    hero_bytes: bytes,
    profile_facts: list[dict[str, str]],
    heading_font: str,
    body_font: str,
) -> None:
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.setFillColor(_hex_color(section.get("group_color", brand.primary_color), "#f07f13"))
    pdf.setFont(heading_font, 26)
    pdf.drawString(36, PAGE_HEIGHT - 48, str(section["title"]))

    metrics = section.get("metric_rows", [])[:4]
    for index, metric in enumerate(metrics):
        x = 36 + (index * 195)
        y = PAGE_HEIGHT - 154
        _draw_round_box(
            pdf,
            x=x,
            y=y,
            width=176,
            height=88,
            radius=18,
            fill_color=colors.HexColor("#f8fbfc"),
            stroke_color=colors.HexColor("#dbe7ec"),
        )
        pdf.setFillColor(colors.HexColor("#61788c"))
        pdf.setFont(body_font, 8)
        pdf.drawString(x + 14, y + 68, str(metric.get("code", ""))[:24])
        pdf.setFillColor(_hex_color(brand.secondary_color, "#0c4a6e"))
        pdf.setFont(heading_font, 18)
        pdf.drawString(x + 14, y + 40, str(metric.get("value", "-"))[:18])
        pdf.setFillColor(colors.HexColor("#243b53"))
        pdf.setFont(body_font, 10)
        pdf.drawString(x + 14, y + 18, str(metric.get("name", ""))[:28])

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

    _draw_round_box(
        pdf,
        x=36,
        y=96,
        width=450,
        height=264,
        radius=24,
        fill_color=colors.HexColor("#f8fbfc"),
        stroke_color=colors.HexColor("#dbe7ec"),
    )
    current_y = PAGE_HEIGHT - 194
    story_paragraphs = section.get("story_paragraphs", []) or [str(section["summary"])]
    if str(section.get("layout_variant", "")) == "message":
        pdf.setFont(heading_font, 18)
        pdf.setFillColor(colors.HexColor("#13293d"))
        pdf.drawString(56, current_y, "Yönetim Perspektifi")
        current_y -= 24
        current_y = _draw_paragraph(
            pdf,
            text=story_paragraphs[0],
            x=56,
            y_top=current_y,
            width=410,
            style=ParagraphStyle(
                "quote",
                fontName=heading_font,
                fontSize=16,
                leading=24,
                textColor=colors.HexColor("#13293d"),
            ),
        ) - 10
        pdf.setFillColor(colors.HexColor("#5b7084"))
        pdf.setFont(body_font, 10)
        pdf.drawString(56, current_y, str(company_profile.ceo_name or "Kurumsal Liderlik"))
        current_y -= 18
    for paragraph in story_paragraphs[:3]:
        current_y = _draw_paragraph(
            pdf,
            text=str(paragraph),
            x=56,
            y_top=current_y,
            width=410,
            style=summary_style,
        ) - 10
    for item in section.get("evidence_points", [])[:3]:
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
    _draw_round_box(
        pdf,
        x=522,
        y=96,
        width=264,
        height=84,
        radius=20,
        fill_color=colors.HexColor("#f8fbfc"),
        stroke_color=colors.HexColor("#dbe7ec"),
    )
    pdf.setFillColor(_hex_color(brand.secondary_color, "#0c4a6e"))
    pdf.setFont(heading_font, 13)
    panel_title = "Kurumsal Profil Özeti" if section.get("layout_variant") == "profile" else "Kanıt ve İzlenebilirlik"
    pdf.drawString(540, 154, panel_title)
    sidebar_y = 136
    pdf.setFont(body_font, 10)
    pdf.setFillColor(colors.HexColor("#243b53"))
    sidebar_items: list[str]
    if section.get("layout_variant") == "profile":
        sidebar_items = [f"{item['label']}: {item['value']}" for item in profile_facts[:3]]
    else:
        sidebar_items = list(section.get("insight_chips", [])[:3] or section.get("claims", [])[:3])
    for item in sidebar_items:
        pdf.drawString(540, sidebar_y, f"• {str(item)[:36]}")
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
    reporting_year = _prepare_section_payloads_for_render(
        section_payloads=section_payloads,
        company_profile=company_profile,
    )
    cover_metrics = _build_cover_metrics(
        company_profile=company_profile,
        section_payloads=section_payloads,
    )
    profile_facts = _build_profile_facts(
        company_profile=company_profile,
        section_payloads=section_payloads,
    )

    cover_hero = visual_data.get("cover_hero")
    cover_bytes = (
        cover_hero[0]
        if cover_hero
        else _generate_fallback_visual(
            title="Kapak",
            brand=brand,
            accent_label="COVER",
            visual_slot="cover_hero",
        )
    )
    _draw_cover_page(
        pdf,
        tenant=tenant,
        project=project,
        company_profile=company_profile,
        brand=brand,
        hero_bytes=cover_bytes,
        reporting_year=reporting_year,
        cover_metrics=cover_metrics,
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
            company_profile=company_profile,
            brand=brand,
            hero_bytes=hero_bytes,
            profile_facts=profile_facts,
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
    readiness = build_report_factory_readiness(
        company_profile=company_profile,
        brand_kit=brand,
    )
    if not readiness["is_ready"]:
        blocker_summary = "; ".join(blocker["message"] for blocker in readiness["blockers"])
        raise ReportPackageGenerationError(
            "Report factory context hazir degil. "
            f"{blocker_summary}"
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
                                    f"{section['title']} bölümü için dekoratif kurumsal sürdürülebilirlik görseli. "
                                    f"Sahne: {VISUAL_SCENE_LABELS.get(_visual_scene_for_slot(visual_slot), VISUAL_SCENE_LABELS['default'])}. "
                                    f"Sektör bağlamı: {company_profile.sector or 'kurumsal üretim'}. "
                                    f"Renk paleti: primary {brand.primary_color}, secondary {brand.secondary_color}, accent {brand.accent_color}. "
                                    "Tam sayfa editoryal kalite, profesyonel annual report estetiği, veri iddiası taşımayan, "
                                    "gerçek belge veya operasyon fotoğrafı gibi görünmeyen, üzerinde metin veya rakam barındırmayan."
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
                            f"Dekoratif kurumsal kapak görseli. Marka tonu {brand.tone_name}; "
                            f"renkler {brand.primary_color}, {brand.secondary_color}, {brand.accent_color}. "
                            f"Konu: {company_profile.sector or 'endüstriyel üretim'} için sürdürülebilirlik report cover. "
                            "Premium annual report hissi, derinlikli kompozisyon, endüstriyel ve çevresel motif dengesi, "
                            "metin ve rakam içermeyen, veri iddiası taşımayan konsept görsel."
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
                "metadata": row.metadata_json or {},
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
