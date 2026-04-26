from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import BrandKit, CompanyProfile, ReportPackage, ReportRun, ReportVisualAsset
from app.services.blob_storage import BlobStorageService


# Bu moduldaki kural basit: veri iddiasi tasiyan grafikler deterministic SVG,
# dekoratif sahneler ise kurumsal gorsel prompt zinciri uzerinden uretilir.
@dataclass(frozen=True)
class VisualBuildResult:
    section_payloads: list[dict[str, Any]]
    visual_data: dict[str, tuple[bytes, str]]
    visual_data_uris: dict[str, str]


def generate_visual_assets(
    *,
    db: Session,
    blob_storage: BlobStorageService,
    package: ReportPackage,
    report_run: ReportRun,
    company_profile: CompanyProfile,
    brand: BrandKit,
    section_payloads: list[dict[str, Any]],
) -> VisualBuildResult:
    from app.services import report_factory as legacy_report_factory

    visual_data: dict[str, tuple[bytes, str]] = {}
    visual_data_uris: dict[str, str] = {}
    report_run.visual_generation_status = "running"

    for section in section_payloads:
        for visual_slot in section["visual_slots"]:
            if visual_slot in visual_data:
                continue
            lower_slot = visual_slot.lower()
            if any(token in lower_slot for token in ("chart", "matrix", "grid")):
                # Sayisal guven tasiyan varliklar burada modelden degil,
                # section payload icinden deterministic olarak uretiliyor.
                if "matrix" in lower_slot:
                    svg = legacy_report_factory._build_matrix_svg(
                        title=section["title"],
                        metrics=section["metrics"],
                        brand=brand,
                    )
                elif "grid" in lower_slot:
                    svg = legacy_report_factory._build_grid_svg(
                        title=section["title"],
                        metrics=section["metrics"],
                        brand=brand,
                    )
                else:
                    svg = section["chart_svg"] or legacy_report_factory._build_chart_svg(
                        title=section["title"],
                        values=section["chart_values"],
                        brand=brand,
                    )
                payload, content_type = legacy_report_factory._upload_visual_svg_asset(
                    db=db,
                    blob_storage=blob_storage,
                    package=package,
                    visual_slot=visual_slot,
                    title=section["title"],
                    svg=svg,
                )
            else:
                # Dekoratif gorseller bilincli olarak "metin ve rakam icermeyen"
                # promptlarla uretiliyor; boylece rapor anlatisi ile gorsel karismaz.
                payload, content_type = legacy_report_factory._upload_visual_image_asset(
                    db=db,
                    blob_storage=blob_storage,
                    package=package,
                    brand=brand,
                    visual_slot=visual_slot,
                    title=section["title"],
                    prompt_text=(
                        f"{section['title']} bolumu icin dekoratif kurumsal surdurulebilirlik gorseli. "
                        f"Sahne: {legacy_report_factory.VISUAL_SCENE_LABELS.get(legacy_report_factory._visual_scene_for_slot(visual_slot), legacy_report_factory.VISUAL_SCENE_LABELS['default'])}. "
                        f"Sektor baglami: {company_profile.sector or 'kurumsal uretim'}. "
                        f"Renk paleti: primary {brand.primary_color}, secondary {brand.secondary_color}, accent {brand.accent_color}. "
                        "Tam sayfa editoryal kalite, profesyonel annual report estetigi, veri iddiasi tasimayan, "
                        "gercek belge veya operasyon fotografi gibi gorunmeyen, uzerinde metin veya rakam barindirmayan."
                    ),
                )
            visual_data[visual_slot] = (payload, content_type)
            visual_data_uris[visual_slot] = legacy_report_factory._to_data_uri(payload, content_type)

    if "cover_hero" not in visual_data:
        # Kapak gorseli blueprint'te ayrica verilmemisse dahi paket eksik kalmasin diye
        # kurumsal bir fallback hero uretiyoruz.
        payload, content_type = legacy_report_factory._upload_visual_image_asset(
            db=db,
            blob_storage=blob_storage,
            package=package,
            brand=brand,
            visual_slot="cover_hero",
            title="Kurumsal Surdurulebilirlik",
            prompt_text=(
                f"Dekoratif kurumsal kapak gorseli. Marka tonu {brand.tone_name}; "
                f"renkler {brand.primary_color}, {brand.secondary_color}, {brand.accent_color}. "
                f"Konu: {company_profile.sector or 'endustriyel uretim'} icin surdurulebilirlik report cover. "
                "Premium annual report hissi, derinlikli kompozisyon, endustriyel ve cevresel motif dengesi, "
                "metin ve rakam icermeyen, veri iddiasi tasimayan konsept gorsel."
            ),
        )
        visual_data["cover_hero"] = (payload, content_type)
        visual_data_uris["cover_hero"] = legacy_report_factory._to_data_uri(payload, content_type)

    report_run.visual_generation_status = "completed"

    for section in section_payloads:
        section["chart_visual_slot"] = next(
            (
                slot
                for slot in section["visual_slots"]
                if any(token in slot.lower() for token in ("chart", "matrix", "grid"))
            ),
            None,
        )

    return VisualBuildResult(
        section_payloads=section_payloads,
        visual_data=visual_data,
        visual_data_uris=visual_data_uris,
    )


def build_visual_manifest(*, db: Session, package_id: str) -> list[dict[str, Any]]:
    return [
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
            select(ReportVisualAsset).where(ReportVisualAsset.report_package_id == package_id)
        ).all()
    ]
