from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.core import Project, ReportArtifact, ReportPackage, ReportRun, ReportVisualAsset
from app.services.blob_storage import BlobStorageService


# Package state modulu, controlled publish surecinin denetlenebilir hafizasidir.
# UI'daki queue board ve audit bundle ayni stage gecmisini burada okur.
@dataclass(frozen=True)
class PackageArtifacts:
    package: ReportPackage
    artifacts: list[ReportArtifact]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_artifact_download_path(*, report_run_id: str, artifact_id: str, tenant_id: str, project_id: str) -> str:
    return (
        f"/runs/{report_run_id}/artifacts/{artifact_id}"
        f"?tenant_id={tenant_id}&project_id={project_id}"
    )


def serialize_stage_history(package: ReportPackage) -> list[dict[str, Any]]:
    history = package.stage_history_json or []
    return history if isinstance(history, list) else []


def append_stage(package: ReportPackage, stage: str, status: str, detail: str | None = None) -> None:
    history = serialize_stage_history(package)
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


def update_stage(package: ReportPackage, stage: str, status: str, detail: str | None = None) -> None:
    history = serialize_stage_history(package)
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


def to_artifact_response_payload(artifact: ReportArtifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "filename": artifact.filename,
        "content_type": artifact.content_type,
        "size_bytes": artifact.size_bytes,
        "checksum": artifact.checksum,
        "created_at_utc": artifact.created_at.isoformat(),
        "download_path": build_artifact_download_path(
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
        # Ilk kayit aninda package'i hemen olusturuyoruz ki
        # queue ve approval center "henuz artefakt yok" durumunu da izleyebilsin.
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
        append_stage(package, "queued", "queued", "Report package queued for controlled publish.")
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
        append_stage(package, "queued", "queued", "Retry requested for report package.")
        report_run.package_status = "queued"
        if report_run.visual_generation_status == "failed":
            report_run.visual_generation_status = "not_started"
        db.flush()
        return package

    if package.status not in {"queued", "running"}:
        package.status = "queued"
        package.current_stage = "queued"
        append_stage(package, "queued", "queued", "Report package queued for controlled publish.")

    report_run.package_status = package.status
    db.flush()
    return package


def build_package_status_payload(*, db: Session, report_run: ReportRun) -> dict[str, Any]:
    package = get_report_package(db=db, report_run_id=report_run.id)
    return {
        "run_id": report_run.id,
        "package_job_id": package.id if package else None,
        "package_status": package.status if package else report_run.package_status,
        "current_stage": package.current_stage if package else None,
        "report_quality_score": report_run.report_quality_score,
        "visual_generation_status": report_run.visual_generation_status,
        "artifacts": [to_artifact_response_payload(item) for item in list_run_artifacts(db=db, report_run_id=report_run.id)],
        "stage_history": serialize_stage_history(package) if package else [],
        "generated_at_utc": _utcnow().isoformat(),
    }


def complete_report_package(
    *,
    db: Session,
    blob_storage: BlobStorageService,
    package: ReportPackage,
    report_run: ReportRun,
    project: Project,
    blueprint_version: str,
    facts: list[Any],
    section_payloads: list[dict[str, Any]],
    rendered_pdf: Any,
    citation_index: list[dict[str, Any]],
    calculations: list[dict[str, Any]],
    assumptions: list[str],
) -> PackageArtifacts:
    from app.services import report_factory as legacy_report_factory

    # Final artefact seti tek noktada kapanir; boylece publish gate,
    # package completeness ve download endpoint'leri ayni truth source'u kullanir.
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

    confidence_values = [getattr(fact, "confidence_score", None) or 0.9 for fact in facts]
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
        "blueprint_version": blueprint_version,
    }

    artifacts = [
        legacy_report_factory._upsert_artifact(
            db=db,
            blob_storage=blob_storage,
            package=package,
            report_run=report_run,
            artifact_type=artifact_type,
            content_type=content_type,
            payload=payload,
            filename=legacy_report_factory._artifact_filename(project, report_run, artifact_type, extension),
            metadata=metadata,
        )
        for artifact_type, content_type, payload, extension, metadata in [
            (
                legacy_report_factory.REPORT_PDF_ARTIFACT_TYPE,
                "application/pdf",
                rendered_pdf.payload,
                "pdf",
                artifact_metadata,
            ),
            (
                legacy_report_factory.VISUAL_MANIFEST_ARTIFACT_TYPE,
                "application/json",
                json.dumps(visual_manifest, ensure_ascii=False, indent=2).encode("utf-8"),
                "json",
                {"package_id": package.id, "visual_count": len(visual_manifest)},
            ),
            (
                legacy_report_factory.CITATION_INDEX_ARTIFACT_TYPE,
                "application/json",
                json.dumps(citation_index, ensure_ascii=False, indent=2).encode("utf-8"),
                "json",
                {"package_id": package.id, "citation_count": len(citation_index)},
            ),
            (
                legacy_report_factory.CALCULATION_APPENDIX_ARTIFACT_TYPE,
                "application/json",
                json.dumps(calculations, ensure_ascii=False, indent=2).encode("utf-8"),
                "json",
                {"package_id": package.id, "calculation_count": len(calculations)},
            ),
            (
                legacy_report_factory.COVERAGE_MATRIX_ARTIFACT_TYPE,
                "application/json",
                json.dumps(coverage_matrix, ensure_ascii=False, indent=2).encode("utf-8"),
                "json",
                {"package_id": package.id, "section_count": len(section_payloads)},
            ),
            (
                legacy_report_factory.ASSUMPTION_REGISTER_ARTIFACT_TYPE,
                "application/json",
                json.dumps(assumptions, ensure_ascii=False, indent=2).encode("utf-8"),
                "json",
                {"package_id": package.id, "assumption_count": len(assumptions)},
            ),
        ]
    ]
    db.flush()
    return PackageArtifacts(package=package, artifacts=artifacts)
