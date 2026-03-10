from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_env_files() -> tuple[str, ...]:
    repo_root = Path(__file__).resolve().parents[4]
    candidates = (
        repo_root / ".env",
        repo_root / "services" / "worker" / ".env",
    )
    return tuple(str(path) for path in candidates)


def _is_local_dev_database_host(database_url: str) -> bool:
    hostname = (urlparse(database_url).hostname or "").strip().lower()
    return hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
        "postgres",
        "db",
        "host.docker.internal",
    }


class WorkerRuntimeSettings(BaseSettings):
    allowed_chat_model: ClassVar[str] = "gpt-5.2"
    allowed_embedding_model: ClassVar[str] = "text-embedding-3-large"

    app_env: str = Field(default="development")
    allow_local_dev_database: bool = Field(default=False)
    worker_concurrency: int = Field(default=4)
    database_url: str = Field(
        default="postgresql+asyncpg://username:password@project.neon.tech/neondb?sslmode=require"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    queue_name: str = Field(default="arq:queue")
    ocr_job_max_retries: int = Field(default=3)
    ocr_retry_base_seconds: int = Field(default=2)
    ocr_retry_max_defer_seconds: int = Field(default=30)
    index_job_max_retries: int = Field(default=3)
    index_retry_base_seconds: int = Field(default=2)
    index_retry_max_defer_seconds: int = Field(default=30)
    azure_openai_chat_deployment: str = Field(default="gpt-5.2")
    azure_openai_embedding_deployment: str = Field(default="text-embedding-3-large")

    @model_validator(mode="after")
    def enforce_locked_ai_and_database_policy(self) -> "WorkerRuntimeSettings":
        if self.azure_openai_chat_deployment.strip() != self.allowed_chat_model:
            raise ValueError(
                f"AZURE_OPENAI_CHAT_DEPLOYMENT must be '{self.allowed_chat_model}'."
            )

        if self.azure_openai_embedding_deployment.strip() != self.allowed_embedding_model:
            raise ValueError(
                f"AZURE_OPENAI_EMBEDDING_DEPLOYMENT must be '{self.allowed_embedding_model}'."
            )

        normalized_database_url = self.database_url.strip().lower()
        if not normalized_database_url.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("DATABASE_URL must use PostgreSQL (Neon PostgreSQL).")

        if ".neon.tech" not in normalized_database_url:
            if (
                self.allow_local_dev_database
                and self.app_env.strip().lower() == "development"
                and _is_local_dev_database_host(self.database_url)
            ):
                return self
            raise ValueError("DATABASE_URL must point to a Neon PostgreSQL host (*.neon.tech).")

        return self

    model_config = SettingsConfigDict(
        env_file=_default_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = WorkerRuntimeSettings()
