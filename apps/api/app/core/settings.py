# Bu cekirdek modul, settings icin calisma zamani varsayimlarini toplar.

from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_env_files() -> tuple[str, ...]:
    repo_root = Path(__file__).resolve().parents[4]
    return (str(repo_root / ".env"),)


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


class Settings(BaseSettings):
    allowed_chat_model: ClassVar[str] = "gpt-5.2"
    allowed_embedding_model: ClassVar[str] = "text-embedding-3-large"
    allowed_image_models: ClassVar[set[str]] = {"gpt-image-1", "gpt-image-1.5"}
    repo_root: ClassVar[Path] = Path(__file__).resolve().parents[4]

    app_name: str = Field(default="Veni AI Sustainability Cockpit API")
    app_env: str = Field(default="development")
    api_prefix: str = Field(default="")
    api_version: str = Field(default="v1")
    cors_allow_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000")
    allow_local_dev_database: bool = Field(default=False)
    database_url: str = Field(
        default="postgresql+asyncpg://username:password@project.neon.tech/neondb?sslmode=require"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    arq_queue_name: str = Field(default="arq:queue")
    azure_storage_account_name: str | None = Field(default=None)
    azure_storage_connection_string: str | None = Field(default=None)
    azure_storage_container_raw: str = Field(default="raw-documents")
    azure_storage_container_parsed: str = Field(default="parsed-documents")
    azure_storage_container_artifacts: str = Field(default="report-artifacts")
    azure_storage_use_local: bool = Field(default=True)
    local_blob_root: str = Field(default="apps/api/storage")
    azure_document_intelligence_endpoint: str | None = Field(default=None)
    azure_document_intelligence_api_key: str | None = Field(default=None)
    azure_document_intelligence_api_version: str = Field(default="2024-11-30")
    azure_ai_search_endpoint: str | None = Field(default=None)
    azure_ai_search_api_key: str | None = Field(default=None)
    azure_ai_search_index_name: str = Field(default="esg-evidence-index")
    azure_ai_search_use_local: bool = Field(default=True)
    local_search_index_root: str = Field(default="apps/api/storage/search-index")
    local_checkpoint_root: str = Field(default="apps/api/storage/checkpoints")
    workflow_retry_max_per_node: int = Field(default=2)
    workflow_retry_base_seconds: int = Field(default=2)
    workflow_retry_max_defer_seconds: int = Field(default=30)
    workflow_execute_max_steps: int = Field(default=64)
    azure_openai_endpoint: str | None = Field(default=None)
    azure_openai_api_key: str | None = Field(default=None)
    azure_openai_api_version: str = Field(default="2024-10-21")
    azure_openai_chat_deployment: str = Field(default="gpt-5.2")
    azure_openai_embedding_deployment: str = Field(default="text-embedding-3-large")
    azure_openai_image_deployment: str | None = Field(default=None)
    azure_openai_image_fallback_deployment: str | None = Field(default=None)
    verifier_mode: str = Field(default="heuristic")
    verifier_pass_threshold: float = Field(default=0.55)
    verifier_unsure_threshold: float = Field(default=0.3)
    report_factory_default_blueprint_version: str = Field(default="brandable-tr-v1")
    report_factory_default_locale: str = Field(default="tr-TR")
    connector_operations_inline_fallback: bool = Field(default=True)
    connector_agent_stale_after_seconds: int = Field(default=300)
    otel_enabled: bool = Field(default=False)
    otel_service_name: str = Field(default="veni-ai-sustainability-cockpit-api")
    otel_exporter_otlp_endpoint: str | None = Field(default=None)
    otel_exporter_otlp_headers: str | None = Field(default=None)
    otel_console_export: bool = Field(default=False)

    @model_validator(mode="after")
    def enforce_locked_ai_and_database_policy(self) -> "Settings":
        if self.azure_openai_chat_deployment.strip() != self.allowed_chat_model:
            raise ValueError(
                f"AZURE_OPENAI_CHAT_DEPLOYMENT must be '{self.allowed_chat_model}'."
            )

        if self.azure_openai_embedding_deployment.strip() != self.allowed_embedding_model:
            raise ValueError(
                f"AZURE_OPENAI_EMBEDDING_DEPLOYMENT must be '{self.allowed_embedding_model}'."
            )

        if (
            self.azure_openai_image_deployment
            and self.azure_openai_image_deployment.strip() not in self.allowed_image_models
        ):
            raise ValueError(
                "AZURE_OPENAI_IMAGE_DEPLOYMENT must be one of "
                f"{sorted(self.allowed_image_models)}."
            )
        if (
            self.azure_openai_image_fallback_deployment
            and self.azure_openai_image_fallback_deployment.strip() not in self.allowed_image_models
        ):
            raise ValueError(
                "AZURE_OPENAI_IMAGE_FALLBACK_DEPLOYMENT must be one of "
                f"{sorted(self.allowed_image_models)}."
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

    @property
    def database_sync_url(self) -> str:
        database_url = self.database_url.strip()
        if database_url.startswith("postgresql+asyncpg://"):
            return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return database_url

    def resolve_repo_path(self, value: str) -> Path:
        raw = Path(value)
        if raw.is_absolute():
            return raw
        return (self.repo_root / raw).resolve()

    @property
    def local_blob_root_path(self) -> Path:
        return self.resolve_repo_path(self.local_blob_root)

    @property
    def local_search_index_root_path(self) -> Path:
        return self.resolve_repo_path(self.local_search_index_root)

    @property
    def local_checkpoint_root_path(self) -> Path:
        return self.resolve_repo_path(self.local_checkpoint_root)

    model_config = SettingsConfigDict(
        env_file=_default_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
