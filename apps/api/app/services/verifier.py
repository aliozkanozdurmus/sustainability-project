# Bu servis, verifier akisindaki uygulama mantigini tek yerde toplar.

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
import re
from typing import Any, Literal
from urllib import error, request

from app.core.settings import settings


VerifierStatus = Literal["PASS", "FAIL", "UNSURE"]
VERIFIER_POLICY_VERSION = "verifier-policy-v1"


@dataclass
class ClaimInput:
    claim_id: str
    statement: str
    is_numeric: bool
    citations: list[dict[str, Any]]
    calculation_refs: list[str]


@dataclass
class VerifierDecision:
    claim_id: str
    status: VerifierStatus
    severity: Literal["normal", "critical"]
    confidence: float
    reason: str
    reason_code: str
    policy_version: str
    blocking: bool
    evidence_refs: list[str]
    citation_span_refs: list[dict[str, Any]]


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"\w+", text.lower()) if token}


def _overlap_score(statement: str, evidence_text: str) -> float:
    statement_tokens = _tokenize(statement)
    evidence_tokens = _tokenize(evidence_text)
    if not statement_tokens or not evidence_tokens:
        return 0.0
    lexical = len(statement_tokens.intersection(evidence_tokens)) / len(statement_tokens)
    semanticish = SequenceMatcher(None, statement.lower(), evidence_text.lower()).ratio()
    return round((0.7 * lexical) + (0.3 * semanticish), 6)


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"-?\d+(?:\.\d+)?", text)


def _citations_have_valid_spans(citations: list[dict[str, Any]]) -> bool:
    if not citations:
        return False
    for citation in citations:
        span_start = citation.get("span_start")
        span_end = citation.get("span_end")
        if not isinstance(span_start, (int, float)) or not isinstance(span_end, (int, float)):
            return False
        if int(span_end) <= int(span_start):
            return False
    return True


def _claim_numbers_supported(statement: str, evidence_texts: list[str]) -> bool:
    claim_numbers = _extract_numbers(statement)
    if not claim_numbers:
        return True
    evidence_number_pool = {number for text in evidence_texts for number in _extract_numbers(text)}
    return all(number in evidence_number_pool for number in claim_numbers)


def _unique_reasons(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _legacy_reason_text(reason_code: str) -> str:
    mapping = {
        "MISSING_CITATIONS": "missing_citations",
        "INVALID_CITATION_REFERENCE": "invalid_citation_reference",
        "CITATION_NOT_FOUND_IN_EVIDENCE_POOL": "citation_not_found_in_evidence_pool",
        "MISSING_CITATION_SPAN": "missing_citation_span",
        "MISSING_CALCULATION_ARTIFACT": "missing_calculation_artifact_for_numeric_claim",
        "INVALID_CALCULATION_REFERENCE": "invalid_calculation_reference",
        "NUMERIC_CONFLICT": "numeric_claim_not_supported_by_evidence",
        "CLAIM_SUPPORTED": "entailment_threshold_passed",
        "SUPPORT_AMBIGUOUS": "entailment_ambiguous_requires_human_review",
        "ENTAILMENT_BELOW_THRESHOLD": "entailment_below_threshold",
    }
    return mapping.get(reason_code, reason_code.lower())


def _should_use_azure_openai() -> bool:
    return (
        settings.verifier_mode == "azure_openai"
        and bool(settings.azure_openai_endpoint)
        and bool(settings.azure_openai_api_key)
        and bool(settings.azure_openai_chat_deployment)
    )


def _azure_openai_entailment_score(statement: str, evidence_texts: list[str]) -> float:
    if not _should_use_azure_openai():
        return 0.0

    endpoint = settings.azure_openai_endpoint.rstrip("/")
    deployment = str(settings.azure_openai_chat_deployment)
    api_version = settings.azure_openai_api_version
    url = (
        f"{endpoint}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={api_version}"
    )
    prompt = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an entailment verifier. Return ONLY compact JSON with key entailment_score "
                    "as number between 0 and 1."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "claim": statement,
                        "evidence": evidence_texts,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": 100,
    }
    payload = json.dumps(prompt, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        url=url,
        method="POST",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "api-key": str(settings.azure_openai_api_key),
        },
    )
    try:
        with request.urlopen(req, timeout=12) as response:
            raw = response.read().decode("utf-8")
    except (error.HTTPError, error.URLError, TimeoutError):
        return 0.0

    try:
        parsed = json.loads(raw)
        choices = parsed.get("choices", [])
        if not choices:
            return 0.0
        content = choices[0].get("message", {}).get("content", "")
        candidate = json.loads(content)
        score = float(candidate.get("entailment_score", 0.0))
        return max(0.0, min(1.0, score))
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0.0


def verify_claims(
    *,
    claims: list[ClaimInput],
    evidence_map: dict[tuple[str, str], str],
    calculation_ids: set[str],
    pass_threshold: float | None = None,
    unsure_threshold: float | None = None,
) -> list[VerifierDecision]:
    effective_pass_threshold = pass_threshold if pass_threshold is not None else settings.verifier_pass_threshold
    effective_unsure_threshold = (
        unsure_threshold if unsure_threshold is not None else settings.verifier_unsure_threshold
    )
    effective_pass_threshold = max(0.0, min(1.0, effective_pass_threshold))
    effective_unsure_threshold = max(0.0, min(1.0, effective_unsure_threshold))
    if effective_unsure_threshold > effective_pass_threshold:
        effective_unsure_threshold = effective_pass_threshold

    decisions: list[VerifierDecision] = []
    for claim in claims:
        reasons: list[str] = []
        evidence_refs: list[str] = []
        evidence_texts: list[str] = []
        citation_span_refs: list[dict[str, Any]] = []

        if not claim.citations:
            reasons.append("MISSING_CITATIONS")
        else:
            for citation in claim.citations:
                source_document_id = str(citation.get("source_document_id", "")).strip()
                chunk_id = str(citation.get("chunk_id", "")).strip()
                if not source_document_id or not chunk_id:
                    reasons.append("INVALID_CITATION_REFERENCE")
                    continue
                key = (source_document_id, chunk_id)
                evidence_text = evidence_map.get(key)
                if not evidence_text:
                    reasons.append("CITATION_NOT_FOUND_IN_EVIDENCE_POOL")
                    continue
                evidence_refs.append(f"{source_document_id}:{chunk_id}")
                evidence_texts.append(evidence_text)
                citation_span_refs.append(
                    {
                        "source_document_id": source_document_id,
                        "chunk_id": chunk_id,
                        "span_start": int(citation.get("span_start", 0) or 0),
                        "span_end": int(citation.get("span_end", 0) or 0),
                    }
                )

        if claim.citations and not _citations_have_valid_spans(claim.citations):
            reasons.append("MISSING_CITATION_SPAN")

        if claim.is_numeric:
            if not claim.calculation_refs:
                reasons.append("MISSING_CALCULATION_ARTIFACT")
            else:
                for ref in claim.calculation_refs:
                    if ref not in calculation_ids:
                        reasons.append("INVALID_CALCULATION_REFERENCE")
                        break

        max_overlap = 0.0
        for evidence_text in evidence_texts:
            max_overlap = max(max_overlap, _overlap_score(claim.statement, evidence_text))

        azure_score = _azure_openai_entailment_score(claim.statement, evidence_texts) if evidence_texts else 0.0
        if azure_score > 0:
            max_overlap = max(max_overlap, azure_score)

        if claim.is_numeric and evidence_texts and not _claim_numbers_supported(claim.statement, evidence_texts):
            reasons.append("NUMERIC_CONFLICT")

        normalized_reasons = _unique_reasons(reasons)
        if reasons:
            status: VerifierStatus = "FAIL"
            severity: Literal["normal", "critical"] = "critical"
            reason_code = normalized_reasons[0]
            reason = "; ".join(_legacy_reason_text(item) for item in normalized_reasons)
        elif max_overlap >= effective_pass_threshold:
            status = "PASS"
            severity = "normal"
            reason_code = "CLAIM_SUPPORTED"
            reason = _legacy_reason_text(reason_code)
        elif max_overlap >= effective_unsure_threshold:
            status = "UNSURE"
            severity = "normal"
            reason_code = "SUPPORT_AMBIGUOUS"
            reason = _legacy_reason_text(reason_code)
        else:
            status = "FAIL"
            severity = "critical"
            reason_code = "ENTAILMENT_BELOW_THRESHOLD"
            reason = _legacy_reason_text(reason_code)

        decisions.append(
            VerifierDecision(
                claim_id=claim.claim_id,
                status=status,
                severity=severity,
                confidence=round(max_overlap, 6),
                reason=reason,
                reason_code=reason_code,
                policy_version=VERIFIER_POLICY_VERSION,
                blocking=status != "PASS",
                evidence_refs=evidence_refs,
                citation_span_refs=citation_span_refs,
            )
        )

    return decisions
