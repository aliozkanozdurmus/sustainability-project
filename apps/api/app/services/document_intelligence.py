# Bu servis, document_intelligence akisindaki uygulama mantigini tek yerde toplar.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from fastapi import Request

from app.core.settings import settings


@dataclass
class OcrPage:
    page_number: int
    text: str


@dataclass
class OcrResult:
    full_text: str
    pages: list[OcrPage]
    raw_payload: dict[str, Any]
    model_id: str


class DocumentIntelligenceService(Protocol):
    def analyze_document(
        self,
        payload: bytes,
        content_type: str | None = None,
    ) -> OcrResult: ...


@dataclass
class AzureDocumentIntelligenceService:
    client: DocumentIntelligenceClient
    model_id: str = "prebuilt-layout"

    def analyze_document(
        self,
        payload: bytes,
        content_type: str | None = None,
    ) -> OcrResult:
        poller = self.client.begin_analyze_document(
            model_id=self.model_id,
            body=payload,
            content_type=content_type or "application/octet-stream",
        )
        result = poller.result()
        pages: list[OcrPage] = []
        for page in result.pages or []:
            lines = [line.content for line in page.lines or [] if line.content]
            page_text = "\n".join(lines).strip()
            pages.append(OcrPage(page_number=page.page_number or len(pages) + 1, text=page_text))

        raw_payload = result.as_dict() if hasattr(result, "as_dict") else {}
        return OcrResult(
            full_text=(result.content or "").strip(),
            pages=pages,
            raw_payload=raw_payload,
            model_id=self.model_id,
        )

    def close(self) -> None:
        self.client.close()


def create_document_intelligence_service() -> DocumentIntelligenceService:
    if not settings.azure_document_intelligence_endpoint:
        raise ValueError("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT must be set.")
    if not settings.azure_document_intelligence_api_key:
        raise ValueError("AZURE_DOCUMENT_INTELLIGENCE_API_KEY must be set.")

    client = DocumentIntelligenceClient(
        endpoint=settings.azure_document_intelligence_endpoint,
        credential=AzureKeyCredential(settings.azure_document_intelligence_api_key),
        api_version=settings.azure_document_intelligence_api_version,
    )
    return AzureDocumentIntelligenceService(client=client)


def get_document_intelligence_service(request: Request = None) -> DocumentIntelligenceService:
    runtime_state = getattr(getattr(request, "app", None), "state", None)
    runtime_services = getattr(runtime_state, "runtime_services", None) if runtime_state is not None else None
    if runtime_services is not None and runtime_services.document_intelligence is not None:
        return runtime_services.document_intelligence
    return create_document_intelligence_service()
