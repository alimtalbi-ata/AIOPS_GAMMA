from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.reused.unified_telemetry import TelemetryObservation, preview_observations

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TENANT = uuid4()
GRANTS = frozenset({("sentinel", "svc-1")})


def sample(**changes):
    data = dict(tenant_id=TENANT, source="sentinel", resource_id="svc-1",
                external_id="event-1", source_version="v1",
                observed_at=NOW, fetched_at=NOW, metric="anomalies_total", value=2)
    return TelemetryObservation(**(data | changes))


def preview(*items):
    return preview_observations(list(items), tenant_id=TENANT, grants=GRANTS, now=NOW)


def test_duplicate_and_unverified():
    result = preview(sample(), sample())
    assert result["duplicates"] == 1
    assert result["items"][0]["state"] == "UNVERIFIED"
    assert result["source_authenticated"] is False
    assert result["live_remediation_authorized"] is False


@pytest.mark.parametrize("changes", [{"tenant_id": uuid4()}, {"resource_id": "svc-2"}])
def test_scope_denied(changes):
    with pytest.raises(PermissionError):
        preview(sample(**changes))


def test_stale():
    assert preview(sample(observed_at=NOW-timedelta(seconds=301)))["items"][0]["state"] == "STALE"


def test_conflicting_duplicate():
    with pytest.raises(ValueError):
        preview(sample(), sample(value=3))


@pytest.mark.parametrize("changes", [{"value": 1.5}, {"metric": "latency_ms"},
                                     {"fetched_at": NOW+timedelta(seconds=1)}])
def test_invalid_observation(changes):
    with pytest.raises(ValueError):
        preview(sample(**changes))


def test_arguslm_ratio():
    row = sample(source="arguslm", metric="availability_ratio", value=0.99)
    result = preview_observations([row], tenant_id=TENANT,
        grants=frozenset({("arguslm", "svc-1")}), now=NOW)
    assert result["items"][0]["value"] == 0.99
    with pytest.raises(ValueError):
        preview_observations([row.model_copy(update={"value": 2})], tenant_id=TENANT,
            grants=frozenset({("arguslm", "svc-1")}), now=NOW)
