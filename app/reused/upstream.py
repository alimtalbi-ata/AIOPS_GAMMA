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


def _unique_json_object(pairs):
    """Reject ambiguous duplicate keys in upstream security attestations."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate upstream JSON key")
        obj[key] = value
    return obj


def parse_unique_json(data):
    """Parse upstream JSON without duplicate keys or non-finite constants."""
    def reject_constant(value):
        raise ValueError("non-finite upstream JSON constant")

    return json.loads(data, object_pairs_hook=_unique_json_object,
                      parse_constant=reject_constant)
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
        # Force port parsing here: urlsplit accepts malformed port strings
        # until .port is accessed, which otherwise fails later in HTTPX.
        port = u.port
        if (u.scheme != "https" or not host or u.username or u.password
                or u.path not in ("", "/") or u.query or u.fragment
                or (port is not None and port <= 0)):
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
    """HOLD: no canonical reads until independently verified upstream ACL.

    A caller-supplied X-Tenant-Id and an echoed tenant_id are not proof of
    actor-to-tenant-to-resource authorization. Do not make a network request,
    even if the legacy feature flag is enabled by accident. Re-enable only
    with a separately reviewed identity, resource ACL and cross-tenant E2E
    contract for Core, Evidence and Twin.
    """
    if resource not in ALLOWED_RESOURCES:
        raise HTTPException(404, "Unknown upstream resource")
    raise HTTPException(503, "Canonical actor/tenant/resource ACL not qualified")
