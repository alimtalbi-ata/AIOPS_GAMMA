from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class TimeWindow(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def valid_window(self):
        if (
            self.start.tzinfo is None
            or self.end.tzinfo is None
            or self.start.utcoffset() is None
            or self.end.utcoffset() is None
            or self.end <= self.start
        ):
            raise ValueError("TimeWindow requires timezone-aware increasing timestamps")
        return self


class LogSearchRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.-]+$")
    window: TimeWindow
    severity: list[Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")]] = Field(
        default_factory=list, max_length=10
    )
    limit: int = Field(default=100, ge=1, le=500)


class AlertPayload(BaseModel):
    external_event_id: str = Field(min_length=1, max_length=255)
    source: str = Field(default="opensearch", min_length=1, max_length=100)
    service_name: str = Field(min_length=1, max_length=255)
    severity: Literal["critical", "major", "minor", "warning", "info"]
    status: Literal["firing", "resolved"]
    observed_at: datetime
    evidence_refs: list[Annotated[str, Field(min_length=1, max_length=512)]] = Field(
        default_factory=list, max_length=50
    )

    @field_validator("external_event_id", "source", "service_name")
    @classmethod
    def canonical_alert_identity(cls, value: str) -> str:
        # These values become inbox deduplication keys and outbox aggregate IDs.
        if value != value.strip() or any(
            ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
            for ch in value
        ):
            raise ValueError("alert identity fields must be canonical printable text")
        return value

    @field_validator("evidence_refs")
    @classmethod
    def canonical_alert_evidence_refs(cls, values: list[str]) -> list[str]:
        if any(
            value != value.strip() or any(
                ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
                for ch in value
            )
            for value in values
        ):
            raise ValueError("alert evidence references must be canonical printable text")
        return values

    @field_validator("observed_at")
    @classmethod
    def aware_alert_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("alert observed_at requires a valid UTC offset")
        return value


class BindingIn(BaseModel):
    cmdb_service_id: UUID
    otel_service_name: str = Field(min_length=1, max_length=255)
    environment: str = Field(default="production", min_length=1, max_length=100)

    @field_validator("otel_service_name", "environment")
    @classmethod
    def canonical_binding_identity(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
            for ch in value
        ):
            raise ValueError("service binding identity must be canonical printable text")
        return value


class EvidenceIn(BaseModel):
    investigation_id: UUID
    source_type: Literal["logs", "metrics", "traces", "change"]
    source_ref: str = Field(min_length=1, max_length=512)
    summary: str | None = Field(default=None, max_length=4096)
    observed_at: datetime

    @field_validator("source_ref")
    @classmethod
    def canonical_source_reference(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
            for ch in value
        ):
            raise ValueError("source_ref must be canonical printable text")
        return value

    @model_validator(mode="after")
    def valid_evidence_timestamp(self):
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at requires a valid UTC offset")
        return self
