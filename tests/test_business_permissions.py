from dataclasses import replace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from app.main import alerts, add_binding, list_bindings, add_evidence, list_evidence
from app.security import Principal, require_business_permission, BUSINESS_PERMISSIONS


def principal(*permissions):
    return Principal(uuid4(), "synthetic", "user", "synthetic-jti", 2000000000,
                     evidence_incident_grants=("INC-1",),
                     business_permissions=permissions)


@pytest.mark.parametrize("permission", sorted(BUSINESS_PERMISSIONS))
def test_exact_permission(permission):
    require_business_permission(principal(permission), permission)
    for other in BUSINESS_PERMISSIONS - {permission}:
        with pytest.raises(HTTPException) as exc:
            require_business_permission(principal(permission), other)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("handler,args", [
    (alerts, (None,)),
    (add_binding, (None,)),
    (list_bindings, ()),
    (add_evidence, ("INC-1", None)),
    (list_evidence, ("INC-1",)),
])
async def test_missing_permission_denied_before_business_db(handler, args):
    session = Mock()
    with pytest.raises(HTTPException) as exc:
        await handler(*args, principal(), session)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Business permission denied"
    assert session.mock_calls == []


@pytest.mark.asyncio
async def test_evidence_read_permission_does_not_allow_write():
    session = Mock()
    with pytest.raises(HTTPException) as exc:
        await add_evidence("INC-1", None, principal("evidence:read"), session)
    assert exc.value.status_code == 403
    assert session.mock_calls == []
