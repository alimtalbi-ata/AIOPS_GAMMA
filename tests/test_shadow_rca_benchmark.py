"""Adjudicated synthetic benchmark fixtures and fail-closed scoring tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.reused.shadow_investigation import Evidence, Hypothesis, InvestigationInput
from app.reused.shadow_rca_benchmark import BenchmarkCase, evaluate_benchmark

NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
H = (Hypothesis("db", "Database saturation"), Hypothesis("net", "Network congestion"))


def ev(ref, cause="db", stance="supports", source=None, **kw):
    return replace(Evidence(ref, "tenant-1", "incident-1", cause, stance,
                            NOW, True, source or ref), **kw)


def req(*items):
    return InvestigationInput("tenant-1", "incident-1", H, tuple(items), NOW)


def fixtures():
    return (
        BenchmarkCase("supported", req(ev("metric"), ev("trace")), "db"),
        BenchmarkCase("contradicted", req(ev("metric"), ev("trace"),
                                        ev("counter", stance="contradicts")), None),
        BenchmarkCase("ambiguous", req(ev("a"), ev("b"), ev("c", "net"),
                                     ev("d", "net")), None),
        BenchmarkCase("same-source", req(ev("metric", source="otel"),
                                        ev("trace", source="otel")), None),
        BenchmarkCase("stale", req(ev("metric"), ev("trace",
                            observed_at=NOW - timedelta(hours=1))), None),
        BenchmarkCase("unverified", req(ev("metric"), ev("trace",
                                 source_verified=False)), None),
        BenchmarkCase("cross-tenant", req(ev("metric"), ev("trace",
                                   tenant_id="tenant-2")), None),
        BenchmarkCase("no-evidence", req(), None),
    )


def test_adjudicated_fixture_metrics():
    result = evaluate_benchmark(fixtures())
    assert result["total"] == 8
    assert result["correct_selections"] == 1
    assert result["false_positives"] == 0
    assert result["missed_causes"] == 0
    assert result["abstentions"] == 7
    assert result["correct_abstentions"] == 7
    assert result["selection_precision"] == 1.0
    assert result["abstention_rate"] == 7 / 8
    assert result["case_accuracy"] == 1.0
    assert result["authoritative"] is False
    assert result["live_execution_authorized"] is False


def test_wrong_selection_is_false_positive():
    case = BenchmarkCase("wrong", req(ev("metric"), ev("trace")), "net")
    result = evaluate_benchmark((case,))
    assert result["false_positives"] == 1
    assert result["case_accuracy"] == 0.0


def test_missed_supported_cause_is_counted():
    case = BenchmarkCase("missed", req(ev("metric")), "db")
    result = evaluate_benchmark((case,))
    assert result["missed_causes"] == 1
    assert result["selection_precision"] is None


def test_unexpected_selection_on_negative_is_false_positive():
    case = BenchmarkCase("unexpected", req(ev("metric"), ev("trace")), None)
    result = evaluate_benchmark((case,))
    assert result["false_positives"] == 1


@pytest.mark.parametrize("cases", [
    (), (BenchmarkCase("dup", req(), None), BenchmarkCase("dup", req(), None)),
    (BenchmarkCase("", req(), None),),
    (BenchmarkCase("bad", req(), "nonexistent"),),
    (BenchmarkCase("bad", req(), 42),),
])
def test_invalid_benchmark_rejected(cases):
    with pytest.raises(ValueError):
        evaluate_benchmark(cases)
