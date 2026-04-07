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
    evidence_refs: list[str]


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

        if not claim.citations:
            reasons.append("missing_citations")
        else:
            for citation in claim.citations:
                source_document_id = str(citation.get("source_document_id", "")).strip()
                chunk_id = str(citation.get("chunk_id", "")).strip()
                if not source_document_id or not chunk_id:
                    reasons.append("invalid_citation_reference")
                    continue
                key = (source_document_id, chunk_id)
                evidence_text = evidence_map.get(key)
                if not evidence_text:
                    reasons.append("citation_not_found_in_evidence_pool")
                    continue
                evidence_refs.append(f"{source_document_id}:{chunk_id}")
                evidence_texts.append(evidence_text)

        if claim.is_numeric:
            if not claim.calculation_refs:
                reasons.append("missing_calculation_artifact_for_numeric_claim")
            else:
                for ref in claim.calculation_refs:
                    if ref not in calculation_ids:
                        reasons.append("invalid_calculation_reference")
                        break

        max_overlap = 0.0
        for evidence_text in evidence_texts:
            max_overlap = max(max_overlap, _overlap_score(claim.statement, evidence_text))

        azure_score = _azure_openai_entailment_score(claim.statement, evidence_texts) if evidence_texts else 0.0
        if azure_score > 0:
            max_overlap = max(max_overlap, azure_score)

        if reasons:
            status: VerifierStatus = "FAIL"
            severity: Literal["normal", "critical"] = "critical"
            reason = "; ".join(sorted(set(reasons)))
        elif max_overlap >= effective_pass_threshold:
            status = "PASS"
            severity = "normal"
            reason = "entailment_threshold_passed"
        elif max_overlap >= effective_unsure_threshold:
            status = "UNSURE"
            severity = "normal"
            reason = "entailment_ambiguous_requires_human_review"
        else:
            status = "FAIL"
            severity = "critical"
            reason = "entailment_below_threshold"

        decisions.append(
            VerifierDecision(
                claim_id=claim.claim_id,
                status=status,
                severity=severity,
                confidence=round(max_overlap, 6),
                reason=reason,
                evidence_refs=evidence_refs,
            )
        )

    return decisions
