from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.outbox_claim import claim_statement


def test_claim_is_tenant_scoped_and_locks_one_pending_row():
    tenant = uuid4()
    compiled = claim_statement(tenant, datetime.now(timezone.utc)).compile(
        dialect=postgresql.dialect()
    )
    sql = str(compiled)
    assert "integration_outbox.tenant_id =" in sql
    assert tenant in compiled.params.values()
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "published_at IS NULL" in sql
    assert "next_attempt_at" in sql
    assert "LIMIT" in sql


@pytest.mark.parametrize("tenant", [None, "", UUID(int=0)])
def test_claim_rejects_missing_tenant(tenant):
    with pytest.raises(ValueError):
        claim_statement(tenant, datetime.now(timezone.utc))


def test_claim_requires_aware_clock():
    with pytest.raises(ValueError):
        claim_statement(uuid4(), datetime.now())
