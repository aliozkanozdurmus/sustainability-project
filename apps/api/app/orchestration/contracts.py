from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowContractModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CitationSpan(WorkflowContractModel):
    source_document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    span_start: int = Field(default=0, ge=0)
    span_end: int = Field(default=1, ge=1)
    page: int | None = None

    @model_validator(mode="after")
    def validate_span_bounds(self) -> "CitationSpan":
        if self.span_end <= self.span_start:
            self.span_end = self.span_start + 1
        return self


class TaskEnvelope(WorkflowContractModel):
    task_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    framework_target: str = Field(min_length=1)
    section_target: str = Field(min_length=1)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    deadline_utc: str | None = None
    query_text: str = Field(min_length=1)
    retrieval_mode: Literal["hybrid", "sparse", "dense"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0)
    min_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    retrieval_hints: dict[str, Any] | None = None
    status: str = "planned"


class ScopeDecision(WorkflowContractModel):
    decision_id: str | None = None
    jurisdiction_code: str | None = None
    in_scope: bool | None = None
    required_frameworks: list[str] = Field(default_factory=list)
    legal_instrument_refs: list[str] = Field(default_factory=list)
    transition_reliefs_applied: list[str] = Field(default_factory=list)
    rule_version: str | None = None
    snapshot_date: date | str | None = None
    mode: str | None = None
    retrieval_defaults: dict[str, Any] = Field(default_factory=dict)
    retrieval_tasks: list[dict[str, Any]] = Field(default_factory=list)
    quality_policy: dict[str, Any] = Field(default_factory=dict)
    verifier_policy: dict[str, Any] = Field(default_factory=dict)
    simulate_failures: dict[str, int] = Field(default_factory=dict)


class ReadinessScorecard(WorkflowContractModel):
    run_id: str | None = None
    completeness_score: float | None = None
    evidence_quality_score: float | None = None
    traceability_score: float | None = None
    numeric_reliability_score: float | None = None
    blocking_issues: list[str] = Field(default_factory=list)
    advisory_issues: list[str] = Field(default_factory=list)
    status: str | None = None
    applicability_resolved: bool | None = None
    framework_target: list[str] = Field(default_factory=list)


class EvidenceMetadata(WorkflowContractModel):
    section_label: str | None = None
    period: str | None = None
    framework_tags: list[str] = Field(default_factory=list)
    document_type: str | None = None
    quality_grade: str | None = None
    quality_score: float | None = None
    owner: str | None = None
    issued_at: str | None = None
    chunk_index: int | None = None
    token_count: int | None = None
    matched_terms: list[str] = Field(default_factory=list)
    ranking_breakdown: dict[str, float | int | str | None] = Field(default_factory=dict)
    source_quality: dict[str, Any] = Field(default_factory=dict)


class EvidenceBlock(WorkflowContractModel):
    evidence_id: str = Field(min_length=1)
    task_id: str | None = None
    framework: str | None = None
    section_target: str | None = None
    query_text: str | None = None
    source_document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    page: int | None = None
    text: str
    score_dense: float | None = None
    score_sparse: float | None = None
    score_final: float = Field(ge=0.0)
    quality_grade: str | None = None
    quality_score: float | None = None
    metadata: EvidenceMetadata = Field(default_factory=EvidenceMetadata)
    citations: list[CitationSpan] = Field(default_factory=list)


class CalculationResult(WorkflowContractModel):
    calc_id: str = Field(min_length=1)
    evidence_id: str | None = None
    claim_id: str | None = None
    status: str = "completed"
    formula_name: str = Field(min_length=1)
    code_hash: str = Field(min_length=1)
    inputs_ref: str = Field(min_length=1)
    output_value: float | None = None
    output_unit: str | None = None
    trace_log_ref: str = Field(min_length=1)
    normalization_policy_ref: str = Field(min_length=1)


class Claim(WorkflowContractModel):
    claim_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    is_numeric: bool = False
    citations: list[CitationSpan] = Field(default_factory=list)
    calculation_refs: list[str] = Field(default_factory=list)
    evidence_id: str | None = None
    confidence: float | None = None


class DraftSection(WorkflowContractModel):
    section_code: str = Field(min_length=1)
    status: str = "drafted"
    claims: list[Claim] = Field(default_factory=list)
    claim_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def sync_claim_count(self) -> "DraftSection":
        self.claim_count = len(self.claims)
        return self


class VerificationResultContract(WorkflowContractModel):
    claim_id: str = Field(min_length=1)
    section_code: str | None = None
    status: Literal["PASS", "FAIL", "UNSURE"]
    severity: Literal["normal", "critical"] = "normal"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    blocking: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    citation_span_refs: list[CitationSpan] = Field(default_factory=list)
