from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TimeWindow(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def valid_window(self):
        if not self.start.tzinfo or not self.end.tzinfo or self.end <= self.start:
            raise ValueError("TimeWindow requires timezone-aware increasing timestamps")
        return self


class LogSearchRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.-]+$")
    window: TimeWindow
    severity: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=100, ge=1, le=500)


class AlertPayload(BaseModel):
    external_event_id: str = Field(min_length=1, max_length=255)
    source: str = Field(default="opensearch", min_length=1, max_length=100)
    service_name: str = Field(min_length=1, max_length=255)
    severity: Literal["critical", "major", "minor", "warning", "info"]
    status: Literal["firing", "resolved"]
    observed_at: datetime
    evidence_refs: list[str] = Field(default_factory=list)


class BindingIn(BaseModel):
    cmdb_service_id: UUID
    otel_service_name: str = Field(min_length=1, max_length=255)
    environment: str = Field(default="production", min_length=1, max_length=100)


class EvidenceIn(BaseModel):
    investigation_id: UUID
    source_type: Literal["logs", "metrics", "traces", "change"]
    source_ref: str = Field(min_length=1)
    summary: str | None = None
    observed_at: datetime
