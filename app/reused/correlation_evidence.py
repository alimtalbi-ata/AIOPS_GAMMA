"""Read-only correlation/evidence join. Never infers canonical incident identity."""
from pydantic import BaseModel, Field
from app.reused.correlation import CorrelationPreview, correlate
from app.reused.evidence import EvidenceInput, normalize
from datetime import datetime, timezone


class CorrelationEvidencePreview(BaseModel):
    correlation: CorrelationPreview
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=500)
    max_age_seconds: int = Field(default=3600, ge=1, le=86400)


def preview(request: CorrelationEvidencePreview, tenant_id: str, *, now: datetime | None = None) -> dict:
    """Match only explicit source+external_event_id, never a fuzzy service name."""
    if any(e.tenant_id != tenant_id for e in request.evidence):
        raise PermissionError("Cross-tenant evidence rejected")
    corr = correlate(request.correlation.signals, tenant_id, request.correlation.window_seconds)
    evidence_result = (
        normalize(request.evidence, now=now or datetime.now(timezone.utc), max_age_seconds=request.max_age_seconds)
        if request.evidence else {"items": [], "duplicates": 0}
    )
    for group in corr["groups"]:
        event_ids = {(e["source"], e["external_event_id"]) for e in group["source_events"]}
        linked = [e for e in evidence_result["items"]
                  if (e["source"], e["external_id"]) in event_ids]
        group["evidence"] = linked
        # The source-event identity is not a canonical incident identifier.
        # Multiple incident claims for one group must not be treated as corroboration.
        incident_ids = {e["incident_id"] for e in linked}
        group["evidence_state"] = "UNKNOWN" if (
            not linked or len(incident_ids) > 1
            or any(e["state"] == "UNKNOWN" for e in linked)
        ) else "UNVERIFIED"
    corr["evidence_duplicates"] = evidence_result["duplicates"]
    corr["schema_version"] = "aiops.gamma.correlation-evidence-preview.v1"
    corr["persisted"] = False
    corr["live_remediation_authorized"] = False
    return corr
