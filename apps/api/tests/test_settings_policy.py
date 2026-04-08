# Bu test dosyasi, settings policy davranisini dogrular.

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.settings import Settings, _default_env_files


NEON_DATABASE_URL = "postgresql+asyncpg://user:password@demo-project.neon.tech/neondb?sslmode=require"
LOCAL_DEV_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@postgres:5432/sustainability"


def test_settings_accepts_locked_model_stack_and_neon_database() -> None:
    settings = Settings(
        _env_file=None,
        database_url=NEON_DATABASE_URL,
        azure_openai_chat_deployment="gpt-5.2",
        azure_openai_embedding_deployment="text-embedding-3-large",
    )

    assert settings.azure_openai_chat_deployment == "gpt-5.2"
    assert settings.azure_openai_embedding_deployment == "text-embedding-3-large"
    assert settings.database_sync_url.startswith("postgresql+psycopg://")


def test_settings_maps_generic_postgres_url_to_psycopg_sync_url() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@demo-project.neon.tech/neondb?sslmode=require",
        azure_openai_chat_deployment="gpt-5.2",
        azure_openai_embedding_deployment="text-embedding-3-large",
    )

    assert settings.database_sync_url.startswith("postgresql+psycopg://")


def test_settings_env_file_chain_uses_repo_root_only() -> None:
    env_files = _default_env_files()

    repo_root = Path(__file__).resolve().parents[3]
    assert env_files
    assert env_files == (str(repo_root / ".env"),)
    assert Settings.model_config["env_file"] == env_files


def test_settings_resolves_local_storage_paths_from_repo_root() -> None:
    settings = Settings(
        _env_file=None,
        database_url=NEON_DATABASE_URL,
        azure_openai_chat_deployment="gpt-5.2",
        azure_openai_embedding_deployment="text-embedding-3-large",
        local_blob_root="apps/api/storage",
        local_search_index_root="apps/api/storage/search-index",
        local_checkpoint_root="apps/api/storage/checkpoints",
    )

    repo_root = Path(__file__).resolve().parents[3]
    assert settings.local_blob_root_path == (repo_root / "apps" / "api" / "storage").resolve()
    assert settings.local_search_index_root_path == (
        repo_root / "apps" / "api" / "storage" / "search-index"
    ).resolve()
    assert settings.local_checkpoint_root_path == (
        repo_root / "apps" / "api" / "storage" / "checkpoints"
    ).resolve()


def test_settings_rejects_non_neon_database_host() -> None:
    with pytest.raises(ValidationError, match=r"Neon PostgreSQL host"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:password@localhost:5432/sustainability",
        )


def test_settings_accepts_local_database_for_explicit_development_override() -> None:
    settings = Settings(
        _env_file=None,
        app_env="development",
        allow_local_dev_database=True,
        database_url=LOCAL_DEV_DATABASE_URL,
        azure_openai_chat_deployment="gpt-5.2",
        azure_openai_embedding_deployment="text-embedding-3-large",
    )

    assert settings.database_url == LOCAL_DEV_DATABASE_URL


def test_settings_rejects_local_database_override_outside_development() -> None:
    with pytest.raises(ValidationError, match=r"Neon PostgreSQL host"):
        Settings(
            _env_file=None,
            app_env="production",
            allow_local_dev_database=True,
            database_url=LOCAL_DEV_DATABASE_URL,
        )


def test_settings_rejects_disallowed_chat_model() -> None:
    with pytest.raises(ValidationError, match=r"AZURE_OPENAI_CHAT_DEPLOYMENT"):
        Settings(
            _env_file=None,
            database_url=NEON_DATABASE_URL,
            azure_openai_chat_deployment="gpt-4.1",
        )


def test_settings_rejects_disallowed_embedding_model() -> None:
    with pytest.raises(ValidationError, match=r"AZURE_OPENAI_EMBEDDING_DEPLOYMENT"):
        Settings(
            _env_file=None,
            database_url=NEON_DATABASE_URL,
            azure_openai_embedding_deployment="text-embedding-3-small",
        )
