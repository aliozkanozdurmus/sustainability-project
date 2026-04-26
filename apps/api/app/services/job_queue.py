# Bu servis, job_queue akisindaki uygulama mantigini tek yerde toplar.

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from arq.connections import RedisSettings, create_pool
from fastapi import Request

from app.core.settings import settings
from app.telemetry import observe_operation


class JobQueueService(Protocol):
    async def enqueue_extraction(self, extraction_id: str) -> str: ...
    async def enqueue_report_package(self, report_run_id: str, *, package_job_id: str | None = None) -> str: ...


def _redis_settings_from_url(redis_url: str) -> RedisSettings:
    parsed = urlparse(redis_url)
    db = 0
    if parsed.path and parsed.path != "/":
        db = int(parsed.path.strip("/"))
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=db,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


@dataclass
class ArqJobQueueService:
    redis_url: str
    queue_name: str

    async def _enqueue_job(
        self,
        function_name: str,
        payload: dict[str, str],
        *,
        job_id: str | None = None,
    ) -> str:
        with observe_operation(
            "job_queue.enqueue",
            attributes={
                "queue.name": self.queue_name,
                "job.function": function_name,
                "job.id": job_id,
            },
        ):
            pool = await create_pool(_redis_settings_from_url(self.redis_url))
            try:
                job = await pool.enqueue_job(
                    function_name,
                    payload,
                    _job_id=job_id,
                    _queue_name=self.queue_name,
                )
                if job is None:
                    if job_id:
                        return job_id
                    raise RuntimeError("Queue accepted no job handle.")
                return str(job.job_id)
            finally:
                await pool.close()

    async def enqueue_extraction(self, extraction_id: str) -> str:
        return await self._enqueue_job(
            "run_document_extraction_job",
            {"extraction_id": extraction_id},
        )

    async def enqueue_report_package(self, report_run_id: str, *, package_job_id: str | None = None) -> str:
        return await self._enqueue_job(
            "run_report_package_job",
            {
                "report_run_id": report_run_id,
                "package_job_id": package_job_id or "",
            },
            job_id=package_job_id,
        )


    async def close(self) -> None:
        return None


def create_job_queue_service() -> JobQueueService:
    return ArqJobQueueService(redis_url=settings.redis_url, queue_name=settings.arq_queue_name)


def get_job_queue_service(request: Request = None) -> JobQueueService:
    runtime_state = getattr(getattr(request, "app", None), "state", None)
    runtime_services = getattr(runtime_state, "runtime_services", None) if runtime_state is not None else None
    if runtime_services is not None:
        return runtime_services.job_queue
    return create_job_queue_service()
