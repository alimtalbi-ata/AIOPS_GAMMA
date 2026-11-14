"""Read-only evidence normalization adapted from aiops/app/evidence/main.py.

No database, network access, remediation, or inferred proof of integrity.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from pydantic import BaseModel, Field, model_validator


def _require_string_json_keys(value: object) -> None:
    """Reject non-string keys, cyclic containers and excessive JSON nesting."""
    stack = [(value, 0, False)]
    active: set[int] = set()
    while stack:
        node, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(node))
            continue
        if not isinstance(node, (dict, list, tuple)):
            continue
        if depth > 64:
            raise ValueError("JSON nesting exceeds 64 levels")
        if id(node) in active:
            raise ValueError("Cyclic JSON container rejected")
        active.add(id(node))
        stack.append((node, depth, True))
        if isinstance(node, dict):
            for key, nested in node.items():
                if not isinstance(key, str):
                    raise ValueError("JSON object keys must be strings")
                stack.append((nested, depth + 1, False))
        else:
            for nested in node:
                stack.append((nested, depth + 1, False))


class EvidenceInput(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    incident_id: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=255)
    claim: str = Field(min_length=1, max_length=2048)
    observed_at: datetime
    payload: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def aware_timestamp(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at requires timezone")
        for name, limit in (("payload", 65536), ("provenance", 8192)):
            _require_string_json_keys(getattr(self, name))
            try:
                encoded = json.dumps(getattr(self, name), allow_nan=False, sort_keys=True, separators=(",", ":"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be finite JSON") from exc
            if len(encoded.encode("utf-8")) > limit:
                raise ValueError(f"{name} exceeds {limit} bytes")
        return self


def observed_at_key(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def normalize(items: list[EvidenceInput], *, now: datetime, max_age_seconds: int = 3600) -> dict:
    """Bounded preview; identical claims can conflict and are never auto-resolved."""
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now requires timezone")
    if (not isinstance(items, list) or not 1 <= len(items) <= 500
            or not isinstance(max_age_seconds, int) or isinstance(max_age_seconds, bool)
            or not 1 <= max_age_seconds <= 86400):
        raise ValueError("evidence bounds exceeded")
    if any(not isinstance(item, EvidenceInput) for item in items):
        raise ValueError("Invalid evidence input structure")
    # Mutable evidence and nested payload/provenance can bypass construction
    # validators. Recheck timestamps, finite JSON and byte budgets at use time.
    items = [EvidenceInput.model_validate(item.model_dump()) for item in items]
    now = now.astimezone(timezone.utc)
    seen = {}
    conflicts = set()
    results = []
    duplicate_count = 0
    claims = {}
    # Sort before deduplication so contradictory versions cannot make the
    # displayed representative depend on collector arrival order.
    def stable_order(item: EvidenceInput) -> tuple:
        return (
            item.tenant_id, item.incident_id, item.source, item.external_id,
            json.dumps(item.payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
            json.dumps(item.provenance, sort_keys=True, separators=(",", ":"), allow_nan=False),
            item.claim, observed_at_key(item.observed_at),
        )

    for item in sorted(items, key=stable_order):
        key = (item.tenant_id, item.incident_id, item.source, item.external_id)
        canonical = json.dumps(item.payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = sha256(canonical.encode("utf-8")).hexdigest()
        provenance_canonical = json.dumps(item.provenance, sort_keys=True, separators=(",", ":"), allow_nan=False)
        provenance_digest = sha256(provenance_canonical.encode("utf-8")).hexdigest()
        if key in seen:
            duplicate_count += 1
            if seen[key] != (digest, provenance_digest, item.claim, observed_at_key(item.observed_at)):
                conflicts.add(key)
            continue
        seen[key] = (digest, provenance_digest, item.claim, observed_at_key(item.observed_at))
        observed = item.observed_at.astimezone(timezone.utc)
        fresh = timedelta(0) <= now - observed <= timedelta(seconds=max_age_seconds)
        # Hashing the supplied payload does not authenticate its source.
        state = "UNVERIFIED" if fresh else "UNKNOWN"
        results.append({
            "tenant_id": item.tenant_id, "incident_id": item.incident_id,
            "source": item.source, "external_id": item.external_id,
            "claim": item.claim, "observed_at": observed.isoformat(),
            "payload_sha256": digest, "provenance_sha256": provenance_digest,
            "freshness": "FRESH" if fresh else "UNKNOWN",
            "integrity": "UNVERIFIED", "state": state,
        })
        claims.setdefault((item.tenant_id, item.incident_id, item.claim), set()).add(digest)
    for result in results:
        if (len(claims[(result["tenant_id"], result["incident_id"], result["claim"])]) > 1
                or (result["tenant_id"], result["incident_id"], result["source"], result["external_id"]) in conflicts):
            result["state"] = "UNKNOWN"
    return {
        "schema_version": "aiops.gamma.evidence-preview.v1",
        "items": results, "duplicates": duplicate_count,
        "persisted": False, "live_remediation_authorized": False,
    }
