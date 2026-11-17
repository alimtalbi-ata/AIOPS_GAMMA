"""Offline adjudicated synthetic RCA benchmark; no tool or network access."""
from __future__ import annotations

from dataclasses import dataclass
from app.reused.shadow_investigation import InvestigationInput, investigate_shadow


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    request: InvestigationInput
    expected_hypothesis_id: str | None  # None = expected abstention


def evaluate_benchmark(cases: tuple[BenchmarkCase, ...]) -> dict:
    """Evaluate deterministic fixtures; fail on malformed or cross-case identity."""
    if type(cases) is not tuple or not cases:
        raise ValueError("Nonempty benchmark tuple required")
    seen = set()
    outcomes = []
    tp = fp = abstain = missed = correct_abstain = 0
    for case in cases:
        if (type(case) is not BenchmarkCase or type(case.case_id) is not str
                or not case.case_id.strip() or case.case_id in seen
                or type(case.request) is not InvestigationInput
                or (case.expected_hypothesis_id is not None
                    and (type(case.expected_hypothesis_id) is not str
                         or not case.expected_hypothesis_id.strip()))):
            raise ValueError("Invalid benchmark case")
        seen.add(case.case_id)
        valid_ids = {h.hypothesis_id for h in case.request.hypotheses}
        if case.expected_hypothesis_id is not None and case.expected_hypothesis_id not in valid_ids:
            raise ValueError("Expected hypothesis missing from fixture")
        result = investigate_shadow(case.request)
        selected = result["selected_hypothesis_id"]
        expected = case.expected_hypothesis_id
        if selected is None:
            abstain += 1
            if expected is None:
                correct_abstain += 1
                category = "CORRECT_ABSTENTION"
            else:
                missed += 1
                category = "MISSED_CAUSE"
        elif selected == expected:
            tp += 1
            category = "CORRECT_SELECTION"
        else:
            fp += 1
            category = "FALSE_POSITIVE"
        outcomes.append({
            "case_id": case.case_id,
            "category": category,
            "expected_hypothesis_id": expected,
            "selected_hypothesis_id": selected,
            "state": result["state"],
            "reasons": result["reasons"],
        })
    total = len(cases)
    selections = tp + fp
    return {
        "mode": "synthetic_shadow",
        "total": total,
        "correct_selections": tp,
        "false_positives": fp,
        "missed_causes": missed,
        "abstentions": abstain,
        "correct_abstentions": correct_abstain,
        "selection_precision": tp / selections if selections else None,
        "abstention_rate": abstain / total,
        "case_accuracy": (tp + correct_abstain) / total,
        "outcomes": tuple(outcomes),
        "authoritative": False,
        "live_execution_authorized": False,
    }
