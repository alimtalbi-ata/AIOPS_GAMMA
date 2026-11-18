"""Route-level least-privilege checks for tenant resource grants."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from app.main import add_evidence, logs
from app.schemas import EvidenceIn, LogSearchRequest
from app.security import Principal
from app.settings import settings


def principal(*, log_grants=(), incident_grants=()):
    return Principal(
        tenant_id=uuid4(), subject="user:acl-test", actor_type="user",
        assertion_id="acl-test-assertion", expires_at=2_000_000_000,
        log_service_grants=tuple(log_grants),
        evidence_incident_grants=tuple(incident_grants),
        business_permissions=("evidence:write",),
    )


@pytest.mark.asyncio
async def test_log_search_denies_service_without_explicit_grant(monkeypatch):
    monkeypatch.setattr(settings, "enable_opensearch", True)
    now = datetime.now(timezone.utc)
    request = LogSearchRequest(
        service_name="checkout-api",
        window={"start": now - timedelta(minutes=5), "end": now},
    )
    with pytest.raises(HTTPException) as exc:
        await logs(request, Response(), principal(log_grants=("payments-api",)))
    assert exc.value.status_code == 403
    assert exc.value.detail == "Service log access denied"


@pytest.mark.asyncio
async def test_log_search_accepts_only_exact_signed_service_grant(monkeypatch):
    monkeypatch.setattr(settings, "enable_opensearch", False)
    now = datetime.now(timezone.utc)
    request = LogSearchRequest(
        service_name="checkout-api",
        window={"start": now - timedelta(minutes=5), "end": now},
    )
    with pytest.raises(HTTPException) as exc:
        await logs(request, Response(), principal(log_grants=("checkout-api",)))
    # Exact grant passes authorization; disabled adapter then fails closed.
    assert exc.value.status_code == 503
    assert exc.value.detail == "OpenSearch adapter disabled"


@pytest.mark.asyncio
async def test_evidence_write_denies_ungranted_incident_before_database():
    req = EvidenceIn(
        investigation_id=uuid4(), source_type="logs",
        source_ref="opensearch://safe-ref", observed_at=datetime.now(timezone.utc),
    )
    with pytest.raises(HTTPException) as exc:
        await add_evidence("INC-OTHER-TENANT", req, principal(incident_grants=("INC-OWN",)), object())
    assert exc.value.status_code == 403
    assert exc.value.detail == "Incident evidence access denied"


@pytest.mark.asyncio
async def test_evidence_write_accepts_only_exact_incident_grant():
    req = EvidenceIn(
        investigation_id=uuid4(), source_type="logs",
        source_ref="opensearch://safe-ref", observed_at=datetime.now(timezone.utc),
    )
    # A matching grant passes the ACL check; an unusable DB object then fails.
    with pytest.raises(AttributeError):
        await add_evidence("INC-OWN", req, principal(incident_grants=("INC-OWN",)), object())
