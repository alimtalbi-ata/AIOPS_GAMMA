"""Deterministic, bounded, read-only alert correlation preview.

Inspired by aiops NOC canonical identity checks and Aurora's recurring-incident
investigation UX. No incident lifecycle writes, ticket creation or LIVE effects.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CorrelationSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=80)
    external_event_id: str = Field(min_length=1, max_length=255)
    service_name: str = Field(min_length=1, max_length=255)
    environment: str = Field(min_length=1, max_length=80)
    severity: Literal["critical", "major", "minor", "warning", "info"]
    status: Literal["firing", "resolved"]
    observed_at: datetime
    ci_id: str | None = Field(default=None, min_length=1, max_length=255)
    symptom_key: str = Field(min_length=1, max_length=255)
    evidence_refs: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("source", "external_event_id", "service_name", "environment", "symptom_key")
    @classmethod
    def validate_identity(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
            for ch in value
        ):
            raise ValueError("identity fields must be canonical printable text")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, refs: list[str]) -> list[str]:
        # Bounded, printable references only: never propagate arbitrary upstream
        # text or control characters as evidence identifiers in a preview.
        if any(not ref or len(ref) > 256 or ref != ref.strip()
               or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
                      for ch in ref) for ref in refs):
            raise ValueError("invalid correlation evidence reference")
        return refs

    @model_validator(mode="after")
    def validate_time(self):
        if self.ci_id is not None and (
            self.ci_id != self.ci_id.strip()
            or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
                   for ch in self.ci_id)
        ):
            raise ValueError("ci_id must be canonical printable text")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must have a timezone with a valid UTC offset")
        return self


class CorrelationPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signals: list[CorrelationSignal] = Field(min_length=1, max_length=500)
    window_seconds: int = Field(default=300, ge=30, le=3600)


_SEVERITY = {"critical": 5, "major": 4, "minor": 3, "warning": 2, "info": 1}


def correlate(signals: list[CorrelationSignal], tenant_id: str, window_seconds: int = 300) -> dict:
    """Exact source ID dedup, then deterministic service/CI/symptom window groups.

    Caller tenant identity must be independently authenticated. No inferred
    cross-service topology; that requires separately verified CMDB data.
    """
    if (not isinstance(signals, list) or not 1 <= len(signals) <= 500
            or not isinstance(window_seconds, int) or isinstance(window_seconds, bool)
            or not 30 <= window_seconds <= 3600):
        raise ValueError("correlation bounds exceeded")
    if (not isinstance(tenant_id, str) or not tenant_id.strip()
            or tenant_id != tenant_id.strip()
            or len(tenant_id) > 128
            or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
                   for ch in tenant_id)):
        raise ValueError("Invalid correlation tenant identity")
    if any(not isinstance(signal, CorrelationSignal) for signal in signals):
        raise ValueError("Invalid correlation signal structure")
    # Protect direct callers against mutations after Pydantic construction.
    signals = [CorrelationSignal.model_validate(signal.model_dump()) for signal in signals]
    seen: dict[tuple[str, str], CorrelationSignal] = {}
    highest_severity_by_identity: dict[tuple[str, str], str] = {}
    conflicting_identities: set[tuple[str, str]] = set()
    duplicates = 0
    for signal in signals:
        identity = (signal.source, signal.external_event_id)
        previous_severity = highest_severity_by_identity.get(identity)
        if previous_severity is None or _SEVERITY[signal.severity] > _SEVERITY[previous_severity]:
            highest_severity_by_identity[identity] = signal.severity
        if identity in seen:
            duplicates += 1
            if seen[identity] != signal:
                conflicting_identities.add(identity)
                # Deterministic representative: never let input order choose
                # the displayed severity, status or grouping attributes.
                if signal.model_dump_json() < seen[identity].model_dump_json():
                    seen[identity] = signal
            continue
        seen[identity] = signal
    unique = list(seen.values())
    unique.sort(key=lambda s: (s.observed_at.astimezone(timezone.utc), s.source, s.external_event_id))
    groups: list[dict] = []
    # Indexed by the complete grouping key. A single pass over sorted signals
    # avoids repeatedly scanning all previous groups for every incoming event.
    latest_group_by_key: dict[tuple, dict] = {}
    for signal in unique:
        timestamp = signal.observed_at.astimezone(timezone.utc)
        # A CI identifier alone cannot authorize or justify a cross-service join.
        # Always retain service identity, even when CI metadata is supplied.
        key = (signal.environment, signal.service_name, signal.ci_id, signal.symptom_key)
        matching = latest_group_by_key.get(key)
        if matching is not None and timestamp - matching["_first"] > timedelta(seconds=window_seconds):
            matching = None
        if matching is None:
            stable_key = json.dumps((tenant_id, *key, timestamp.isoformat()), ensure_ascii=False, separators=(",", ":"))
            matching = {
                "_key": key, "_first": timestamp, "_last": timestamp,
                "group_id": "grp-" + sha256(stable_key.encode()).hexdigest()[:20],
                "service_name": signal.service_name,
                "environment": signal.environment,
                "ci_id": signal.ci_id,
                "symptom_key": signal.symptom_key,
                "severity": signal.severity,
                "status": signal.status,
                "first_observed_at": timestamp.isoformat(),
                "last_observed_at": timestamp.isoformat(),
                "source_events": [],
                "evidence_refs": [],
                "_evidence_ref_set": set(),
            }
            groups.append(matching)
            latest_group_by_key[key] = matching
        matching["_last"] = timestamp
        matching["last_observed_at"] = timestamp.isoformat()
        # A duplicate may have a higher severity than the deterministic
        # representative. Never understate the observed maximum, while
        # keeping severity_state UNKNOWN for conflicting source identities.
        observed_severity = highest_severity_by_identity[(signal.source, signal.external_event_id)]
        if _SEVERITY[observed_severity] > _SEVERITY[matching["severity"]]:
            matching["severity"] = observed_severity
        if signal.status == "firing":
            matching["status"] = "firing"
        matching["source_events"].append({
            "source": signal.source,
            "external_event_id": signal.external_event_id,
            "status": signal.status,
        })
        for ref in signal.evidence_refs:
            if ref not in matching["_evidence_ref_set"]:
                matching["_evidence_ref_set"].add(ref)
                matching["evidence_refs"].append(ref)
    for group in groups:
        group.pop("_key")
        group.pop("_first")
        group.pop("_last")
        group.pop("_evidence_ref_set")
        group["evidence_refs"].sort()
        group["event_count"] = len(group["source_events"])
        group["conflicting_source_events"] = sum(
            (event["source"], event["external_event_id"]) in conflicting_identities
            for event in group["source_events"]
        )
        # A conflicting source identity can have multiple severity values.
        # The deterministic representative is only a display choice, not
        # authoritative evidence of the incident's actual severity.
        group["severity_state"] = (
            "UNKNOWN" if group["conflicting_source_events"] else "UNVERIFIED"
        )
        # A mixed firing/resolved group is not proof of recovery. Surface
        # ambiguity rather than promoting a derived incident lifecycle state.
        statuses = {event["status"] for event in group["source_events"]}
        group["resolution_state"] = (
            "UNKNOWN" if group["conflicting_source_events"] or len(statuses) > 1
            else "FIRING_UNVERIFIED" if statuses == {"firing"}
            else "RESOLVED_UNVERIFIED"
        )
        group["impact_state"] = "UNKNOWN_UNTIL_CMDB_VERIFIED"
        group["root_cause_state"] = "UNKNOWN"
        group["itsm_ticket_state"] = "NOT_CREATED"
    return {
        "schema_version": "aiops.gamma.correlation-preview.v1",
        "source_events": len(signals),
        "deduplicated_events": duplicates,
        "conflicting_source_events": len(conflicting_identities),
        "groups": groups,
        "persisted": False,
        "live_remediation_authorized": False,
    }
