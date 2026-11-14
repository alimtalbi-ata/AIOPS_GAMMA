"""Deterministic, bounded, read-only alert correlation preview.

Inspired by aiops NOC canonical identity checks and Aurora's recurring-incident
investigation UX. No incident lifecycle writes, ticket creation or LIVE effects.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CorrelationSignal(BaseModel):
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
        if value != value.strip():
            raise ValueError("identity fields must not contain surrounding whitespace")
        return value

    @model_validator(mode="after")
    def validate_time(self):
        if self.ci_id is not None and self.ci_id != self.ci_id.strip():
            raise ValueError("ci_id must not contain surrounding whitespace")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must have a timezone")
        return self


class CorrelationPreview(BaseModel):
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
    if not isinstance(tenant_id, str) or not tenant_id.strip() or tenant_id != tenant_id.strip():
        raise ValueError("Invalid correlation tenant identity")
    if any(not isinstance(signal, CorrelationSignal) for signal in signals):
        raise ValueError("Invalid correlation signal structure")
    # Protect direct callers against mutations after Pydantic construction.
    signals = [CorrelationSignal.model_validate(signal.model_dump()) for signal in signals]
    seen: dict[tuple[str, str], CorrelationSignal] = {}
    conflicting_identities: set[tuple[str, str]] = set()
    duplicates = 0
    for signal in signals:
        identity = (signal.source, signal.external_event_id)
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
    for signal in unique:
        timestamp = signal.observed_at.astimezone(timezone.utc)
        key = (signal.environment, "ci" if signal.ci_id else "service",
               signal.ci_id if signal.ci_id else signal.service_name, signal.symptom_key)
        matching = next((
            g for g in reversed(groups)
            if g["_key"] == key
            and timestamp - g["_last"] <= timedelta(seconds=window_seconds)
        ), None)
        if matching is None:
            stable_key = json.dumps((tenant_id, *key, timestamp.isoformat()), ensure_ascii=False, separators=(",", ":"))
            matching = {
                "_key": key, "_last": timestamp,
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
            }
            groups.append(matching)
        matching["_last"] = timestamp
        matching["last_observed_at"] = timestamp.isoformat()
        if _SEVERITY[signal.severity] > _SEVERITY[matching["severity"]]:
            matching["severity"] = signal.severity
        if signal.status == "firing":
            matching["status"] = "firing"
        matching["source_events"].append({
            "source": signal.source,
            "external_event_id": signal.external_event_id,
            "status": signal.status,
        })
        for ref in signal.evidence_refs:
            if ref not in matching["evidence_refs"]:
                matching["evidence_refs"].append(ref)
    for group in groups:
        group.pop("_key")
        group.pop("_last")
        group["evidence_refs"].sort()
        group["event_count"] = len(group["source_events"])
        group["conflicting_source_events"] = sum(
            (event["source"], event["external_event_id"]) in conflicting_identities
            for event in group["source_events"]
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
