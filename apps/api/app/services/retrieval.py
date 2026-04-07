# Bu servis, retrieval akisindaki uygulama mantigini tek yerde toplar.

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import re
from time import perf_counter
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

from app.core.settings import settings
from app.schemas.retrieval import EvidenceResult, RetrievalDiagnostics, RetrievalHints


@dataclass
class RetrievalOutcome:
    evidence: list[EvidenceResult]
    diagnostics: RetrievalDiagnostics


class RetrievalQualityGateError(RuntimeError):
    def __init__(self, *, diagnostics: RetrievalDiagnostics, reason: str) -> None:
        super().__init__(reason)
        self.diagnostics = diagnostics
        self.reason = reason


@dataclass
class RetrievalStats:
    evidence: list[EvidenceResult]
    filter_hit_count: int
    query_token_count: int
    matched_query_token_count: int
    best_score: float


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"\w+", text.lower()) if token}


def _sparse_score(query_tokens: set[str], content_tokens: set[str]) -> float:
    if not query_tokens or not content_tokens:
        return 0.0
    return len(query_tokens.intersection(content_tokens)) / len(query_tokens)


def _dense_score(query_text: str, content_text: str) -> float:
    if not query_text.strip() or not content_text.strip():
        return 0.0
    return SequenceMatcher(None, query_text.lower(), content_text.lower()).ratio()


def _final_score(mode: str, sparse: float, dense: float) -> float:
    if mode == "sparse":
        return sparse
    if mode == "dense":
        return dense
    return (0.6 * sparse) + (0.4 * dense)


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


def _compute_coverage(query_token_count: int, matched_query_token_count: int) -> float:
    if query_token_count <= 0:
        return 0.0
    return round(matched_query_token_count / query_token_count, 6)


def _load_local_index() -> dict[str, dict[str, Any]]:
    target = settings.local_search_index_root_path / f"{settings.azure_ai_search_index_name}.json"
    if not target.exists():
        return {}
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return {str(k): v for k, v in parsed.items() if isinstance(v, dict)}
    except json.JSONDecodeError:
        return {}
    return {}


def _normalized_lower_list(values: list[str]) -> list[str]:
    return [value.strip().lower() for value in values if value.strip()]


def _build_augmented_query(query_text: str, hints: RetrievalHints | None) -> str:
    if hints is None:
        return query_text
    fragments: list[str] = [query_text]
    fragments.extend(hints.keywords)
    fragments.extend(hints.section_tags)
    if hints.period:
        fragments.append(hints.period)
    return " ".join(part.strip() for part in fragments if part and part.strip())


def _row_matches_hints(row: dict[str, Any], hints: RetrievalHints | None) -> bool:
    if hints is None:
        return True

    section_tags = _normalized_lower_list(hints.section_tags)
    period = hints.period.strip().lower() if hints.period else None

    section_label = str(row.get("section_label", "") or "").lower()
    content = str(row.get("content", "") or "").lower()

    if section_tags and not any(tag in section_label or tag in content for tag in section_tags):
        return False

    if period and period not in content and period not in section_label:
        metadata = row.get("metadata")
        if isinstance(metadata, dict):
            period_value = str(metadata.get("period", "") or "").lower()
            if period_value != period:
                return False
        else:
            return False

    return True


def _to_chunk_index(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _build_evidence_result(
    *,
    row: dict[str, Any],
    sparse: float | None,
    dense: float | None,
    final: float,
) -> EvidenceResult:
    chunk_id = str(row.get("chunk_id", row.get("id", "")))
    token_count_raw = row.get("token_count")
    token_count = token_count_raw if isinstance(token_count_raw, int) else None
    return EvidenceResult(
        evidence_id=chunk_id,
        source_document_id=str(row.get("source_document_id", "")),
        chunk_id=chunk_id,
        page=row.get("page"),
        text=str(row.get("content", "") or ""),
        score_dense=round(dense, 6) if dense is not None else None,
        score_sparse=round(sparse, 6) if sparse is not None else None,
        score_final=round(final, 6),
        metadata={
            "section_label": row.get("section_label"),
            "chunk_index": row.get("chunk_index"),
            "token_count": token_count,
        },
    )


def _expand_small_to_big_local(
    *,
    anchors: list[EvidenceResult],
    row_lookup: dict[tuple[str, int], dict[str, Any]],
    query_text: str,
    query_tokens: set[str],
    retrieval_mode: str,
    context_window: int,
) -> list[EvidenceResult]:
    selected: list[EvidenceResult] = []
    seen_chunk_ids: set[str] = set()

    for anchor in anchors:
        if anchor.chunk_id not in seen_chunk_ids:
            selected.append(anchor)
            seen_chunk_ids.add(anchor.chunk_id)

        source_document_id = anchor.source_document_id
        chunk_index_value = anchor.metadata.get("chunk_index")
        chunk_index = _to_chunk_index(chunk_index_value)
        if chunk_index is None:
            continue

        for offset in range(-context_window, context_window + 1):
            if offset == 0:
                continue
            neighbor_index = chunk_index + offset
            if neighbor_index < 0:
                continue
            neighbor = row_lookup.get((source_document_id, neighbor_index))
            if neighbor is None:
                continue
            neighbor_chunk_id = str(neighbor.get("chunk_id", neighbor.get("id", "")))
            if neighbor_chunk_id in seen_chunk_ids:
                continue

            neighbor_text = str(neighbor.get("content", "") or "")
            content_tokens = _tokenize(neighbor_text)
            sparse = _sparse_score(query_tokens, content_tokens)
            dense = _dense_score(query_text, neighbor_text)
            final = _final_score(retrieval_mode, sparse, dense)

            selected.append(
                _build_evidence_result(
                    row=neighbor,
                    sparse=sparse,
                    dense=dense,
                    final=final,
                )
            )
            seen_chunk_ids.add(neighbor_chunk_id)

    return selected


def _quality_gate_passes(
    *,
    result_count: int,
    best_score: float,
    coverage: float,
    min_score: float,
    min_coverage: float,
) -> bool:
    return result_count > 0 and best_score >= min_score and coverage >= min_coverage


def retrieve_evidence(
    *,
    tenant_id: str,
    project_id: str,
    query_text: str,
    top_k: int,
    retrieval_mode: str,
    min_score: float,
    min_coverage: float,
    retrieval_hints: RetrievalHints | None,
) -> RetrievalOutcome:
    started = perf_counter()
    hints = retrieval_hints
    if settings.azure_ai_search_use_local:
        stats = _retrieve_local(
            tenant_id=tenant_id,
            project_id=project_id,
            query_text=query_text,
            top_k=top_k,
            retrieval_mode=retrieval_mode,
            min_score=min_score,
            retrieval_hints=hints,
        )
        latency_ms = int((perf_counter() - started) * 1000)
        coverage = _compute_coverage(
            stats.query_token_count,
            stats.matched_query_token_count,
        )
        quality_gate_passed = _quality_gate_passes(
            result_count=len(stats.evidence),
            best_score=stats.best_score,
            coverage=coverage,
            min_score=min_score,
            min_coverage=min_coverage,
        )
        diagnostics = RetrievalDiagnostics(
            backend="local_json",
            retrieval_mode=retrieval_mode,
            top_k=top_k,
            result_count=len(stats.evidence),
            filter_hit_count=stats.filter_hit_count,
            coverage=coverage,
            best_score=round(stats.best_score, 6),
            quality_gate_passed=quality_gate_passed,
            latency_ms=latency_ms,
            index_name=settings.azure_ai_search_index_name,
            applied_filters={"tenant_id": tenant_id, "project_id": project_id},
        )
        if not quality_gate_passed:
            raise RetrievalQualityGateError(
                diagnostics=diagnostics,
                reason=(
                    "Retrieval quality gate failed: "
                    f"result_count={len(stats.evidence)}, "
                    f"best_score={stats.best_score:.6f} (min={min_score:.6f}), "
                    f"coverage={coverage:.6f} (min={min_coverage:.6f})."
                ),
            )
        return RetrievalOutcome(
            evidence=stats.evidence,
            diagnostics=diagnostics,
        )

    stats = _retrieve_azure(
        tenant_id=tenant_id,
        project_id=project_id,
        query_text=query_text,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        min_score=min_score,
        retrieval_hints=hints,
    )
    latency_ms = int((perf_counter() - started) * 1000)
    coverage = _compute_coverage(
        stats.query_token_count,
        stats.matched_query_token_count,
    )
    quality_gate_passed = _quality_gate_passes(
        result_count=len(stats.evidence),
        best_score=stats.best_score,
        coverage=coverage,
        min_score=min_score,
        min_coverage=min_coverage,
    )
    diagnostics = RetrievalDiagnostics(
        backend="azure_ai_search",
        retrieval_mode=retrieval_mode,
        top_k=top_k,
        result_count=len(stats.evidence),
        filter_hit_count=stats.filter_hit_count,
        coverage=coverage,
        best_score=round(stats.best_score, 6),
        quality_gate_passed=quality_gate_passed,
        latency_ms=latency_ms,
        index_name=settings.azure_ai_search_index_name,
        applied_filters={"tenant_id": tenant_id, "project_id": project_id},
    )
    if not quality_gate_passed:
        raise RetrievalQualityGateError(
            diagnostics=diagnostics,
            reason=(
                "Retrieval quality gate failed: "
                f"result_count={len(stats.evidence)}, "
                f"best_score={stats.best_score:.6f} (min={min_score:.6f}), "
                f"coverage={coverage:.6f} (min={min_coverage:.6f})."
            ),
        )
    return RetrievalOutcome(
        evidence=stats.evidence,
        diagnostics=diagnostics,
    )


def _retrieve_local(
    *,
    tenant_id: str,
    project_id: str,
    query_text: str,
    top_k: int,
    retrieval_mode: str,
    min_score: float,
    retrieval_hints: RetrievalHints | None,
) -> RetrievalStats:
    rows = list(_load_local_index().values())
    effective_query = _build_augmented_query(query_text, retrieval_hints)
    query_tokens = _tokenize(effective_query)
    filtered_rows: list[dict[str, Any]] = []
    row_lookup: dict[tuple[str, int], dict[str, Any]] = {}
    scored: list[tuple[EvidenceResult, dict[str, Any]]] = []

    for row in rows:
        if row.get("tenant_id") != tenant_id or row.get("project_id") != project_id:
            continue
        if not _row_matches_hints(row, retrieval_hints):
            continue
        filtered_rows.append(row)
        chunk_index = _to_chunk_index(row.get("chunk_index"))
        source_document_id = str(row.get("source_document_id", ""))
        if chunk_index is not None and source_document_id:
            row_lookup[(source_document_id, chunk_index)] = row

        content = str(row.get("content", "") or "")
        content_tokens = _tokenize(content)
        sparse = _sparse_score(query_tokens, content_tokens)
        dense = _dense_score(effective_query, content)
        final = _final_score(retrieval_mode, sparse, dense)
        if final <= 0:
            continue
        scored.append(
            (
                _build_evidence_result(row=row, sparse=sparse, dense=dense, final=final),
                row,
            )
        )

    scored.sort(key=lambda item: item[0].score_final, reverse=True)
    anchors = [item[0] for item in scored if item[0].score_final >= min_score][:top_k]
    if retrieval_hints and retrieval_hints.small_to_big and retrieval_hints.context_window > 0:
        selected = _expand_small_to_big_local(
            anchors=anchors,
            row_lookup=row_lookup,
            query_text=effective_query,
            query_tokens=query_tokens,
            retrieval_mode=retrieval_mode,
            context_window=retrieval_hints.context_window,
        )
    else:
        selected = anchors

    matched_tokens: set[str] = set()
    for item in selected:
        matched_tokens.update(_tokenize(item.text).intersection(query_tokens))
    best_score = max((item.score_final for item in selected), default=0.0)

    return RetrievalStats(
        evidence=selected,
        filter_hit_count=len(filtered_rows),
        query_token_count=len(query_tokens),
        matched_query_token_count=len(matched_tokens),
        best_score=best_score,
    )


def _retrieve_azure(
    *,
    tenant_id: str,
    project_id: str,
    query_text: str,
    top_k: int,
    retrieval_mode: str,
    min_score: float,
    retrieval_hints: RetrievalHints | None,
) -> RetrievalStats:
    _ = retrieval_mode
    client = _build_azure_search_client()
    effective_query = _build_augmented_query(query_text, retrieval_hints)
    query_tokens = _tokenize(effective_query)
    filters = f"tenant_id eq '{tenant_id}' and project_id eq '{project_id}'"
    results = client.search(search_text=effective_query, top=top_k, filter=filters)
    evidence: list[EvidenceResult] = []
    filter_hit_count = 0
    for row in results:
        row_dict = dict(row)
        if not _row_matches_hints(row_dict, retrieval_hints):
            continue
        filter_hit_count += 1
        score = float(row.get("@search.score", 0.0) or 0.0)
        if score < min_score:
            continue
        evidence.append(
            _build_evidence_result(
                row=row_dict,
                sparse=None,
                dense=None,
                final=score,
            )
        )

    evidence.sort(key=lambda item: item.score_final, reverse=True)
    selected = evidence[:top_k]
    matched_tokens = set()
    for item in selected:
        matched_tokens.update(_tokenize(item.text).intersection(query_tokens))
    best_score = max((item.score_final for item in selected), default=0.0)
    return RetrievalStats(
        evidence=selected,
        filter_hit_count=filter_hit_count,
        query_token_count=len(query_tokens),
        matched_query_token_count=len(matched_tokens),
        best_score=best_score,
    )
