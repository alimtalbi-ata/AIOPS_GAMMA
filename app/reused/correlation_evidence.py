"""Read-only correlation/evidence join. Never infers canonical incident identity."""
from pydantic import BaseModel, ConfigDict, Field
from app.reused.correlation import CorrelationPreview, correlate
from app.reused.evidence import EvidenceInput, normalize, _require_string_json_keys
from datetime import datetime, timezone


class CorrelationEvidencePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: CorrelationPreview
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=500)
    max_age_seconds: int = Field(default=3600, ge=1, le=86400)


def preview(request: CorrelationEvidencePreview, tenant_id: str, *, now: datetime | None = None) -> dict:
    """Match only explicit source+external_event_id, never a fuzzy service name."""
    if (not isinstance(request, CorrelationEvidencePreview)
            or not isinstance(tenant_id, str) or not tenant_id.strip()
            or tenant_id != tenant_id.strip()
            or len(tenant_id) > 128
            or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
                   for ch in tenant_id)):
        raise ValueError("Invalid correlation/evidence request or tenant")
    if (not isinstance(request.max_age_seconds, int)
            or isinstance(request.max_age_seconds, bool)):
        raise ValueError("Invalid evidence freshness bound")
    if (now is not None and (not isinstance(now, datetime)
            or now.tzinfo is None or now.utcoffset() is None)):
        raise ValueError("now requires timezone")
    if not isinstance(request.evidence, list):
        raise ValueError("Invalid correlation evidence collection")
    # Nested Pydantic inputs may be mutated after construction. Revalidate
    # evidence timestamps, payload bounds and correlation signals at the gate.
    # Guard mutated nested evidence before Pydantic serialization: a cyclic or
    # excessively deep payload must fail with a bounded validation error.
    for item in request.evidence:
        if not isinstance(item, EvidenceInput):
            raise ValueError("Invalid correlation evidence item")
        _require_string_json_keys(item.payload)
        _require_string_json_keys(item.provenance)
    request = CorrelationEvidencePreview.model_validate(request.model_dump())
    if any(e.tenant_id != tenant_id for e in request.evidence):
        raise PermissionError("Cross-tenant evidence rejected")
    corr = correlate(request.correlation.signals, tenant_id, request.correlation.window_seconds)
    evidence_result = (
        normalize(request.evidence, now=now or datetime.now(timezone.utc), max_age_seconds=request.max_age_seconds)
        if request.evidence else {"items": [], "duplicates": 0}
    )
    all_event_ids = {
        (event["source"], event["external_event_id"])
        for group in corr["groups"] for event in group["source_events"]
    }
    unmatched = sum(
        (item["source"], item["external_id"]) not in all_event_ids
        for item in evidence_result["items"]
    )
    corr["unmatched_evidence"] = unmatched
    # Index normalized evidence once, preserving its original order and every
    # distinct incident claim for a source event. Avoid scanning all evidence
    # for each correlated group (up to 500 groups x 500 evidence records).
    evidence_by_event: dict[tuple[str, str], list[dict]] = {}
    for item in evidence_result["items"]:
        evidence_by_event.setdefault((item["source"], item["external_id"]), []).append(item)
    evidence_order = {id(item): index for index, item in enumerate(evidence_result["items"])}
    for group in corr["groups"]:
        event_ids = {(e["source"], e["external_event_id"]) for e in group["source_events"]}
        # Retain normalized ordering even when events within a group differ.
        linked = sorted(
            (item for event_id in event_ids for item in evidence_by_event.get(event_id, [])),
            key=lambda item: evidence_order[id(item)],
        )
        covered_events = {(e["source"], e["external_id"]) for e in linked}
        group["evidence_covered_events"] = len(covered_events)
        group["evidence_missing_events"] = len(event_ids - covered_events)
        group["evidence"] = linked
        # The source-event identity is not a canonical incident identifier.
        # Multiple incident claims for one group must not be treated as corroboration.
        incident_ids = {e["incident_id"] for e in linked}
        group["evidence_state"] = "UNKNOWN" if (
            len(covered_events) != len(event_ids) or len(incident_ids) > 1
            or group["conflicting_source_events"] > 0
            or any(e["state"] == "UNKNOWN" for e in linked)
        ) else "UNVERIFIED"
    # Complete means both directions are covered, not merely that every
    # supplied evidence item found a matching source event.
    corr["evidence_join_complete"] = (
        unmatched == 0
        and all(group["evidence_missing_events"] == 0 for group in corr["groups"])
    )
    # Coverage alone does not establish consistency or provenance authenticity.
    corr["evidence_join_consistent"] = (
        corr["evidence_join_complete"]
        and all(group["evidence_state"] != "UNKNOWN" for group in corr["groups"])
    )
    corr["evidence_duplicates"] = evidence_result["duplicates"]
    corr["schema_version"] = "aiops.gamma.correlation-evidence-preview.v1"
    corr["persisted"] = False
    corr["live_remediation_authorized"] = False
    return corr
