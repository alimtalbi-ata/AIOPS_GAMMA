from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.reused.correlation import CorrelationSignal, CorrelationPreview
from app.reused.evidence import EvidenceInput
from app.reused.correlation_evidence import CorrelationEvidencePreview, preview

TENANT = str(UUID("11111111-1111-4111-8111-111111111111"))
NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def request(source="otel", tenant=TENANT):
    return CorrelationEvidencePreview(
        correlation=CorrelationPreview(signals=[CorrelationSignal(
            source="otel", external_event_id="evt-1", service_name="checkout",
            environment="prod", severity="major", status="firing",
            observed_at=NOW, symptom_key="latency",
        )]),
        evidence=[EvidenceInput(
            tenant_id=tenant, incident_id="inc-1", source=source,
            external_id="evt-1", claim="latency", observed_at=NOW,
            payload={"latency_ms": 800},
        )],
    )


def test_exact_source_event_join():
    result = preview(request(), TENANT, now=NOW)
    assert len(result["groups"][0]["evidence"]) == 1
    assert result["groups"][0]["evidence_state"] == "UNVERIFIED"
    assert result["persisted"] is False
    assert result["live_remediation_authorized"] is False


def test_different_source_not_linked():
    result = preview(request(source="prometheus"), TENANT, now=NOW)
    assert result["groups"][0]["evidence"] == []
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"


def test_cross_tenant_rejected():
    with pytest.raises(PermissionError):
        preview(request(tenant="other"), TENANT, now=NOW)


def test_stale_evidence_unknown():
    from datetime import timedelta
    result = preview(request(), TENANT, now=NOW + timedelta(hours=2))
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"


def test_no_evidence_remains_unknown():
    req = request()
    req.evidence = []
    result = preview(req, TENANT, now=NOW)
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["groups"][0]["evidence"] == []


def test_conflicting_duplicate_event_unknown():
    req = request()
    req.evidence.append(req.evidence[0].model_copy(update={"payload": {"latency_ms": 100}}))
    result = preview(req, TENANT, now=NOW)
    assert result["groups"][0]["evidence_state"] == "UNKNOWN"
    assert result["evidence_duplicates"] == 1
