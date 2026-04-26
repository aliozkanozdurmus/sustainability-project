from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Callable


def _extract_first_number(text: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


@dataclass(frozen=True)
class FormulaDefinition:
    name: str
    output_unit: str
    normalization_policy_ref: str
    evaluator: Callable[[str], float | None]

    @property
    def code_hash(self) -> str:
        digest = hashlib.sha256(self.name.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"


@dataclass(frozen=True)
class FormulaExecution:
    calc_id: str
    evidence_id: str
    status: str
    formula_name: str
    code_hash: str
    inputs_ref: str
    output_value: float | None
    output_unit: str
    trace_log_ref: str
    normalization_policy_ref: str


FORMULA_REGISTRY: dict[str, FormulaDefinition] = {
    "regex_numeric_extract_v1": FormulaDefinition(
        name="regex_numeric_extract_v1",
        output_unit="unitless",
        normalization_policy_ref="normalization/unitless/v1",
        evaluator=_extract_first_number,
    )
}


def execute_formula(
    *,
    formula_name: str,
    run_id: str,
    evidence_id: str,
    evidence_text: str,
) -> FormulaExecution:
    formula = FORMULA_REGISTRY.get(formula_name)
    if formula is None:
        raise ValueError(f"Unknown calculation formula: {formula_name}")

    return FormulaExecution(
        calc_id=f"calc_{evidence_id}",
        evidence_id=evidence_id,
        status="completed",
        formula_name=formula.name,
        code_hash=formula.code_hash,
        inputs_ref=f"state://{run_id}/evidence/{evidence_id}",
        output_value=formula.evaluator(evidence_text),
        output_unit=formula.output_unit,
        trace_log_ref=f"state://{run_id}/calc/{evidence_id}/trace",
        normalization_policy_ref=formula.normalization_policy_ref,
    )
