"""Zero-dependency smoke qualification for synthetic shadow RCA.

Run: python scripts/check_shadow_rca_stdlib.py
No network, connectors, persistence, runbook execution or ITSM mutation.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.reused.shadow_evidence_intake import (
    SnapshotRequest, SyntheticSnapshot, investigate_snapshot, snapshot_fingerprint,
)
from app.reused.shadow_investigation import Evidence, Hypothesis
from app.reused.shadow_snapshot_benchmark import SnapshotBenchmarkCase, evaluate_snapshot_benchmark


def main() -> None:
    now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    evidence = (
        Evidence("metric", "tenant-a", "inc-1", "db", "supports", now, True, "metrics"),
        Evidence("trace", "tenant-a", "inc-1", "db", "supports", now, True, "traces"),
    )
    request = SnapshotRequest(
        "actor-a", "tenant-a", "inc-1", ("tenant-a",),
        SyntheticSnapshot("snap-1", "tenant-a", "inc-1", now, evidence),
        (Hypothesis("db", "Database saturation"),), now,
    )
    accepted = investigate_snapshot(request)
    assert accepted["investigation"]["state"] == "REVIEW_CANDIDATE"
    assert accepted["investigation"]["selected_hypothesis_id"] == "db"
    assert accepted["live_execution_authorized"] is False
    assert accepted["connectors_invoked"] is False

    duplicate = replace(request, snapshot=replace(
        request.snapshot, evidence=(evidence[0], replace(evidence[1], source_id="metrics")),
    ))
    assert investigate_snapshot(duplicate)["investigation"]["state"] == "ABSTAIN"

    contradiction = replace(request, snapshot=replace(
        request.snapshot, evidence=evidence + (
            Evidence("counter", "tenant-a", "inc-1", "db", "contradicts", now, True, "logs"),
        ),
    ))
    assert investigate_snapshot(contradiction)["investigation"]["state"] == "ABSTAIN"

    denied = replace(request, allowed_tenants=())
    try:
        investigate_snapshot(denied)
    except PermissionError:
        pass
    else:
        raise AssertionError("Denied tenant was accepted")

    stale = replace(request, snapshot=replace(
        request.snapshot, captured_at=now - timedelta(hours=1),
    ))
    try:
        investigate_snapshot(stale)
    except ValueError:
        pass
    else:
        raise AssertionError("Stale snapshot was accepted")

    reversed_snapshot = replace(request.snapshot, evidence=tuple(reversed(evidence)))
    assert snapshot_fingerprint(request.snapshot) == snapshot_fingerprint(reversed_snapshot)

    benchmark = evaluate_snapshot_benchmark((
        SnapshotBenchmarkCase("supported", request, "db"),
        SnapshotBenchmarkCase("contradiction", contradiction, None),
        SnapshotBenchmarkCase("denied", denied, None, True),
    ))
    assert benchmark["case_accuracy"] == 1.0
    assert benchmark["correct_denials"] == 1
    assert benchmark["false_positives"] == 0
    assert benchmark["live_execution_authorized"] is False
    print("SHADOW_RCA_STDLIB_SMOKE_OK: 7 offline assertions groups passed")


if __name__ == "__main__":
    main()
