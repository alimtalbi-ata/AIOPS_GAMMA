import hmac
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException

from app.settings import settings


@dataclass(frozen=True)
class Principal:
    tenant_id: UUID


def internal_principal(
    x_internal_api_key: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> Principal:
    # Only a trusted, separately authenticated gateway may set these headers.
    if not settings.internal_api_key:
        raise HTTPException(status_code=503, detail="Internal authentication not configured")
    if not x_internal_api_key or not hmac.compare_digest(
        x_internal_api_key, settings.internal_api_key
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        tenant = UUID(x_tenant_id or "")
        if tenant.int == 0:
            raise ValueError("Nil tenant UUID is not a tenant identity")
        if x_tenant_id != str(tenant):
            raise ValueError("Noncanonical tenant UUID")
        return Principal(tenant)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid tenant UUID") from exc
