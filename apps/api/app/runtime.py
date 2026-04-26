from __future__ import annotations

from dataclasses import dataclass
import inspect

from fastapi import FastAPI, Request

from app.services.blob_storage import BlobStorageService, create_blob_storage_service
from app.services.document_intelligence import (
    DocumentIntelligenceService,
    create_document_intelligence_service,
)
from app.services.job_queue import JobQueueService, create_job_queue_service
from app.services.search_index import SearchIndexService, create_search_index_service


# Veni AI API katmaninda paylasilan servisleri tek noktadan tasiyoruz;
# boylece her request'te yeni Azure/queue client'i acmak zorunda kalmiyoruz.
@dataclass(slots=True)
class AppRuntimeServices:
    blob_storage: BlobStorageService
    document_intelligence: DocumentIntelligenceService | None
    search_index: SearchIndexService
    job_queue: JobQueueService


def build_app_runtime_services() -> AppRuntimeServices:
    document_intelligence: DocumentIntelligenceService | None = None
    try:
        # OCR servisi bazi ortamlarda bilincli olarak kapali olabilir;
        # bu durumda uygulama komple dusmek yerine ilgili endpoint 503 doner.
        document_intelligence = create_document_intelligence_service()
    except ValueError:
        document_intelligence = None

    return AppRuntimeServices(
        blob_storage=create_blob_storage_service(),
        document_intelligence=document_intelligence,
        search_index=create_search_index_service(),
        job_queue=create_job_queue_service(),
    )


def bind_runtime_services(app: FastAPI, runtime_services: AppRuntimeServices) -> None:
    app.state.runtime_services = runtime_services


def resolve_runtime_services(request: Request | None = None) -> AppRuntimeServices | None:
    if request is None:
        return None
    runtime_services = getattr(request.app.state, "runtime_services", None)
    return runtime_services if isinstance(runtime_services, AppRuntimeServices) else None


async def _close_service(service: object | None) -> None:
    if service is None:
        return
    close_method = getattr(service, "close", None)
    if not callable(close_method):
        return
    result = close_method()
    if inspect.isawaitable(result):
        await result


async def shutdown_app_runtime_services(runtime_services: AppRuntimeServices | None) -> None:
    if runtime_services is None:
        return

    # Kapanis sirasini deterministik tutuyoruz; package ve retrieval akislarinin
    # dayandigi client'lar kontrollu sekilde serbest birakiliyor.
    for service in (
        runtime_services.document_intelligence,
        runtime_services.search_index,
        runtime_services.job_queue,
        runtime_services.blob_storage,
    ):
        await _close_service(service)
