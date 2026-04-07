# Bu test dosyasi, jobs davranisini dogrular.

import pytest
from arq.worker import Retry

from worker import jobs
from worker.core.settings import settings
from worker.jobs import (
    run_document_extraction_job,
    run_document_indexing_job,
    run_report_package_job,
    sample_health_job,
)


@pytest.mark.asyncio
async def test_sample_health_job_returns_payload() -> None:
    result = await sample_health_job({}, {"tenant_id": "ten_001"})
    assert result["status"] == "processed"
    assert result["job"] == "sample_health_job"
    assert result["payload"]["tenant_id"] == "ten_001"


@pytest.mark.asyncio
async def test_run_document_extraction_job_requires_extraction_id() -> None:
    with pytest.raises(ValueError, match="extraction_id"):
        await run_document_extraction_job({}, {})


@pytest.mark.asyncio
async def test_run_document_extraction_job_delegates_and_enqueues_indexing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(extraction_id: str) -> dict[str, str]:
        return {
            "status": "completed",
            "job": "run_document_extraction_job",
            "extraction_id": extraction_id,
            "source_document_id": "doc_1",
            "chunk_count": 3,
        }

    async def fake_enqueue(_ctx: dict, extraction_id: str) -> str:
        return f"idx-{extraction_id}"

    monkeypatch.setattr(jobs, "_run_extraction_sync", fake_runner)
    monkeypatch.setattr(jobs, "_enqueue_indexing_job", fake_enqueue)

    result = await run_document_extraction_job({}, {"extraction_id": "ext_123"})
    assert result["status"] == "completed"
    assert result["job"] == "run_document_extraction_job"
    assert result["extraction_id"] == "ext_123"
    assert result["indexing_job_id"] == "idx-ext_123"


@pytest.mark.asyncio
async def test_run_document_extraction_job_retries_on_lock_contention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(_extraction_id: str) -> dict[str, str]:
        raise RuntimeError("Extraction lock not acquired.")

    retry_calls: list[tuple[int, int]] = []

    def fake_mark_retry(
        _extraction_id: str,
        *,
        attempt: int,
        defer_seconds: int,
        error_message: str,
    ) -> None:
        assert "lock not acquired" in error_message.lower()
        retry_calls.append((attempt, defer_seconds))

    monkeypatch.setattr(jobs, "_run_extraction_sync", fake_runner)
    monkeypatch.setattr(jobs, "_mark_retry_state_sync", fake_mark_retry)
    monkeypatch.setattr(settings, "ocr_job_max_retries", 3)
    monkeypatch.setattr(settings, "ocr_retry_base_seconds", 2)
    monkeypatch.setattr(settings, "ocr_retry_max_defer_seconds", 30)

    with pytest.raises(Retry) as exc_info:
        await run_document_extraction_job({"job_try": 1}, {"extraction_id": "ext_123"})

    assert retry_calls == [(1, 2)]
    assert exc_info.value.defer_score == 2000


@pytest.mark.asyncio
async def test_run_document_extraction_job_marks_index_failed_when_enqueue_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(extraction_id: str) -> dict[str, str]:
        return {
            "status": "completed",
            "job": "run_document_extraction_job",
            "extraction_id": extraction_id,
        }

    async def fake_enqueue(_ctx: dict, _extraction_id: str) -> str:
        raise RuntimeError("queue offline")

    failed_messages: list[str] = []

    def fake_mark_index_failed(
        _extraction_id: str,
        *,
        error_message: str,
    ) -> None:
        failed_messages.append(error_message)

    monkeypatch.setattr(jobs, "_run_extraction_sync", fake_runner)
    monkeypatch.setattr(jobs, "_enqueue_indexing_job", fake_enqueue)
    monkeypatch.setattr(jobs, "_mark_index_failed_state_sync", fake_mark_index_failed)
    monkeypatch.setattr(settings, "ocr_job_max_retries", 2)

    with pytest.raises(RuntimeError):
        await run_document_extraction_job({"job_try": 2}, {"extraction_id": "ext_123"})

    assert failed_messages
    assert failed_messages[0].startswith("Indexing enqueue failed:")


@pytest.mark.asyncio
async def test_run_document_indexing_job_requires_extraction_id() -> None:
    with pytest.raises(ValueError, match="extraction_id"):
        await run_document_indexing_job({}, {})


@pytest.mark.asyncio
async def test_run_document_indexing_job_delegates_to_sync_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(extraction_id: str) -> dict[str, str]:
        return {
            "status": "indexed",
            "job": "run_document_indexing_job",
            "extraction_id": extraction_id,
            "indexed_chunk_count": 4,
            "index_name": "esg-evidence-index",
        }

    monkeypatch.setattr(jobs, "_run_indexing_sync", fake_runner)
    result = await run_document_indexing_job({}, {"extraction_id": "ext_123"})
    assert result["status"] == "indexed"
    assert result["job"] == "run_document_indexing_job"
    assert result["extraction_id"] == "ext_123"


@pytest.mark.asyncio
async def test_run_document_indexing_job_retries_on_lock_contention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(_extraction_id: str) -> dict[str, str]:
        raise RuntimeError("Indexing lock not acquired.")

    retry_calls: list[tuple[int, int]] = []

    def fake_mark_retry(
        _extraction_id: str,
        *,
        attempt: int,
        defer_seconds: int,
        error_message: str,
    ) -> None:
        assert "lock not acquired" in error_message.lower()
        retry_calls.append((attempt, defer_seconds))

    monkeypatch.setattr(jobs, "_run_indexing_sync", fake_runner)
    monkeypatch.setattr(jobs, "_mark_index_retry_state_sync", fake_mark_retry)
    monkeypatch.setattr(settings, "index_job_max_retries", 3)
    monkeypatch.setattr(settings, "index_retry_base_seconds", 2)
    monkeypatch.setattr(settings, "index_retry_max_defer_seconds", 30)

    with pytest.raises(Retry) as exc_info:
        await run_document_indexing_job({"job_try": 1}, {"extraction_id": "ext_123"})

    assert retry_calls == [(1, 2)]
    assert exc_info.value.defer_score == 2000


@pytest.mark.asyncio
async def test_run_document_indexing_job_marks_failed_after_retry_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(_extraction_id: str) -> dict[str, str]:
        raise RuntimeError("indexing failed hard")

    failed_messages: list[str] = []

    def fake_mark_failed(
        _extraction_id: str,
        *,
        error_message: str,
    ) -> None:
        failed_messages.append(error_message)

    monkeypatch.setattr(jobs, "_run_indexing_sync", fake_runner)
    monkeypatch.setattr(jobs, "_mark_index_failed_state_sync", fake_mark_failed)
    monkeypatch.setattr(settings, "index_job_max_retries", 2)

    with pytest.raises(RuntimeError):
        await run_document_indexing_job({"job_try": 2}, {"extraction_id": "ext_123"})

    assert failed_messages
    assert failed_messages[0].startswith("Retry exhausted:")


@pytest.mark.asyncio
async def test_run_report_package_job_requires_report_run_id() -> None:
    with pytest.raises(ValueError, match="report_run_id"):
        await run_report_package_job({}, {})


@pytest.mark.asyncio
async def test_run_report_package_job_delegates_to_sync_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(report_run_id: str) -> dict[str, str]:
        return {
            "status": "completed",
            "job": "run_report_package_job",
            "report_run_id": report_run_id,
            "package_job_id": "pkg_123",
            "artifact_count": 6,
        }

    monkeypatch.setattr(jobs, "_run_report_package_sync", fake_runner)

    result = await run_report_package_job({}, {"report_run_id": "run_123"})
    assert result["status"] == "completed"
    assert result["job"] == "run_report_package_job"
    assert result["report_run_id"] == "run_123"
    assert result["package_job_id"] == "pkg_123"


@pytest.mark.asyncio
async def test_run_report_package_job_retries_then_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_runner(_report_run_id: str) -> dict[str, str]:
        raise RuntimeError("package compose failed")

    retry_calls: list[tuple[int, int, str]] = []
    failed_messages: list[str] = []

    def fake_mark_retry(
        _report_run_id: str,
        *,
        attempt: int,
        defer_seconds: int,
        error_message: str,
    ) -> None:
        retry_calls.append((attempt, defer_seconds, error_message))

    def fake_mark_failed(
        _report_run_id: str,
        *,
        error_message: str,
    ) -> None:
        failed_messages.append(error_message)

    monkeypatch.setattr(jobs, "_run_report_package_sync", fake_runner)
    monkeypatch.setattr(jobs, "_mark_report_package_retry_state_sync", fake_mark_retry)
    monkeypatch.setattr(jobs, "_mark_report_package_failed_state_sync", fake_mark_failed)
    monkeypatch.setattr(settings, "package_job_max_retries", 2)
    monkeypatch.setattr(settings, "package_retry_base_seconds", 5)
    monkeypatch.setattr(settings, "package_retry_max_defer_seconds", 60)

    with pytest.raises(Retry) as exc_info:
        await run_report_package_job({"job_try": 1}, {"report_run_id": "run_retry"})
    assert retry_calls == [(1, 5, "package compose failed")]
    assert exc_info.value.defer_score == 5000

    with pytest.raises(RuntimeError):
        await run_report_package_job({"job_try": 2}, {"report_run_id": "run_retry"})
    assert failed_messages == ["Retry exhausted: package compose failed"]
