"""Non-persistent human review preview; never grants execution authority."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.reused.telemetry_rca_critic import critique_telemetry
from app.reused.unified_telemetry import TelemetryObservation


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: Literal["request_more_evidence", "reject_hypothesis", "acknowledge_inconclusive"]
    hypothesis_id: str | None = Field(default=None, max_length=80)
    rationale: str = Field(min_length=10, max_length=2000)
    snapshot_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("rationale")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 10:
            raise ValueError("Rationale required")
        return value.strip()


def review_preview(items: list[TelemetryObservation], *, tenant_id: UUID,
                   incident_id: str, reviewer_id: str,
                   review_grants: frozenset[tuple[UUID, str, str]],
                   grants: frozenset[tuple[str, str]], bindings: dict[tuple[str, str], str],
                   snapshot_at: datetime, now: datetime,
                   decision: ReviewDecision | None = None) -> dict:
    """All grants and reviewer identity must be independently server verified."""
    if not isinstance(reviewer_id, str) or not reviewer_id.strip() or len(reviewer_id) > 128:
        raise PermissionError("Invalid reviewer")
    if not isinstance(review_grants, frozenset) or (tenant_id, incident_id, reviewer_id) not in review_grants:
        raise PermissionError("Review access denied")
    if any(not isinstance(t, datetime) or t.utcoffset() is None for t in (now, snapshot_at)):
        raise ValueError("Timezone required")
    if not 0 <= (now - snapshot_at).total_seconds() <= 300:
        raise ValueError("Review snapshot expired or future dated")
    critic = critique_telemetry(items, tenant_id=tenant_id, incident_id=incident_id,
                                grants=grants, bindings=bindings, now=snapshot_at)
    payload = json.dumps({"critic": critic, "reviewer": reviewer_id}, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    digest = sha256(payload.encode()).hexdigest()
    review = None
    if decision is not None:
        if not isinstance(decision, ReviewDecision):
            raise ValueError("Invalid decision")
        decision = ReviewDecision.model_validate(decision.model_dump())
        if decision.snapshot_digest != digest:
            raise ValueError("Review snapshot mismatch")
        ids = {r["hypothesis_id"] for r in critic["reviews"]}
        if decision.hypothesis_id is not None and decision.hypothesis_id not in ids:
            raise ValueError("Unknown hypothesis")
        if decision.decision == "reject_hypothesis" and decision.hypothesis_id is None:
            raise ValueError("Hypothesis required")
        review = decision.model_dump(mode="json")
    return {"schema_version": "gamma.hitl.preview.v1", "tenant_id": str(tenant_id),
            "incident_id": incident_id, "reviewer_id": reviewer_id,
            "snapshot_digest": digest, "snapshot_at": snapshot_at.astimezone(timezone.utc).isoformat(),
            "reviewed_at": now.astimezone(timezone.utc).isoformat() if review else None,
            "critic": critic, "proposed_review": review, "persisted": False,
            "human_adjudicated": False, "authoritative": False,
            "root_cause_confirmed": False, "live_remediation_authorized": False}
