"""Offline fixture generator contract; never contacts OpenSearch."""
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest


def load_generator():
    path = Path(__file__).resolve().parents[1] / "deploy/scripts/generate-opensearch-staging-fixtures.py"
    spec = importlib.util.spec_from_file_location("gamma_staging_fixtures", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixtures_have_exact_tenant_service_matrix_and_outside_window():
    module = load_generator()
    at = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
    a = "11111111-1111-4111-8111-111111111111"
    b = "22222222-2222-4222-8222-222222222222"
    lines = list(module.generate(a, b, "checkout", "payments", "gamma-run-001",
                                 "staging-gamma-fixtures", at))
    assert len(lines) == 10
    assert all(lines[i]["index"]["_index"] == "staging-gamma-fixtures"
               for i in range(0, len(lines), 2))
    docs = lines[1::2]
    assert [(d["tenant"]["id"], d["resource"]["attributes"]["service"]["name"])
            for d in docs[:4]] == [
                (a, "checkout"), (a, "payments"),
                (b, "checkout"), (b, "payments"),
            ]
    assert all(d["gamma_fixture_marker"] == "gamma-run-001" for d in docs)
    assert docs[4]["@timestamp"] != docs[0]["@timestamp"]


@pytest.mark.parametrize("index", ["logs", "staging-*", "staging-bad/index"])
def test_fixture_generator_rejects_unsafe_index(index):
    module = load_generator()
    with pytest.raises(ValueError, match="staging-"):
        list(module.generate(
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
            "checkout", "payments", "gamma-run-001", index,
            datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
        ))


@pytest.mark.parametrize("tenant", [
    "00000000-0000-0000-0000-000000000000",
    "11111111111141118111111111111111",
])
def test_generator_rejects_nil_or_noncanonical_tenant(tenant):
    module = load_generator()
    with pytest.raises(ValueError):
        list(module.generate(
            tenant, "22222222-2222-4222-8222-222222222222",
            "checkout", "payments", "gamma-run-001",
            "staging-gamma-fixtures",
            datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
        ))


@pytest.mark.parametrize("marker", ["../escape", "unsafe marker", "x" * 129])
def test_generator_rejects_unsafe_marker(marker):
    module = load_generator()
    with pytest.raises(ValueError, match="marker"):
        list(module.generate(
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
            "checkout", "payments", marker,
            "staging-gamma-fixtures",
            datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
        ))


@pytest.mark.parametrize("service", ["../other", "bad service", "x" * 256])
def test_generator_rejects_invalid_service(service):
    module = load_generator()
    with pytest.raises(ValueError, match="service"):
        list(module.generate(
            "11111111-1111-4111-8111-111111111111",
            "22222222-2222-4222-8222-222222222222",
            service, "payments", "gamma-run-001",
            "staging-gamma-fixtures",
            datetime(2026, 11, 10, 12, tzinfo=timezone.utc),
        ))
