#!/usr/bin/env python3
"""No-VM, no-Docker GAMMA API smoke using the actual FastAPI ASGI application.

Does not connect to PostgreSQL, external IdP, OpenSearch, GLPI or production.
All tenant routes are tested in denied mode only.
"""
import sys
from fastapi.testclient import TestClient

from app.main import app
from app.settings import settings


def main() -> int:
    # Prevent accidentally using a developer's real gateway/service credentials.
    if settings.internal_api_key or settings.gateway_assertion_secret:
        print("FAIL: refusing smoke with configured gateway/service credentials", file=sys.stderr)
        return 2
    try:
        with TestClient(app) as client:
            live = client.get("/api/v1/health/live")
            assert live.status_code == 200 and live.json() == {"status": "ok"}
            print("PASS actual FastAPI health route")

            openapi = client.get("/openapi.json")
            assert openapi.status_code == 200
            paths = openapi.json()["paths"]
            assert "/api/v1/topology/bindings" in paths
            assert "/api/v1/incidents/{incident_id}/evidence" in paths
            print("PASS OpenAPI topology/evidence route registration")

            demo = client.get("/api/v1/demo/correlation")
            assert demo.status_code == 200
            payload = demo.json()
            assert payload["mode"] == "synthetic_demo"
            assert payload["authoritative"] is False
            assert payload["correlation"]["source_events"] == 2
            assert len(payload["correlation"]["groups"]) == 1
            assert payload["correlation"]["live_remediation_authorized"] is False
            print("PASS real correlation engine on 2 synthetic events → 1 group")

            investigation = client.get("/api/v1/demo/investigation")
            assert investigation.status_code == 200
            investigation_payload = investigation.json()
            assert investigation_payload["mode"] == "synthetic_demo"
            assert investigation_payload["authoritative"] is False
            joined = investigation_payload["investigation"]
            assert joined["evidence_join_complete"] is True
            assert joined["groups"][0]["evidence_state"] == "UNVERIFIED"
            assert joined["groups"][0]["evidence_covered_events"] == 2
            assert joined["live_remediation_authorized"] is False
            print("PASS real evidence join on 2 synthetic events (source UNVERIFIED)")

            denied = client.get("/api/v1/topology/bindings", headers={
                "X-Tenant-ID": "00000000-0000-0000-0000-000000000001",
            })
            assert denied.status_code in (401, 503)
            assert denied.headers["Cache-Control"] == "no-store"
            print("PASS forged tenant header denied without gateway credentials")
    except Exception as exc:
        print(f"FAIL no-VM API smoke: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("PASS no-VM API smoke; database and frontend runtime NOT validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
