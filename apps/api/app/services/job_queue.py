from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from arq.connections import RedisSettings, create_pool

from app.core.settings import settings


class JobQueueService(Protocol):
    async def enqueue_extraction(self, extraction_id: str) -> str: ...


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

    async def enqueue_extraction(self, extraction_id: str) -> str:
        pool = await create_pool(_redis_settings_from_url(self.redis_url))
        try:
            job = await pool.enqueue_job(
                "run_document_extraction_job",
                {"extraction_id": extraction_id},
                _queue_name=self.queue_name,
            )
            if job is None:
                raise RuntimeError("Queue accepted no job handle.")
            return job.job_id
        finally:
            await pool.close()


def get_job_queue_service() -> JobQueueService:
    return ArqJobQueueService(redis_url=settings.redis_url, queue_name=settings.arq_queue_name)
