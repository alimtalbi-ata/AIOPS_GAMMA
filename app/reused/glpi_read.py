"""Conservative GLPI read-only client. No session initialization or mutation.

Requires a pre-provisioned service session token and an infrastructure-enforced
egress allowlist. Tenant-to-GLPI-entity mapping is configured server-side.
"""
from __future__ import annotations

import json
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.reused.upstream import MAX_BYTES, validate_origin
from app.settings import settings


async def read_glpi_incident(tenant_id: UUID, ticket_id: int) -> dict:
    """Read an incident only after verifying a server-owned tenant/entity binding."""
    if type(ticket_id) is not int or ticket_id <= 0:
        raise HTTPException(422, "Invalid GLPI ticket id")
    if not settings.enable_glpi_reads:
        raise HTTPException(503, "GLPI reads disabled")
    # This is a deliberately single-tenant prototype. No browser-supplied entity
    # or token is ever accepted; additional tenants need an ACL-backed registry.
    if (not settings.glpi_tenant_id or str(tenant_id) != settings.glpi_tenant_id
            or not settings.glpi_entity_id or not settings.glpi_session_token
            or not settings.glpi_app_token or not settings.glpi_read_url):
        raise HTTPException(403, "GLPI tenant binding unavailable")
    try:
        origin = validate_origin(settings.glpi_read_url)
        entity = int(settings.glpi_entity_id)
        if entity < 0:
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(503, "GLPI configuration invalid") from exc
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=1.0),
            follow_redirects=False, trust_env=False, verify=True,
        ) as client:
            async with client.stream(
                "GET", f"{origin}/apirest.php/Ticket/{ticket_id}",
                headers={
                    "Session-Token": settings.glpi_session_token,
                    "App-Token": settings.glpi_app_token,
                    "Accept": "application/json",
                },
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(502, "GLPI upstream unavailable")
                if "application/json" not in response.headers.get("content-type", "").lower():
                    raise HTTPException(502, "GLPI response content type invalid")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise HTTPException(502, "GLPI response too large")
        payload = json.loads(raw)
        if (not isinstance(payload, dict) or type(payload.get("id")) is not int
                or payload["id"] != ticket_id
                or type(payload.get("entities_id")) is not int
                or payload["entities_id"] != entity
                or type(payload.get("type")) is not int or payload["type"] != 1
                or (payload.get("status") is not None and type(payload["status"]) is not int)):
            raise HTTPException(502, "GLPI ticket/entity attestation failed")
        # Explicit projection avoids leaking vendor custom fields or PII.
        return {
            "system": "glpi",
            "tenant_id": str(tenant_id),
            "ticket_id": ticket_id,
            "entity_id": entity,
            "status": payload.get("status") if type(payload.get("status")) is int else None,
            "type": 1,
            "read_only": True,
        }
    except (httpx.RequestError, httpx.DecodingError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(502, "GLPI upstream unavailable") from exc
