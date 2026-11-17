"""Public synthetic demo only. Never reads tenant data or external services."""
from datetime import datetime, timezone

from app.reused.correlation import CorrelationSignal, correlate


def synthetic_correlation_demo() -> dict:
    signals = [
        CorrelationSignal(
            source="gamma-synthetic", external_event_id="demo-payment-timeout-1",
            service_name="payment-service", environment="demo",
            severity="critical", status="firing",
            observed_at=datetime(2026, 11, 9, 14, 32, tzinfo=timezone.utc),
            symptom_key="payment-timeout", evidence_refs=["demo-trace-1"],
        ),
        CorrelationSignal(
            source="gamma-synthetic", external_event_id="demo-payment-timeout-2",
            service_name="payment-service", environment="demo",
            severity="major", status="firing",
            observed_at=datetime(2026, 11, 9, 14, 33, tzinfo=timezone.utc),
            symptom_key="payment-timeout", evidence_refs=["demo-log-1"],
        ),
    ]
    result = correlate(signals, "00000000-0000-0000-0000-000000000001", 300)
    return {"mode": "synthetic_demo", "authoritative": False, "correlation": result}


def synthetic_investigation_demo() -> dict:
    """Exercise existing correlation + evidence join with fixed, non-authoritative inputs."""
    from app.reused.correlation import CorrelationPreview
    from app.reused.correlation_evidence import CorrelationEvidencePreview, preview
    from app.reused.evidence import EvidenceInput

    tenant = "00000000-0000-0000-0000-000000000001"
    observed = datetime(2026, 11, 9, 14, 32, tzinfo=timezone.utc)
    signals = [
        CorrelationSignal(
            source="gamma-synthetic", external_event_id=f"demo-payment-timeout-{i}",
            service_name="payment-service", environment="demo",
            severity="critical" if i == 1 else "major", status="firing",
            observed_at=observed.replace(minute=32 + i - 1),
            symptom_key="payment-timeout", evidence_refs=[f"demo-proof-{i}"],
        ) for i in (1, 2)
    ]
    evidence = [
        EvidenceInput(
            tenant_id=tenant, incident_id="DEMO-INCIDENT-1",
            source="gamma-synthetic", external_id=f"demo-payment-timeout-{i}",
            claim=f"Synthetic timeout observation {i}",
            observed_at=observed.replace(minute=32 + i - 1),
            payload={"kind": "synthetic", "event": i},
            provenance={"origin": "bundled-demo", "verified": False},
        ) for i in (1, 2)
    ]
    result = preview(
        CorrelationEvidencePreview(
            correlation=CorrelationPreview(signals=signals, window_seconds=300),
            evidence=evidence, max_age_seconds=3600,
        ),
        tenant, now=datetime(2026, 11, 9, 14, 35, tzinfo=timezone.utc),
    )
    return {
        "mode": "synthetic_demo", "authoritative": False,
        "evidence_source_verified": False, "investigation": result,
    }
