"""Opt-in, read-only staging isolation check against a real OpenSearch cluster.

Requires pre-seeded, uniquely tagged fixture documents and an appropriately
restricted service account. Never creates/deletes indices or documents.
Run with GAMMA_OPENSEARCH_STAGING_TEST=1 and the variables below.
"""
import os
import re
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from app.opensearch_adapter import search_logs
from app.schemas import LogSearchRequest, TimeWindow
from app.settings import settings


@pytest.mark.asyncio
async def test_real_opensearch_tenant_and_service_isolation():
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

    tenants = []
    for key in required[:2]:
        raw = os.environ[key]
        parsed = UUID(raw)
        assert parsed.int != 0 and raw == str(parsed), (
            f"{key} must be a non-nil canonical UUID"
        )
        tenants.append(raw)
    assert tenants[0] != tenants[1], "Two distinct tenants are required"
    services = [os.environ[key] for key in required[2:4]]
    assert services[0] != services[1], "Two distinct services are required"
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", service) for service in services), (
        "Staging service names must match the fixture generator"
    )

    window = TimeWindow(
        start=datetime.fromisoformat(os.environ["GAMMA_STAGING_WINDOW_START"]),
        end=datetime.fromisoformat(os.environ["GAMMA_STAGING_WINDOW_END"]),
    )
    marker = os.environ["GAMMA_STAGING_FIXTURE_MARKER"]
    assert re.fullmatch(r"[A-Za-z0-9-]{8,128}", marker), (
        "Use the same safe fixture marker format as the generator"
    )
    assert window.end - window.start < timedelta(days=2), (
        "Window must be shorter than the fixture outside-window offset"
    )
    assert settings.enable_opensearch, "OpenSearch must be explicitly enabled"
    assert settings.opensearch_url.startswith("https://"), "Staging must use HTTPS"
    assert settings.opensearch_verify_certs, "Staging must verify TLS certificates"
    assert settings.opensearch_username, "Use a restricted authenticated service account"
    assert settings.opensearch_password, "Staging service account password required"
    assert re.fullmatch(r"staging-[a-z0-9][a-z0-9._-]{0,127}", settings.opensearch_logs_index), (
        "Use one explicit staging index; no wildcard, alias list or cross-index expression"
    )

    fixture_timestamp = None
    for tenant_index, tenant in enumerate(tenants):
        for service_index, service in enumerate(services):
            expected_fixture_id = f"{marker}-{1 + 2 * tenant_index + service_index}"
            request = LogSearchRequest(service_name=service, window=window, limit=500)
            result = await search_logs(tenant, request)
            hits = result["hits"]["hits"]
            assert len(hits) < request.limit, (
                "Staging query saturated the result limit; fixture coverage is inconclusive"
            )
            fixture_hits = [
                hit for hit in hits
                if hit.get("_source", {}).get("gamma_fixture_marker") == marker
            ]
            assert len(fixture_hits) == 1, (
                f"No marked fixtures for tenant={tenant}, service={service}; "
                "check seed data, mapping and test window"
            )
            for hit in fixture_hits:
                assert hit["_id"] == expected_fixture_id, "Unexpected fixture identity"
                source = hit["_source"]
                observed = datetime.fromisoformat(source["@timestamp"].replace("Z", "+00:00"))
                assert window.start <= observed <= window.end, "Fixture timestamp outside window"
                if fixture_timestamp is None:
                    fixture_timestamp = observed
                else:
                    assert observed == fixture_timestamp, "Fixture timestamps differ"
                assert source["tenant"]["id"] == tenant
                assert source["resource"]["attributes"]["service"]["name"] == service
                assert source["severityText"] == ("ERROR" if service == services[0] else "WARN")
            # Never accept any cross-tenant/service result, even without marker.
            for hit in hits:
                source = hit["_source"]
                assert source["tenant"]["id"] == tenant
                assert source["resource"]["attributes"]["service"]["name"] == service


    # Severity and time filters must exclude otherwise matching fixtures.
    for tenant in tenants:
        request = LogSearchRequest(
            service_name=services[0], window=window,
            severity=["WARN"], limit=500,
        )
        result = await search_logs(tenant, request)
        hits = result["hits"]["hits"]
        assert len(hits) < request.limit, "Severity query saturated; result is inconclusive"
        assert not any(
            hit.get("_source", {}).get("gamma_fixture_marker") == marker
            for hit in hits
        ), "Severity filter returned an ERROR fixture"

    # The fifth synthetic fixture is two days before the other four.
    # A query in the configured window must never return its known ID.
    for tenant in tenants:
        for service in services:
            request = LogSearchRequest(service_name=service, window=window, limit=500)
            result = await search_logs(tenant, request)
            hits = result["hits"]["hits"]
            assert len(hits) < request.limit, "Time query saturated; result is inconclusive"
            assert all(
                hit.get("_id") != f"{marker}-5"
                for hit in hits
            ), "Out-of-window fixture leaked into results"


    # Positive control: prove the out-of-window fixture actually exists.
    # Otherwise its absence from the in-window search is not meaningful.
    assert fixture_timestamp is not None
    outside_timestamp = fixture_timestamp - timedelta(days=2)
    outside_window = TimeWindow(
        start=outside_timestamp - timedelta(seconds=1),
        end=outside_timestamp + timedelta(seconds=1),
    )
    outside_request = LogSearchRequest(
        service_name=services[0], window=outside_window, limit=500,
    )
    outside_result = await search_logs(tenants[0], outside_request)
    outside_hits = outside_result["hits"]["hits"]
    assert len(outside_hits) < outside_request.limit, (
        "Outside-window control query saturated; result is inconclusive"
    )
    matching_outside = [
        hit for hit in outside_hits
        if hit.get("_id") == f"{marker}-5"
        and hit.get("_source", {}).get("gamma_fixture_marker") == marker
    ]
    assert len(matching_outside) == 1, (
        "Outside-window fixture missing: time-filter qualification is inconclusive"
    )
    assert matching_outside[0]["_source"]["tenant"]["id"] == tenants[0]
    assert matching_outside[0]["_source"]["resource"]["attributes"]["service"]["name"] == services[0]
