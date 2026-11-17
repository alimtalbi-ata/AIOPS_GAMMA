"""Full-path synthetic snapshot benchmark and metadata fingerprint tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.reused.shadow_evidence_intake import (
    SnapshotRequest, SyntheticSnapshot, investigate_snapshot, snapshot_fingerprint,
)
from app.reused.shadow_investigation import Evidence, Hypothesis
from app.reused.shadow_snapshot_benchmark import (
    SnapshotBenchmarkCase, evaluate_snapshot_benchmark,
)

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


def request():
    evidence = (
        Evidence("metric", "tenant-a", "inc-1", "db", "supports", NOW, True, "metrics"),
        Evidence("trace", "tenant-a", "inc-1", "db", "supports", NOW, True, "traces"),
    )
    return SnapshotRequest(
        "actor-a", "tenant-a", "inc-1", ("tenant-a",),
        SyntheticSnapshot("snapshot-a", "tenant-a", "inc-1", NOW, evidence),
        (Hypothesis("db", "Database saturation"),), NOW,
    )


def test_metadata_fingerprint_is_stable_and_order_independent():
    req = request()
    a = snapshot_fingerprint(req.snapshot)
    reversed_snapshot = replace(req.snapshot, evidence=tuple(reversed(req.snapshot.evidence)))
    assert a == snapshot_fingerprint(reversed_snapshot)
    assert a == investigate_snapshot(req)["snapshot_fingerprint_sha256"]
    assert len(a) == 64


def test_metadata_change_changes_fingerprint():
    req = request()
    changed = replace(req.snapshot, evidence=(
        replace(req.snapshot.evidence[0], source_id="different"),
        req.snapshot.evidence[1],
    ))
    assert snapshot_fingerprint(req.snapshot) != snapshot_fingerprint(changed)


def test_full_path_benchmark_counts_denials_and_abstentions():
    good = request()
    denied = replace(good, allowed_tenants=())
    contradictory = replace(good, snapshot=replace(good.snapshot, evidence=(
        *good.snapshot.evidence,
        Evidence("counter", "tenant-a", "inc-1", "db", "contradicts", NOW, True, "logs"),
    )))
    cases = (
        SnapshotBenchmarkCase("supported", good, "db"),
        SnapshotBenchmarkCase("contradiction", contradictory, None),
        SnapshotBenchmarkCase("denied", denied, None, True),
    )
    result = evaluate_snapshot_benchmark(cases)
    assert result["total"] == 3
    assert result["correct_selections"] == 1
    assert result["correct_abstentions"] == 1
    assert result["correct_denials"] == 1
    assert result["false_positives"] == 0
    assert result["case_accuracy"] == 1.0
    assert result["authoritative"] is False
    assert result["live_execution_authorized"] is False


def test_missed_denial_is_detected():
    result = evaluate_snapshot_benchmark((
        SnapshotBenchmarkCase("should-deny", request(), None, True),
    ))
    assert result["missed_denials"] == 1
    assert result["case_accuracy"] == 0.0


def test_unexpected_denial_is_detected():
    req = replace(request(), allowed_tenants=())
    result = evaluate_snapshot_benchmark((
        SnapshotBenchmarkCase("should-allow", req, "db"),
    ))
    assert result["unexpected_denials"] == 1


@pytest.mark.parametrize("cases", [
    (),
    (SnapshotBenchmarkCase("same", request(), "db"),
     SnapshotBenchmarkCase("same", request(), "db")),
    (SnapshotBenchmarkCase("", request(), "db"),),
    (SnapshotBenchmarkCase("bad", request(), "db", True),),
    (SnapshotBenchmarkCase("unknown-ground-truth", request(), "nonexistent"),),
])
def test_invalid_benchmark_cases_fail_closed(cases):
    with pytest.raises(ValueError):
        evaluate_snapshot_benchmark(cases)


def test_wrong_cause_is_false_positive():
    req = request()
    alternate = replace(req, hypotheses=(
        *req.hypotheses, Hypothesis("net", "Network congestion"),
    ))
    result = evaluate_snapshot_benchmark((
        SnapshotBenchmarkCase("wrong-cause", alternate, "net"),
    ))
    assert result["false_positives"] == 1
    assert result["case_accuracy"] == 0.0


def test_missing_cause_is_counted():
    req = request()
    weak = replace(req, snapshot=replace(req.snapshot, evidence=(
        req.snapshot.evidence[0],
    )))
    result = evaluate_snapshot_benchmark((
        SnapshotBenchmarkCase("missing-cause", weak, "db"),
    ))
    assert result["missed_causes"] == 1
    assert result["case_accuracy"] == 0.0


@pytest.mark.parametrize("mutation", [
    {"live_execution_authorized": True},
    {"connectors_invoked": True},
    {"authoritative": True},
    {"itsm_mutations_performed": True},
    {"mode": "live"},
])
def test_unsafe_outer_report_fails_closed(monkeypatch, mutation):
    import app.reused.shadow_snapshot_benchmark as benchmark

    original = benchmark.investigate_snapshot

    def forged(req):
        return {**original(req), **mutation}

    monkeypatch.setattr(benchmark, "investigate_snapshot", forged)
    with pytest.raises(ValueError, match="Unsafe"):
        evaluate_snapshot_benchmark((SnapshotBenchmarkCase("unsafe", request(), "db"),))


@pytest.mark.parametrize("mutation", [
    {"live_execution_authorized": True},
    {"tools_invoked": True},
    {"authoritative": True},
    {"itsm_mutations_performed": True},
    {"mode": "live"},
    {"state": "ABSTAIN", "selected_hypothesis_id": "db"},
    {"state": "REVIEW_CANDIDATE", "selected_hypothesis_id": None},
])
def test_unsafe_or_inconsistent_rca_fails_closed(monkeypatch, mutation):
    import app.reused.shadow_snapshot_benchmark as benchmark

    original = benchmark.investigate_snapshot

    def forged(req):
        result = original(req)
        return {**result, "investigation": {**result["investigation"], **mutation}}

    monkeypatch.setattr(benchmark, "investigate_snapshot", forged)
    with pytest.raises(ValueError):
        evaluate_snapshot_benchmark((SnapshotBenchmarkCase("unsafe-rca", request(), "db"),))


def test_fingerprint_uses_instant_not_timezone_representation():
    req = request()
    offset = timezone(timedelta(hours=5, minutes=30))
    equivalent = replace(req.snapshot,
        captured_at=req.snapshot.captured_at.astimezone(offset),
        evidence=tuple(replace(item, observed_at=item.observed_at.astimezone(offset))
                       for item in req.snapshot.evidence))
    assert snapshot_fingerprint(req.snapshot) == snapshot_fingerprint(equivalent)


def test_pinned_fingerprint_survives_timezone_conversion():
    req = request()
    offset = timezone(timedelta(hours=-4))
    equivalent = replace(req.snapshot,
        captured_at=req.snapshot.captured_at.astimezone(offset),
        evidence=tuple(replace(item, observed_at=item.observed_at.astimezone(offset))
                       for item in req.snapshot.evidence))
    pinned = replace(req, snapshot=equivalent,
                     expected_fingerprint_sha256=snapshot_fingerprint(req.snapshot))
    assert investigate_snapshot(pinned)["snapshot_fingerprint_sha256"] == pinned.expected_fingerprint_sha256


@pytest.mark.parametrize("hypotheses", [
    None, [], ("not-a-hypothesis",), (None,),
])
def test_benchmark_rejects_malformed_hypotheses_before_lookup(hypotheses):
    req = replace(request(), hypotheses=hypotheses)
    with pytest.raises(ValueError, match="Invalid benchmark hypotheses"):
        evaluate_snapshot_benchmark((
            SnapshotBenchmarkCase("malformed", req, "db"),
        ))


@pytest.mark.parametrize("selected", ["invented-cause", 42, "", True])
def test_forged_selected_cause_not_in_hypotheses_is_rejected(monkeypatch, selected):
    import app.reused.shadow_snapshot_benchmark as benchmark

    original = benchmark.investigate_snapshot

    def forged(req):
        result = original(req)
        return {**result, "investigation": {
            **result["investigation"], "selected_hypothesis_id": selected,
        }}

    monkeypatch.setattr(benchmark, "investigate_snapshot", forged)
    with pytest.raises(ValueError, match="Unknown selected RCA hypothesis"):
        evaluate_snapshot_benchmark((
            SnapshotBenchmarkCase("forged-selection", request(), "db"),
        ))


@pytest.mark.parametrize("identifier", [
    None, [], 17, " db ", "",
])
def test_benchmark_rejects_malformed_hypothesis_identifier(identifier):
    req = replace(request(), hypotheses=(Hypothesis(identifier, "Malformed"),))
    with pytest.raises(ValueError, match="Invalid benchmark hypotheses"):
        evaluate_snapshot_benchmark((
            SnapshotBenchmarkCase("malformed-id", req, None),
        ))
