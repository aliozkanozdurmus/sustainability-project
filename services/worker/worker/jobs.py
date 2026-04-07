# Bu job modulu, kuyruga dusen belge ve paket islerini calistirir.

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any

from arq.worker import Retry

from worker.core.settings import settings


async def sample_health_job(
    _ctx: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "processed",
        "job": "sample_health_job",
        "payload": payload or {},
    }


def _ensure_api_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    api_root = repo_root / "apps" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))


def _compute_defer_seconds(job_try: int, base_seconds: int, max_defer_seconds: int) -> int:
    exponent = max(0, job_try - 1)
    defer_seconds = base_seconds * (2**exponent)
    return min(defer_seconds, max_defer_seconds)


def _run_extraction_sync(extraction_id: str) -> dict[str, Any]:
    _ensure_api_path()

    from app.db.session import SessionLocal
    from app.services.blob_storage import get_blob_storage_service
    from app.services.document_intelligence import get_document_intelligence_service
    from app.services.ocr_pipeline import run_ocr_extraction_for_record

    with SessionLocal() as db:
        outcome = run_ocr_extraction_for_record(
            db=db,
            extraction_id=extraction_id,
            blob_storage=get_blob_storage_service(),
            ocr_service=get_document_intelligence_service(),
        )
        return {
            "status": outcome.status,
            "job": "run_document_extraction_job",
            "extraction_id": outcome.extraction_id,
            "source_document_id": outcome.source_document_id,
            "chunk_count": outcome.chunk_count,
        }


def _run_indexing_sync(extraction_id: str) -> dict[str, Any]:
    _ensure_api_path()

    from app.db.session import SessionLocal
    from app.services.indexing_pipeline import run_chunk_indexing_for_extraction
    from app.services.search_index import get_search_index_service

    with SessionLocal() as db:
        outcome = run_chunk_indexing_for_extraction(
            db=db,
            extraction_id=extraction_id,
            index_service=get_search_index_service(),
        )
        return {
            "status": outcome.status,
            "job": "run_document_indexing_job",
            "extraction_id": outcome.extraction_id,
            "source_document_id": outcome.source_document_id,
            "indexed_chunk_count": outcome.indexed_chunk_count,
            "index_name": outcome.index_name,
        }


def _mark_retry_state_sync(
    extraction_id: str,
    *,
    attempt: int,
    defer_seconds: int,
    error_message: str,
) -> None:
    _ensure_api_path()

    from app.db.session import SessionLocal
    from app.services.ocr_pipeline import mark_extraction_retry_state

    with SessionLocal() as db:
        mark_extraction_retry_state(
            db=db,
            extraction_id=extraction_id,
            attempt=attempt,
            defer_seconds=defer_seconds,
            error_message=error_message,
        )


def _mark_failed_state_sync(extraction_id: str, *, error_message: str) -> None:
    _ensure_api_path()

    from app.db.session import SessionLocal
    from app.services.ocr_pipeline import mark_extraction_failed_state

    with SessionLocal() as db:
        mark_extraction_failed_state(
            db=db,
            extraction_id=extraction_id,
            error_message=error_message,
        )


def _mark_index_retry_state_sync(
    extraction_id: str,
    *,
    attempt: int,
    defer_seconds: int,
    error_message: str,
) -> None:
    _ensure_api_path()

    from app.db.session import SessionLocal
    from app.services.indexing_pipeline import mark_indexing_retry_state

    with SessionLocal() as db:
        mark_indexing_retry_state(
            db=db,
            extraction_id=extraction_id,
            attempt=attempt,
            defer_seconds=defer_seconds,
            error_message=error_message,
        )


def _mark_index_failed_state_sync(extraction_id: str, *, error_message: str) -> None:
    _ensure_api_path()

    from app.db.session import SessionLocal
    from app.services.indexing_pipeline import mark_indexing_failed_state

    with SessionLocal() as db:
        mark_indexing_failed_state(
            db=db,
            extraction_id=extraction_id,
            error_message=error_message,
        )


def _mark_report_package_retry_state_sync(
    report_run_id: str,
    *,
    attempt: int,
    defer_seconds: int,
    error_message: str,
) -> None:
    _ensure_api_path()

    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.core import ReportPackage, ReportRun

    with SessionLocal() as db:
        report_run = db.get(ReportRun, report_run_id)
        package = db.scalar(select(ReportPackage).where(ReportPackage.report_run_id == report_run_id))
        if report_run is None or package is None:
            return

        history = package.stage_history_json or []
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "stage": package.current_stage or "queued",
                "status": "retrying",
                "at_utc": datetime.now(timezone.utc).isoformat(),
                "detail": (
                    f"attempt={attempt} defer_seconds={defer_seconds} "
                    f"reason={error_message}"
                ),
            }
        )
        package.stage_history_json = history
        package.status = "queued"
        package.error_message = error_message
        package.completed_at = None
        report_run.package_status = "queued"
        db.commit()


def _mark_report_package_failed_state_sync(
    report_run_id: str,
    *,
    error_message: str,
) -> None:
    _ensure_api_path()

    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.core import AuditEvent, ReportPackage, ReportRun

    with SessionLocal() as db:
        report_run = db.get(ReportRun, report_run_id)
        package = db.scalar(select(ReportPackage).where(ReportPackage.report_run_id == report_run_id))
        if report_run is None:
            return

        failed_at = datetime.now(timezone.utc)
        if package is not None:
            history = package.stage_history_json or []
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "stage": package.current_stage or "queued",
                    "status": "failed",
                    "at_utc": failed_at.isoformat(),
                    "detail": error_message,
                }
            )
            package.stage_history_json = history
            package.status = "failed"
            package.error_message = error_message
            package.completed_at = failed_at

        report_run.package_status = "failed"
        if report_run.visual_generation_status == "running":
            report_run.visual_generation_status = "failed"

        db.add(
            AuditEvent(
                tenant_id=report_run.tenant_id,
                project_id=report_run.project_id,
                report_run_id=report_run.id,
                event_type="publish",
                event_name="publish_failed",
                event_payload={
                    "schema_version": "publish_gate_v1",
                    "run_id": report_run.id,
                    "blocked": False,
                    "published": False,
                    "error_code": "REPORT_PACKAGE_GENERATION_FAILED",
                    "reason": error_message,
                    "generated_at_utc": failed_at.isoformat(),
                },
            )
        )
        db.commit()


def _run_report_package_sync(report_run_id: str) -> dict[str, Any]:
    _ensure_api_path()

    from datetime import datetime, timezone

    from app.db.session import SessionLocal
    from app.models.core import AuditEvent, ReportRun
    from app.services.report_factory import REPORT_PDF_ARTIFACT_TYPE, ensure_report_package

    with SessionLocal() as db:
        report_run = db.get(ReportRun, report_run_id)
        if report_run is None:
            raise ValueError(f"Report run not found: {report_run_id}")

        package_result = ensure_report_package(db=db, report_run=report_run)
        report_run.status = "published"
        report_run.publish_ready = True
        if report_run.completed_at is None:
            report_run.completed_at = datetime.now(timezone.utc)

        report_pdf = next(
            (
                artifact
                for artifact in package_result.artifacts
                if artifact.artifact_type == REPORT_PDF_ARTIFACT_TYPE
            ),
            None,
        )
        event_payload = {
            "schema_version": "publish_gate_v1",
            "run_id": report_run.id,
            "blocked": False,
            "published": True,
            "package_job_id": package_result.package.id,
            "package_status": package_result.package.status,
            "artifacts": [
                {
                    "artifact_id": artifact.id,
                    "artifact_type": artifact.artifact_type,
                    "filename": artifact.filename,
                    "content_type": artifact.content_type,
                    "size_bytes": artifact.size_bytes,
                    "checksum": artifact.checksum,
                }
                for artifact in package_result.artifacts
            ],
            "report_pdf": (
                {
                    "artifact_id": report_pdf.id,
                    "artifact_type": report_pdf.artifact_type,
                    "filename": report_pdf.filename,
                    "content_type": report_pdf.content_type,
                    "size_bytes": report_pdf.size_bytes,
                    "checksum": report_pdf.checksum,
                }
                if report_pdf is not None
                else None
            ),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        db.add(
            AuditEvent(
                tenant_id=report_run.tenant_id,
                project_id=report_run.project_id,
                report_run_id=report_run.id,
                event_type="publish",
                event_name="publish_completed",
                event_payload=event_payload,
            )
        )
        db.commit()

        return {
            "status": package_result.package.status,
            "job": "run_report_package_job",
            "report_run_id": report_run.id,
            "package_job_id": package_result.package.id,
            "artifact_count": len(package_result.artifacts),
            "report_pdf_artifact_id": report_pdf.id if report_pdf is not None else None,
        }


async def _enqueue_indexing_job(ctx: dict[str, Any], extraction_id: str) -> str:
    redis = ctx.get("redis")
    if redis is None:
        raise RuntimeError("Worker redis context is unavailable for enqueue.")
    job = await redis.enqueue_job(
        "run_document_indexing_job",
        {"extraction_id": extraction_id},
        _queue_name=settings.queue_name,
    )
    if job is None:
        raise RuntimeError("Failed to create indexing job handle.")
    return str(job.job_id)


async def run_document_extraction_job(
    ctx: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_payload = payload or {}
    extraction_id = str(job_payload.get("extraction_id", "")).strip()
    if not extraction_id:
        raise ValueError("Missing required extraction_id in payload.")

    job_try = int(ctx.get("job_try", 1))
    max_retries = max(1, settings.ocr_job_max_retries)

    try:
        result = await asyncio.to_thread(_run_extraction_sync, extraction_id)
    except ValueError:
        raise
    except RuntimeError as exc:
        message = str(exc)
        if "already processing" in message.lower() or "lock not acquired" in message.lower():
            if job_try < max_retries:
                defer_seconds = _compute_defer_seconds(
                    job_try,
                    settings.ocr_retry_base_seconds,
                    settings.ocr_retry_max_defer_seconds,
                )
                await asyncio.to_thread(
                    _mark_retry_state_sync,
                    extraction_id,
                    attempt=job_try,
                    defer_seconds=defer_seconds,
                    error_message=message,
                )
                raise Retry(defer=defer_seconds)
            await asyncio.to_thread(
                _mark_failed_state_sync,
                extraction_id,
                error_message=f"Retry exhausted: {message}",
            )
        raise
    except Exception as exc:
        message = str(exc)
        if job_try < max_retries:
            defer_seconds = _compute_defer_seconds(
                job_try,
                settings.ocr_retry_base_seconds,
                settings.ocr_retry_max_defer_seconds,
            )
            await asyncio.to_thread(
                _mark_retry_state_sync,
                extraction_id,
                attempt=job_try,
                defer_seconds=defer_seconds,
                error_message=message,
            )
            raise Retry(defer=defer_seconds)
        await asyncio.to_thread(
            _mark_failed_state_sync,
            extraction_id,
            error_message=f"Retry exhausted: {message}",
        )
        raise

    try:
        indexing_job_id = await _enqueue_indexing_job(ctx, extraction_id)
    except Exception as exc:
        message = str(exc)
        if job_try < max_retries:
            defer_seconds = _compute_defer_seconds(
                job_try,
                settings.ocr_retry_base_seconds,
                settings.ocr_retry_max_defer_seconds,
            )
            raise Retry(defer=defer_seconds) from exc
        await asyncio.to_thread(
            _mark_index_failed_state_sync,
            extraction_id,
            error_message=f"Indexing enqueue failed: {message}",
        )
        raise

    result["indexing_job_id"] = indexing_job_id
    return result


async def run_document_indexing_job(
    ctx: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_payload = payload or {}
    extraction_id = str(job_payload.get("extraction_id", "")).strip()
    if not extraction_id:
        raise ValueError("Missing required extraction_id in payload.")

    job_try = int(ctx.get("job_try", 1))
    max_retries = max(1, settings.index_job_max_retries)

    try:
        return await asyncio.to_thread(_run_indexing_sync, extraction_id)
    except ValueError:
        raise
    except RuntimeError as exc:
        message = str(exc)
        if job_try < max_retries:
            defer_seconds = _compute_defer_seconds(
                job_try,
                settings.index_retry_base_seconds,
                settings.index_retry_max_defer_seconds,
            )
            await asyncio.to_thread(
                _mark_index_retry_state_sync,
                extraction_id,
                attempt=job_try,
                defer_seconds=defer_seconds,
                error_message=message,
            )
            raise Retry(defer=defer_seconds)
        await asyncio.to_thread(
            _mark_index_failed_state_sync,
            extraction_id,
            error_message=f"Retry exhausted: {message}",
        )
        raise


async def run_report_package_job(
    ctx: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_payload = payload or {}
    report_run_id = str(job_payload.get("report_run_id", "")).strip()
    if not report_run_id:
        raise ValueError("Missing required report_run_id in payload.")

    job_try = int(ctx.get("job_try", 1))
    max_retries = max(1, settings.package_job_max_retries)

    try:
        return await asyncio.to_thread(_run_report_package_sync, report_run_id)
    except ValueError:
        raise
    except Exception as exc:
        message = str(exc)
        if job_try < max_retries:
            defer_seconds = _compute_defer_seconds(
                job_try,
                settings.package_retry_base_seconds,
                settings.package_retry_max_defer_seconds,
            )
            await asyncio.to_thread(
                _mark_report_package_retry_state_sync,
                report_run_id,
                attempt=job_try,
                defer_seconds=defer_seconds,
                error_message=message,
            )
            raise Retry(defer=defer_seconds)
        await asyncio.to_thread(
            _mark_report_package_failed_state_sync,
            report_run_id,
            error_message=f"Retry exhausted: {message}",
        )
        raise
