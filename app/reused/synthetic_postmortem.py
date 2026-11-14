"""UC10: reviewable, synthetic-only postmortem draft; no inferred closure.

Caller-supplied incident facts are not canonical evidence. Missing timelines
and unverified RCA remain explicit unknowns. Never writes an ITSM record.
"""
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    summary: str = Field(min_length=1, max_length=500)
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("event_id", "summary", "evidence_ref")
    @classmethod
    def nonblank_event_fields(cls, value):
        if value is not None and (not value.strip() or value != value.strip()
                                  or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError("Invalid timeline event field")
        return value

    @model_validator(mode="after")
    def require_timezone(self):
        if self.occurred_at.utcoffset() is None:
            raise ValueError("Timeline event must be timezone-aware")
        return self


class PostmortemDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    incident_id: str = Field(min_length=1, max_length=128)
    service_name: str = Field(min_length=1, max_length=255)
    timeline: list[TimelineEvent] = Field(default_factory=list, max_length=100)
    rca_summary: str | None = Field(default=None, min_length=1, max_length=1000)
    impact_summary: str | None = Field(default=None, min_length=1, max_length=1000)
    follow_up_candidates: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("incident_id", "service_name", "rca_summary", "impact_summary")
    @classmethod
    def nonblank_incident_fields(cls, value):
        if value is not None and (not value.strip() or value != value.strip()
                                  or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError("Invalid postmortem field")
        return value

    @field_validator("follow_up_candidates")
    @classmethod
    def validate_follow_ups(cls, values):
        if any(not isinstance(value, str) or not value.strip() or
               value != value.strip() or len(value) > 500 or
               any(ord(char) < 32 or ord(char) == 127 for char in value)
               for value in values):
            raise ValueError("Invalid follow-up candidate")
        return values


def draft_postmortem(req: PostmortemDraftRequest, authorized_tenant: UUID) -> dict:
    if not isinstance(req, PostmortemDraftRequest) or not isinstance(authorized_tenant, UUID):
        raise ValueError("Invalid postmortem request or authorized tenant")
    # Mutable Pydantic models may be changed after validation. Revalidate at
    # the preview boundary before interpreting any caller-provided fields.
    req = PostmortemDraftRequest.model_validate(req.model_dump())
    if req.tenant_id != authorized_tenant:
        raise PermissionError("Cross-tenant postmortem rejected")
    if len({e.event_id for e in req.timeline}) != len(req.timeline):
        raise ValueError("Duplicate timeline event identifier")
    events = sorted(req.timeline, key=lambda e: (e.occurred_at.astimezone(timezone.utc), e.event_id))
    return {
        "schema_version": "aiops.gamma.synthetic-postmortem.v1",
        "tenant_id": str(authorized_tenant),
        "incident_id": req.incident_id,
        "service_name": req.service_name,
        "timeline": [{
            "event_id": e.event_id,
            "occurred_at": e.occurred_at.astimezone(timezone.utc).isoformat(),
            "summary": e.summary,
            "evidence_ref": e.evidence_ref,
            "source_verified": False,
        } for e in events],
        "timeline_state": "UNVERIFIED" if events else "UNKNOWN",
        "root_cause_state": "UNVERIFIED" if req.rca_summary else "UNKNOWN",
        "root_cause_summary": req.rca_summary,
        "impact_state": "UNVERIFIED" if req.impact_summary else "UNKNOWN",
        "impact_summary": req.impact_summary,
        "follow_up_candidates": list(req.follow_up_candidates),
        "human_review_required": True,
        "authoritative": False,
        "data_source": "caller_supplied_preview",
        "persisted": False,
        "itsm_mutations_performed": False,
        "incident_closed": False,
        "live_remediation_authorized": False,
    }
