"""Offline cross-source temporal candidates; not alert or causal inference."""
from datetime import datetime
from uuid import UUID
from app.reused.unified_telemetry import TelemetryObservation, preview_observations


def correlate_telemetry(items: list[TelemetryObservation], *, tenant_id: UUID,
                        grants: frozenset[tuple[str, str]],
                        bindings: dict[tuple[str, str], str],
                        now: datetime, window_seconds: int = 120,
                        max_age_seconds: int = 300) -> dict:
    """Bindings and grants must originate in trusted server policy.
    Bindings explicitly map source resources to a shared service identity.
    No matching by unqualified resource names or counter magnitude.
    """
    if type(window_seconds) is not int or not 1 <= window_seconds <= 3600:
        raise ValueError("Invalid correlation window")
    if not isinstance(bindings, dict) or len(bindings) > 1000:
        raise ValueError("Invalid service bindings")
    normalized = preview_observations(items, tenant_id=tenant_id, grants=grants,
                                      now=now, max_age_seconds=max_age_seconds)
    fresh = []
    excluded = {"stale": 0, "unmapped": 0}
    for index, row in enumerate(normalized["items"]):
        if row["state"] == "STALE":
            excluded["stale"] += 1
            continue
        service = bindings.get((row["source"], row["resource_id"]))
        if not isinstance(service, str) or not service or len(service) > 128 or not service.isascii() or not all(c.isalnum() or c in "_.:-" for c in service):
            excluded["unmapped"] += 1
            continue
        fresh.append((index, row, service, datetime.fromisoformat(row["observed_at"])))
    # A batch is bounded by the normalizer; emit at most 500 candidate edges.
    candidates = []
    total = 0
    for left in fresh:
        if left[1]["source"] != "sentinel":
            continue
        for right in fresh:
            if right[1]["source"] != "arguslm" or left[2] != right[2]:
                continue
            distance = abs((left[3] - right[3]).total_seconds())
            if distance <= window_seconds:
                total += 1
                if len(candidates) < 500:
                    candidates.append({"sentinel_index": left[0], "arguslm_index": right[0],
                                       "service_id": left[2], "distance_seconds": distance,
                                       "state": "UNVERIFIED", "relation": "TEMPORAL_PROXIMITY"})
    return {"schema_version": "gamma.telemetry.correlation.preview.v1",
            "observations": normalized["items"], "duplicates": normalized["duplicates"],
            "excluded": excluded, "candidates": candidates, "candidate_count": total,
            "truncated": total > len(candidates), "source_authenticated": False,
            "causality_established": False, "persisted": False,
            "live_remediation_authorized": False}
