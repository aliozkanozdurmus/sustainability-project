# Bu test dosyasi, worker settings davranisini dogrular.

from pathlib import Path

import pytest
from pydantic import ValidationError

from worker.app import WorkerSettings, redis_settings_from_url
from worker.core.settings import WorkerRuntimeSettings, _default_env_files


NEON_DATABASE_URL = "postgresql+asyncpg://user:password@demo-project.neon.tech/neondb?sslmode=require"
LOCAL_DEV_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@postgres:5432/sustainability"


def test_worker_settings_registers_sample_job() -> None:
    job_names = [f.__name__ for f in WorkerSettings.functions]
    assert "sample_health_job" in job_names
    assert "run_document_extraction_job" in job_names
    assert "run_document_indexing_job" in job_names
    assert "run_report_package_job" in job_names
    assert WorkerSettings.queue_name == "arq:queue"
    assert WorkerSettings.max_tries >= 1


def test_redis_settings_parser() -> None:
    parsed = redis_settings_from_url("rediss://user:pass@example.com:6380/2")
    assert parsed.host == "example.com"
    assert parsed.port == 6380
    assert parsed.database == 2
    assert parsed.username == "user"
    assert parsed.password == "pass"
    assert parsed.ssl is True


def test_worker_runtime_settings_lock_model_and_database_policy() -> None:
    settings = WorkerRuntimeSettings(
        _env_file=None,
        database_url=NEON_DATABASE_URL,
        azure_openai_chat_deployment="gpt-5.2",
        azure_openai_embedding_deployment="text-embedding-3-large",
    )

    assert settings.azure_openai_chat_deployment == "gpt-5.2"
    assert settings.azure_openai_embedding_deployment == "text-embedding-3-large"


def test_worker_runtime_settings_rejects_non_neon_database() -> None:
    with pytest.raises(ValidationError, match=r"Neon PostgreSQL host"):
        WorkerRuntimeSettings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:password@localhost:5432/sustainability",
        )


def test_worker_runtime_settings_accepts_local_database_for_explicit_development_override() -> None:
    settings = WorkerRuntimeSettings(
        _env_file=None,
        app_env="development",
        allow_local_dev_database=True,
        database_url=LOCAL_DEV_DATABASE_URL,
        azure_openai_chat_deployment="gpt-5.2",
        azure_openai_embedding_deployment="text-embedding-3-large",
    )

    assert settings.database_url == LOCAL_DEV_DATABASE_URL


def test_worker_runtime_settings_rejects_local_override_outside_development() -> None:
    with pytest.raises(ValidationError, match=r"Neon PostgreSQL host"):
        WorkerRuntimeSettings(
            _env_file=None,
            app_env="production",
            allow_local_dev_database=True,
            database_url=LOCAL_DEV_DATABASE_URL,
        )


def test_worker_env_file_chain_includes_repo_root_before_service_env() -> None:
    env_files = _default_env_files()

    repo_root = Path(__file__).resolve().parents[3]
    assert env_files
    assert env_files[0] == str(repo_root / ".env")
    assert str(repo_root / "services" / "worker" / ".env") in env_files
    assert WorkerRuntimeSettings.model_config["env_file"] == env_files
