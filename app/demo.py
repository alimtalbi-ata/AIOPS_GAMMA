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
