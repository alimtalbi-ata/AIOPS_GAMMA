"""Benchmark the full synthetic snapshot-intake-to-RCA path."""
from __future__ import annotations

from dataclasses import dataclass

from app.reused.shadow_evidence_intake import SnapshotRequest, investigate_snapshot, snapshot_fingerprint
from app.reused.shadow_investigation import Hypothesis


@dataclass(frozen=True)
class SnapshotBenchmarkCase:
    case_id: str
    request: SnapshotRequest
    expected_hypothesis_id: str | None
    expect_access_denied: bool = False


def evaluate_snapshot_benchmark(cases: tuple[SnapshotBenchmarkCase, ...]) -> dict:
    """Score selections, abstentions and declared-grant denials separately."""
    if type(cases) is not tuple or not cases:
        raise ValueError("Nonempty benchmark tuple required")
    seen = set()
    outcomes = []
    correct = false_positive = missed = correct_abstain = 0
    correct_denial = unexpected_denial = missed_denial = 0
    for case in cases:
        if (type(case) is not SnapshotBenchmarkCase
                or type(case.case_id) is not str or not case.case_id.strip()
                or case.case_id in seen or type(case.request) is not SnapshotRequest
                or type(case.expect_access_denied) is not bool
                or (case.expected_hypothesis_id is not None
                    and (type(case.expected_hypothesis_id) is not str
                         or not case.expected_hypothesis_id.strip()))):
            raise ValueError("Invalid snapshot benchmark case")
        seen.add(case.case_id)
        if (type(case.request.hypotheses) is not tuple
                or any(type(h) is not Hypothesis
                       or type(h.hypothesis_id) is not str
                       or not h.hypothesis_id.strip()
                       or h.hypothesis_id != h.hypothesis_id.strip()
                       for h in case.request.hypotheses)):
            raise ValueError("Invalid benchmark hypotheses")
        if (case.expected_hypothesis_id is not None
                and case.expected_hypothesis_id not in {
                    h.hypothesis_id for h in case.request.hypotheses
                }):
            raise ValueError("Unknown expected hypothesis")
        if case.expect_access_denied and case.expected_hypothesis_id is not None:
            raise ValueError("Denied case cannot expect a selected cause")
        try:
            report = investigate_snapshot(case.request)
        except PermissionError:
            category = "CORRECT_DENIAL" if case.expect_access_denied else "UNEXPECTED_DENIAL"
            if case.expect_access_denied:
                correct_denial += 1
            else:
                unexpected_denial += 1
            selected = None
            fingerprint = None
        else:
            if (type(report) is not dict
                    or report.get("snapshot_id") != case.request.snapshot.snapshot_id
                    or report.get("tenant_id") != case.request.tenant_id
                    or report.get("incident_id") != case.request.incident_id
                    or report.get("actor_id") != case.request.actor_id
                    or report.get("snapshot_fingerprint_sha256") != snapshot_fingerprint(case.request.snapshot)
                    or report.get("fingerprint_scope") != "CALLER_DECLARED_METADATA_ONLY"
                    or report.get("grant_origin") != "CALLER_DECLARED_SYNTHETIC"
                    or type(report.get("investigation")) is not dict):
                raise ValueError("Inconsistent snapshot investigation provenance")
            investigation = report["investigation"]
            if (investigation.get("tenant_id") != case.request.tenant_id
                    or investigation.get("incident_id") != case.request.incident_id):
                raise ValueError("Inconsistent RCA investigation identity")
            if (report.get("mode") != "synthetic_shadow"
                    or investigation.get("mode") != "synthetic_shadow"
                    or any(report.get(flag) is not False for flag in (
                        "authoritative", "live_execution_authorized",
                        "connectors_invoked", "itsm_mutations_performed"))
                    or any(investigation.get(flag) is not False for flag in (
                        "authoritative", "live_execution_authorized",
                        "tools_invoked", "itsm_mutations_performed"))):
                raise ValueError("Unsafe snapshot investigation report")
            if "selected_hypothesis_id" not in investigation:
                raise ValueError("Missing RCA selection field")
            selected = investigation["selected_hypothesis_id"]
            if (selected is not None
                    and (type(selected) is not str
                         or selected not in {h.hypothesis_id for h in case.request.hypotheses})):
                raise ValueError("Unknown selected RCA hypothesis")
            if ((investigation.get("state") == "ABSTAIN" and selected is not None)
                    or (investigation.get("state") == "REVIEW_CANDIDATE"
                        and (type(selected) is not str or not selected.strip()))
                    or investigation.get("state") not in ("ABSTAIN", "REVIEW_CANDIDATE")):
                raise ValueError("Inconsistent investigation state")
            fingerprint = report["snapshot_fingerprint_sha256"]
            if case.expect_access_denied:
                missed_denial += 1
                category = "MISSED_DENIAL"
            elif selected is None:
                if case.expected_hypothesis_id is None:
                    correct_abstain += 1
                    category = "CORRECT_ABSTENTION"
                else:
                    missed += 1
                    category = "MISSED_CAUSE"
            elif selected == case.expected_hypothesis_id:
                correct += 1
                category = "CORRECT_SELECTION"
            else:
                false_positive += 1
                category = "FALSE_POSITIVE"
        outcomes.append({
            "case_id": case.case_id,
            "category": category,
            "selected_hypothesis_id": selected,
            "snapshot_fingerprint_sha256": fingerprint,
        })
    total = len(cases)
    return {
        "mode": "synthetic_shadow",
        "total": total,
        "correct_selections": correct,
        "false_positives": false_positive,
        "missed_causes": missed,
        "correct_abstentions": correct_abstain,
        "correct_denials": correct_denial,
        "unexpected_denials": unexpected_denial,
        "missed_denials": missed_denial,
        "case_accuracy": (correct + correct_abstain + correct_denial) / total,
        "outcomes": tuple(outcomes),
        "authoritative": False,
        "live_execution_authorized": False,
    }
