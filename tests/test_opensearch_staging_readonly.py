"""Opt-in, read-only staging isolation check against a real OpenSearch cluster.

Requires pre-seeded, uniquely tagged fixture documents and an appropriately
restricted service account. Never creates/deletes indices or documents.
Run with GAMMA_OPENSEARCH_STAGING_TEST=1 and the variables below.
"""
import os
from datetime import datetime
from uuid import UUID

import pytest

from app.opensearch_adapter import search_logs
from app.schemas import LogSearchRequest, TimeWindow
from app.settings import settings


@pytest.mark.asyncio
async def test_real_opensearch_tenant_and_service_isolation(monkeypatch):
    if os.getenv("GAMMA_OPENSEARCH_STAGING_TEST") != "1":
        pytest.skip("Explicit staging opt-in required")

    required = (
        "GAMMA_STAGING_TENANT_A",
        "GAMMA_STAGING_TENANT_B",
        "GAMMA_STAGING_SERVICE_A",
        "GAMMA_STAGING_SERVICE_B",
        "GAMMA_STAGING_WINDOW_START",
        "GAMMA_STAGING_WINDOW_END",
        "GAMMA_STAGING_FIXTURE_MARKER",
    )
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        pytest.fail("Missing staging configuration: " + ", ".join(missing))

    tenants = [str(UUID(os.environ[key])) for key in required[:2]]
    assert tenants[0] != tenants[1], "Two distinct tenants are required"
    services = [os.environ[key] for key in required[2:4]]
    assert services[0] != services[1], "Two distinct services are required"

    window = TimeWindow(
        start=datetime.fromisoformat(os.environ["GAMMA_STAGING_WINDOW_START"]),
        end=datetime.fromisoformat(os.environ["GAMMA_STAGING_WINDOW_END"]),
    )
    marker = os.environ["GAMMA_STAGING_FIXTURE_MARKER"]
    assert len(marker) >= 8, "Use a unique fixture marker"
    assert settings.enable_opensearch, "OpenSearch must be explicitly enabled"
    assert settings.opensearch_url.startswith("https://"), "Staging must use HTTPS"
    assert settings.opensearch_verify_certs, "Staging must verify TLS certificates"
    assert settings.opensearch_username, "Use a restricted authenticated service account"

    for tenant in tenants:
        for service in services:
            request = LogSearchRequest(service_name=service, window=window, limit=500)
            result = await search_logs(tenant, request)
            hits = result["hits"]["hits"]
            fixture_hits = [
                hit["_source"] for hit in hits
                if marker in str(hit.get("_source", {}))
            ]
            assert fixture_hits, (
                f"No marked fixtures for tenant={tenant}, service={service}; "
                "check seed data, mapping and test window"
            )
            for source in fixture_hits:
                assert source["tenant"]["id"] == tenant
                assert source["resource"]["attributes"]["service"]["name"] == service
            # Never accept any cross-tenant/service result, even without marker.
            for hit in hits:
                source = hit["_source"]
                assert source["tenant"]["id"] == tenant
                assert source["resource"]["attributes"]["service"]["name"] == service
