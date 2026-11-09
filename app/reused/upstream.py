"""Fail-closed, read-only adapter to canonical AIOps services.

Not a tenant identity provider: only use behind an authenticated gateway.
No arbitrary URLs, redirects, mutating methods or browser-provided upstream paths.
"""
from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.settings import settings

MAX_BYTES = 262144
ALLOWED_RESOURCES = {
    "core": ("core_read_url", "/api/v1/incidents"),
    "evidence": ("evidence_read_url", "/api/v1/evidence"),
    "twin": ("twin_read_url", "/api/v1/topology"),
}


def validate_origin(origin: str) -> str:
    """Accept a fixed HTTPS origin only, without path/query/credentials."""
    try:
        u = urlsplit(origin)
        host = u.hostname or ""
        if (u.scheme != "https" or not host or u.username or u.password
                or u.path not in ("", "/") or u.query or u.fragment):
            raise ValueError("Invalid HTTPS upstream origin")
        # Literal loopback/private IPs still need HTTPS. DNS egress allowlisting
        # must be enforced by infrastructure, not inferred from this check.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if host.endswith(".") or host.lower() == "localhost":
                raise ValueError("Invalid upstream hostname")
        return origin.rstrip("/")
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid HTTPS upstream origin") from exc


async def fetch_canonical(resource: str, tenant_id: UUID) -> dict:
    if resource not in ALLOWED_RESOURCES:
        raise HTTPException(404, "Unknown upstream resource")
    setting_name, path = ALLOWED_RESOURCES[resource]
    origin = getattr(settings, setting_name)
    if not settings.enable_canonical_reads or not origin or not settings.canonical_read_token:
        raise HTTPException(503, "Canonical read adapter disabled")
    try:
        base = validate_origin(origin)
    except ValueError as exc:
        raise HTTPException(503, "Canonical upstream configuration invalid") from exc
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(3.0, connect=1.0),
            follow_redirects=False,
            trust_env=False,
            verify=True,
        ) as client:
            async with client.stream(
                "GET", base + path,
                headers={
                    "Authorization": "Bearer " + settings.canonical_read_token,
                    "X-Tenant-Id": str(tenant_id),
                    "Accept": "application/json",
                },
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(502, "Canonical upstream unavailable")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise HTTPException(502, "Canonical upstream response too large")
                if "application/json" not in response.headers.get("content-type", "").lower():
                    raise HTTPException(502, "Canonical upstream content type invalid")
        decoded = json.loads(data)
        if not isinstance(decoded, dict):
            raise HTTPException(502, "Canonical upstream response shape invalid")
        # Do not assert authorization merely because upstream echoed a tenant.
        # A production integration must validate the upstream tenant ACL contract.
        if decoded.get("tenant_id") != str(tenant_id):
            raise HTTPException(502, "Canonical upstream tenant attestation missing")
        return decoded
    except (httpx.RequestError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(502, "Canonical upstream unavailable") from exc
