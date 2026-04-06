from urllib.parse import urlparse

from arq.connections import RedisSettings

from worker.core.settings import settings
from worker.jobs import (
    run_document_extraction_job,
    run_document_indexing_job,
    run_report_package_job,
    sample_health_job,
)


def redis_settings_from_url(redis_url: str) -> RedisSettings:
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


async def on_startup(_ctx: dict) -> None:
    return None


async def on_shutdown(_ctx: dict) -> None:
    return None


class WorkerSettings:
    functions = [
        sample_health_job,
        run_document_extraction_job,
        run_document_indexing_job,
        run_report_package_job,
    ]
    redis_settings = redis_settings_from_url(settings.redis_url)
    queue_name = settings.queue_name
    max_jobs = settings.worker_concurrency
    max_tries = max(settings.ocr_job_max_retries, settings.index_job_max_retries)
    on_startup = on_startup
    on_shutdown = on_shutdown
