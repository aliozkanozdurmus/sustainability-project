from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from typing import Protocol

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from app.core.settings import settings


class BlobStorageService(Protocol):
    def upload_bytes(
        self,
        payload: bytes,
        blob_name: str,
        content_type: str | None,
        container: str | None = None,
    ) -> str: ...

    def download_bytes(self, storage_uri: str) -> bytes: ...


@dataclass
class LocalBlobStorageService:
    root_path: Path
    container: str

    def upload_bytes(
        self,
        payload: bytes,
        blob_name: str,
        content_type: str | None,
        container: str | None = None,
    ) -> str:
        _ = content_type
        target_container = container or self.container
        target = self.root_path / target_container / blob_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return f"file://{target.resolve().as_posix()}"

    def download_bytes(self, storage_uri: str) -> bytes:
        if not storage_uri.startswith("file://"):
            raise ValueError("Local blob storage supports only file:// URIs.")
        path = Path(storage_uri.replace("file://", ""))
        return path.read_bytes()


@dataclass
class AzureBlobStorageService:
    container: str
    service_client: BlobServiceClient

    def upload_bytes(
        self,
        payload: bytes,
        blob_name: str,
        content_type: str | None,
        container: str | None = None,
    ) -> str:
        target_container = container or self.container
        container_client = self.service_client.get_container_client(target_container)
        try:
            container_client.create_container()
        except Exception:
            # Container may already exist. Let upload surface real failures.
            pass

        blob_client = container_client.get_blob_client(blob=blob_name)
        content_settings = ContentSettings(content_type=content_type) if content_type else None
        blob_client.upload_blob(payload, overwrite=True, content_settings=content_settings)
        return blob_client.url

    def download_bytes(self, storage_uri: str) -> bytes:
        parsed = urlparse(storage_uri)
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) < 2:
            raise ValueError("Invalid Azure blob URI.")
        container = path_parts[0]
        blob_name = "/".join(path_parts[1:])
        blob_client = self.service_client.get_blob_client(container=container, blob=blob_name)
        return blob_client.download_blob().readall()


def _build_azure_client() -> BlobServiceClient:
    if settings.azure_storage_connection_string:
        return BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)

    if not settings.azure_storage_account_name:
        raise ValueError("AZURE_STORAGE_ACCOUNT_NAME must be set when local blob mode is disabled.")

    account_url = f"https://{settings.azure_storage_account_name}.blob.core.windows.net"
    return BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())


def get_blob_storage_service() -> BlobStorageService:
    if settings.azure_storage_use_local:
        return LocalBlobStorageService(
            root_path=settings.local_blob_root_path,
            container=settings.azure_storage_container_raw,
        )

    return AzureBlobStorageService(
        container=settings.azure_storage_container_raw,
        service_client=_build_azure_client(),
    )
