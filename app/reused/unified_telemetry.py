"""Offline telemetry contract; never authenticates source data or performs I/O."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
import re

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator


class TelemetryObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    tenant_id: UUID
    source: Literal["sentinel", "arguslm"]
    resource_id: str = Field(min_length=1, max_length=128)
    external_id: str = Field(min_length=1, max_length=128)
    source_version: str = Field(min_length=1, max_length=128)
    observed_at: AwareDatetime
    fetched_at: AwareDatetime
    metric: Literal["anomalies_total", "events_processed_total", "latency_ms", "ttft_ms", "availability_ratio"]
    value: float = Field(ge=0, strict=True)

    @field_validator("resource_id", "external_id", "source_version")
    @classmethod
    def canonical_identifier(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value):
            raise ValueError("Invalid identifier")
        return value

    @field_validator("observed_at", "fetched_at", mode="before")
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, datetime) and (
            not isinstance(value, str) or "T" not in value
        ):
            raise ValueError("Explicit ISO timestamp required")
        return value


def preview_observations(items: list[TelemetryObservation], *,
                         tenant_id: UUID,
                         grants: frozenset[tuple[str, str]],
                         now: datetime, max_age_seconds: int = 300) -> dict:
    """Grants must come from trusted server policy, never caller payloads."""
    if not isinstance(tenant_id, UUID) or tenant_id.int == 0:
        raise PermissionError("Invalid authorized tenant")
    if not isinstance(grants, frozenset):
        raise PermissionError("Missing resource grants")
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Timezone required")
    if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400:
        raise ValueError("Invalid freshness bound")
    if not isinstance(items, list) or not 1 <= len(items) <= 500:
        raise ValueError("Invalid batch size")
    records = {}
    for item in items:
        if not isinstance(item, TelemetryObservation):
            raise ValueError("Invalid observation")
        item = TelemetryObservation.model_validate(item.model_dump())
        if item.tenant_id != tenant_id or (item.source, item.resource_id) not in grants:
            raise PermissionError("Telemetry access denied")
        if item.source == "sentinel":
            if item.metric not in ("anomalies_total", "events_processed_total") or not item.value.is_integer() or item.value > 2**53-1:
                raise ValueError("Invalid Sentinel counter")
        elif item.metric not in ("latency_ms", "ttft_ms", "availability_ratio"):
            raise ValueError("Invalid ArgusLM metric")
        if item.metric == "availability_ratio" and item.value > 1:
            raise ValueError("Availability must be a ratio")
        if item.observed_at > item.fetched_at or item.fetched_at > now:
            raise ValueError("Invalid observation chronology")
        key = (item.source, item.resource_id, item.external_id, item.metric)
        if key in records and records[key] != item:
            raise ValueError("Conflicting observation")
        records[key] = item
    rows = []
    for key, item in sorted(records.items()):
        row = item.model_dump(mode="json")
        row["observed_at"] = item.observed_at.astimezone(timezone.utc).isoformat()
        row["fetched_at"] = item.fetched_at.astimezone(timezone.utc).isoformat()
        row["state"] = "STALE" if (now-item.observed_at).total_seconds() > max_age_seconds else "UNVERIFIED"
        rows.append(row)
    return {"schema_version": "gamma.telemetry.preview.v1", "items": rows,
            "duplicates": len(items)-len(rows), "source_authenticated": False,
            "live_remediation_authorized": False, "persisted": False}
