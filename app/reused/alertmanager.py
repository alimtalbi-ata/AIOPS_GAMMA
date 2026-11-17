"""Bounded, pure Alertmanager/Grafana webhook normalizer for correlation previews.

Source concepts: akmatori-sre/internal/alerts/adapters/{alertmanager,grafana}.go
No source code copied, no webhook exposed: caller must pass through trusted
internal auth; incoming notifications are untrusted observations, not commands.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.reused.correlation import CorrelationSignal

_ALLOWED_SEVERITY = {
    "critical": "critical",
    "fatal": "critical",
    "p1": "critical",
    "high": "major",
    "major": "major",
    "error": "major",
    "p2": "major",
    "minor": "minor",
    "warning": "warning",
    "warn": "warning",
    "info": "info",
}
_LABEL = r"^[a-zA-Z0-9_.:/-]{1,255}$"


class UpstreamAlert(BaseModel):
    model_config = ConfigDict(extra="ignore")
    status: Literal["firing", "resolved"]
    fingerprint: str = Field(min_length=1, max_length=255, pattern=_LABEL)
    labels: dict[str, str] = Field(min_length=1, max_length=40)
    annotations: dict[str, str] = Field(default_factory=dict, max_length=40)
    startsAt: datetime

    @model_validator(mode="after")
    def valid_fields(self):
        if self.startsAt.tzinfo is None:
            raise ValueError("startsAt must include timezone")
        for collection in (self.labels, self.annotations):
            if any(
                not key or len(key) > 120 or len(value) > 500
                for key, value in collection.items()
            ):
                raise ValueError("Alert labels and annotations exceed policy bounds")
        return self


class AlertmanagerBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    alerts: list[UpstreamAlert] = Field(min_length=1, max_length=100)
    status: Literal["firing", "resolved"] | None = None


class AlertNormalizeRequest(BaseModel):
    source: Literal["alertmanager", "grafana"]
    environment: str = Field(min_length=1, max_length=80, pattern=_LABEL)
    payload: AlertmanagerBatch


def normalize_alerts(req: AlertNormalizeRequest) -> list[CorrelationSignal]:
    """Normalize each alert; do not use webhook annotations for tool invocation.

    A validated CMDB binding is required to assign ci_id; source-provided
    labels cannot assert asset ownership or authorize remediation.
    """
    result = []
    for alert in req.payload.alerts:
        labels = alert.labels
        service = labels.get("service") or labels.get("job") or labels.get("app")
        symptom = labels.get("alertname")
        if not service or not symptom:
            raise ValueError("Alert requires service/job/app and alertname labels")
        if len(service) > 255 or len(symptom) > 255:
            raise ValueError("Alert service or symptom exceeds limits")
        # Source identity must include the monitored environment; a fingerprint
        # is not globally unique and is never a canonical incident identifier.
        event_id = sha256(
            f"{req.environment}|{alert.fingerprint}|{alert.startsAt.isoformat()}|{alert.status}".encode()
        ).hexdigest()
        result.append(CorrelationSignal(
            source=req.source,
            external_event_id=event_id,
            service_name=service,
            environment=req.environment,
            severity=_ALLOWED_SEVERITY.get(labels.get("severity", "").lower(), "warning"),
            status=alert.status,
            observed_at=alert.startsAt,
            ci_id=None,
            symptom_key=symptom,
            evidence_refs=[],
        ))
    return result
