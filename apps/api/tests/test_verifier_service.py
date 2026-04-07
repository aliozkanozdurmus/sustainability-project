# Bu test dosyasi, verifier service davranisini dogrular.

from __future__ import annotations

from app.services.verifier import ClaimInput, verify_claims


def test_verify_claims_returns_pass_for_supported_claim() -> None:
    claims = [
        ClaimInput(
            claim_id="clm-1",
            statement="Scope 2 emissions decreased to 120 in 2025.",
            is_numeric=True,
            citations=[
                {
                    "source_document_id": "doc-1",
                    "chunk_id": "chk-1",
                    "span_start": 0,
                    "span_end": 42,
                }
            ],
            calculation_refs=["calc-1"],
        )
    ]
    evidence_map = {
        ("doc-1", "chk-1"): "Scope 2 emissions decreased to 120 in 2025 due to renewable energy contracts."
    }
    decisions = verify_claims(
        claims=claims,
        evidence_map=evidence_map,
        calculation_ids={"calc-1"},
        pass_threshold=0.4,
        unsure_threshold=0.2,
    )
    assert len(decisions) == 1
    assert decisions[0].status == "PASS"


def test_verify_claims_returns_unsure_for_ambiguous_claim() -> None:
    claims = [
        ClaimInput(
            claim_id="clm-2",
            statement="The company improved supplier engagement this year.",
            is_numeric=False,
            citations=[
                {
                    "source_document_id": "doc-2",
                    "chunk_id": "chk-2",
                    "span_start": 0,
                    "span_end": 40,
                }
            ],
            calculation_refs=[],
        )
    ]
    evidence_map = {
        ("doc-2", "chk-2"): "Supplier program updates were mentioned with limited detail."
    }
    decisions = verify_claims(
        claims=claims,
        evidence_map=evidence_map,
        calculation_ids=set(),
        pass_threshold=0.7,
        unsure_threshold=0.15,
    )
    assert decisions[0].status == "UNSURE"
    assert decisions[0].severity == "normal"


def test_verify_claims_returns_critical_fail_for_numeric_without_calculator() -> None:
    claims = [
        ClaimInput(
            claim_id="clm-3",
            statement="Scope 1 emissions are 55 tCO2e.",
            is_numeric=True,
            citations=[
                {
                    "source_document_id": "doc-3",
                    "chunk_id": "chk-3",
                    "span_start": 0,
                    "span_end": 30,
                }
            ],
            calculation_refs=[],
        )
    ]
    evidence_map = {
        ("doc-3", "chk-3"): "Scope 1 emissions are 55 tCO2e according to the inventory."
    }
    decisions = verify_claims(
        claims=claims,
        evidence_map=evidence_map,
        calculation_ids=set(),
        pass_threshold=0.4,
        unsure_threshold=0.2,
    )
    assert decisions[0].status == "FAIL"
    assert decisions[0].severity == "critical"
    assert "missing_calculation_artifact_for_numeric_claim" in decisions[0].reason
