from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RetrievalHints(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    section_tags: list[str] = Field(default_factory=list)
    period: str | None = None
    small_to_big: bool = False
    context_window: int = Field(default=1, ge=0, le=3)


class RetrievalQueryRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    query_text: str = Field(min_length=2)
    top_k: int = Field(default=10, ge=1, le=50)
    retrieval_mode: Literal["hybrid", "sparse", "dense"] = "hybrid"
    min_score: float = Field(default=0.0, ge=0.0)
    min_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieval_hints: RetrievalHints | None = None


class EvidenceResult(BaseModel):
    evidence_id: str
    source_document_id: str
    chunk_id: str
    page: int | None
    text: str
    score_dense: float | None
    score_sparse: float | None
    score_final: float
    metadata: dict[str, Any]


class RetrievalDiagnostics(BaseModel):
    backend: str
    retrieval_mode: str
    top_k: int
    result_count: int
    filter_hit_count: int
    coverage: float = Field(ge=0.0, le=1.0)
    best_score: float = Field(ge=0.0)
    quality_gate_passed: bool
    latency_ms: int
    index_name: str
    applied_filters: dict[str, str]


class RetrievalQueryResponse(BaseModel):
    retrieval_run_id: str
    evidence: list[EvidenceResult]
    diagnostics: RetrievalDiagnostics
