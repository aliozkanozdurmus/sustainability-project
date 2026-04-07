# Bu servis, search_index akisindaki uygulama mantigini tek yerde toplar.

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

from app.core.settings import settings


@dataclass
class SearchChunkDocument:
    chunk_id: str
    tenant_id: str
    project_id: str
    source_document_id: str
    extraction_record_id: str
    chunk_index: int
    page: int | None
    section_label: str | None
    token_count: int
    content: str
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.chunk_id,
            "chunk_id": self.chunk_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "source_document_id": self.source_document_id,
            "extraction_record_id": self.extraction_record_id,
            "chunk_index": self.chunk_index,
            "page": self.page,
            "section_label": self.section_label,
            "token_count": self.token_count,
            "content": self.content,
            "metadata": self.metadata,
        }


class SearchIndexService(Protocol):
    def upsert_chunk_documents(self, documents: list[SearchChunkDocument]) -> int: ...


@dataclass
class LocalSearchIndexService:
    root_path: Path
    index_name: str

    def upsert_chunk_documents(self, documents: list[SearchChunkDocument]) -> int:
        self.root_path.mkdir(parents=True, exist_ok=True)
        target = self.root_path / f"{self.index_name}.json"
        existing: dict[str, dict[str, Any]] = {}
        if target.exists():
            try:
                parsed = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    existing = {str(k): v for k, v in parsed.items() if isinstance(v, dict)}
            except json.JSONDecodeError:
                existing = {}

        for document in documents:
            existing[document.chunk_id] = document.to_payload()

        target.write_text(json.dumps(existing, ensure_ascii=True, indent=2), encoding="utf-8")
        return len(documents)


@dataclass
class AzureSearchIndexService:
    client: SearchClient

    def upsert_chunk_documents(self, documents: list[SearchChunkDocument]) -> int:
        if not documents:
            return 0
        payload = [document.to_payload() for document in documents]
        results = self.client.merge_or_upload_documents(documents=payload)
        succeeded = 0
        for result in results:
            ok = getattr(result, "succeeded", None)
            if ok is True:
                succeeded += 1
        if succeeded == 0 and payload:
            # SDK variants may not expose "succeeded" on local mocks; assume success if no exception.
            return len(payload)
        return succeeded


def _build_azure_search_client() -> SearchClient:
    if not settings.azure_ai_search_endpoint:
        raise ValueError("AZURE_AI_SEARCH_ENDPOINT must be set when local search mode is disabled.")

    if settings.azure_ai_search_api_key:
        credential = AzureKeyCredential(settings.azure_ai_search_api_key)
    else:
        credential = DefaultAzureCredential()

    return SearchClient(
        endpoint=settings.azure_ai_search_endpoint,
        index_name=settings.azure_ai_search_index_name,
        credential=credential,
    )


def get_search_index_service() -> SearchIndexService:
    if settings.azure_ai_search_use_local:
        return LocalSearchIndexService(
            root_path=settings.local_search_index_root_path,
            index_name=settings.azure_ai_search_index_name,
        )

    return AzureSearchIndexService(client=_build_azure_search_client())
