"""No-Docker contract checks for the explicitly synthetic frontend/API demo."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vite_dev_server_only_proxies_public_synthetic_demo():
    config = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert '"/api/v1/demo/correlation"' in config
    assert 'target: "http://127.0.0.1:8000"' in config
    assert 'host: "127.0.0.1"' in config
    assert '"/api/v1/"' not in config


def test_nginx_only_proxies_public_synthetic_demo():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "location = /api/v1/demo/correlation" in nginx
    assert "proxy_pass http://api:8000/api/v1/demo/correlation;" in nginx
    assert 'proxy_set_header X-Gateway-Principal "";' in nginx
    assert "location /api/v1/" not in nginx


def test_frontend_correlation_demo_uses_local_fixture_without_api_fetch():
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "const runSyntheticDemo=()=>{" in source
    assert 'setDemoGroups(1);' in source
    assert 'setDemoEvents(2);' in source
    assert 'LOCAL DEMO · Corrélation illustrative uniquement' in source
    assert 'fetch("/api/v1/demo/correlation"' not in source

def test_investigation_demo_uses_local_unverified_fixtures_without_api_fetch():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "const runInvestigationDemo=()=>{" in app
    assert 'external_id:"demo-payment-timeout-1"' in app
    assert 'external_id:"demo-payment-timeout-2"' in app
    assert 'state:"UNVERIFIED"' in app
    assert 'LOCAL DEMO · Jointure illustrative uniquement' in app
    assert 'fetch("/api/v1/demo/investigation"' not in app
    assert "Fixtures locales · non vérifiées" in app

def test_vite_dev_command_is_loopback_only():
    import json
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["dev"] == "vite --host 127.0.0.1"


def test_frontend_preview_command_is_loopback_only():
    import json
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["preview"] == "vite preview --host 127.0.0.1"


def test_compose_frontend_waits_for_api_before_nginx_upstream_resolution():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    frontend = compose.split("  frontend:", 1)[1].split("\n  api:", 1)[0]
    assert "depends_on:" in frontend
    assert "api:" in frontend
    assert "condition: service_healthy" in frontend


def test_api_healthcheck_uses_actual_liveness_without_tenant_credentials():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    api = compose.split("\n  api:", 1)[1].split("\n  migrate:", 1)[0]
    assert "healthcheck:" in api
    assert "/api/v1/health/live" in api
    assert "127.0.0.1:8000" in api
    assert "INTERNAL_API_KEY" not in api.split("healthcheck:", 1)[1]
    assert "condition: service_completed_successfully" in api


def test_nginx_rejects_non_demo_api_paths_before_spa_fallback():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "location ^~ /api/ {" in nginx
    api_block = nginx.split("location ^~ /api/ {", 1)[1].split("}", 1)[0]
    assert "return 404;" in api_block
    assert "proxy_pass" not in api_block
    assert nginx.index("location = /api/v1/demo/correlation") < nginx.index("location ^~ /api/")
    assert nginx.index("location = /api/v1/demo/investigation") < nginx.index("location ^~ /api/")
    assert nginx.index("location ^~ /api/") < nginx.index("location / { try_files")


def test_vite_rejects_unknown_api_routes_before_proxy():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert 'name: "deny-non-demo-api"' in vite
    assert 'path.startsWith("/api/") && !publicDemoPaths.has(path)' in vite
    assert "res.statusCode = 404;" in vite
    assert 'res.setHeader("Cache-Control", "no-store")' in vite
    assert '"/api/v1/demo/correlation"' in vite
    assert '"/api/v1/demo/investigation"' in vite


def test_investigation_local_fixture_cannot_claim_verified_or_live_evidence():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    handler = app.split("const runInvestigationDemo=()=>{", 1)[1].split("const [demoGroups", 1)[0]
    assert handler.count('state:"UNVERIFIED"') == 2
    assert 'source NON VÉRIFIÉE' in handler
    assert 'LOCAL DEMO · Jointure illustrative uniquement' in handler
    assert 'authoritative' not in handler
    assert 'persisted' not in handler
    assert 'live_remediation_authorized' not in handler

def test_local_demos_make_no_backend_request_or_live_claim():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert 'fetch("/api/v1/demo/correlation"' not in app
    assert 'fetch("/api/v1/demo/investigation"' not in app
    assert "Fixture locale · sans réseau" in app
    assert "LOCAL DEMO" in app

def test_correlation_local_fixture_is_fixed_and_non_authoritative():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    handler = app.split("const runSyntheticDemo=()=>{", 1)[1].split("const [query,setQuery]", 1)[0]
    assert 'setDemoGroups(1);' in handler
    assert 'setDemoEvents(2);' in handler
    assert 'LOCAL DEMO · Corrélation illustrative uniquement' in handler
    assert 'fetch(' not in handler

def test_nginx_demo_proxy_strips_browser_credentials_and_tenant_identity():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    for route in ("correlation", "investigation"):
        block = nginx.split(f"location = /api/v1/demo/{route} {{", 1)[1].split("}", 1)[0]
        for header in (
            "Authorization", "Cookie", "X-Tenant-ID", "X-Forwarded-User",
            "X-Internal-Api-Key", "X-Gateway-Principal",
        ):
            assert f'proxy_set_header {header} "";' in block


def test_vite_dev_demo_proxy_allowlists_only_non_identity_headers():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert "if (publicDemoPaths.has(path)) {" in vite
    assert 'const allowedHeaders = new Set(["host", "accept", "user-agent"]);' in vite
    assert "for (const header of Object.keys(req.headers)) {" in vite
    assert "if (!allowedHeaders.has(header)) {" in vite
    assert "delete req.headers[header];" in vite


def test_nginx_public_demo_upstream_is_bounded_and_unbuffered():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    for route in ("correlation", "investigation"):
        block = nginx.split(f"location = /api/v1/demo/{route} {{", 1)[1].split("}", 1)[0]
        for directive in (
            "proxy_connect_timeout 3s;",
            "proxy_send_timeout 8s;",
            "proxy_read_timeout 8s;",
            "proxy_buffering off;",
        ):
            assert directive in block


def test_nginx_demo_proxy_does_not_forward_arbitrary_browser_headers():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    for route in ("correlation", "investigation"):
        block = nginx.split(f"location = /api/v1/demo/{route} {{", 1)[1].split("}", 1)[0]
        assert "proxy_pass_request_headers off;" in block
        # Host is deliberately supplied by the proxy, not inherited from the browser.
        assert "proxy_set_header Host api;" in block


def test_nginx_demo_routes_are_get_only_and_drop_request_bodies():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    for route in ("correlation", "investigation"):
        block = nginx.split(f"location = /api/v1/demo/{route} {{", 1)[1]
        # The method guard is the last directive in the location; its nested
        # closing brace must not be confused with the location's closing brace.
        block = block.split("limit_except GET { deny all; }", 1)[0]
        assert "proxy_pass_request_body off;" in block
        assert 'proxy_set_header Content-Length "";' in block
        assert 'proxy_pass_request_headers off;' in block
        assert "limit_except GET { deny all; }" in nginx.split(
            f"location = /api/v1/demo/{route} {{", 1
        )[1].split("location ", 1)[0]


def test_vite_demo_proxy_rejects_mutating_methods_before_forwarding():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert 'if (req.method !== "GET" && req.method !== "HEAD") {' in vite
    assert "res.statusCode = 405;" in vite
    assert 'res.setHeader("Allow", "GET, HEAD");' in vite
    assert 'res.setHeader("Cache-Control", "no-store");' in vite
    assert 'res.end("Method not allowed");' in vite
    assert vite.index('if (req.method !== "GET"') < vite.index("const allowedHeaders")


def test_vite_demo_proxy_rejects_request_bodies_before_stripping_headers():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert 'req.headers["transfer-encoding"] !== undefined' in vite
    assert 'req.headers["content-length"] !== undefined' in vite
    assert 'req.headers["content-length"] !== "0"' in vite
    assert "res.statusCode = 400;" in vite
    assert 'res.end("Request body not allowed");' in vite
    assert vite.index('req.headers["transfer-encoding"]') < vite.index(
        "const allowedHeaders"
    )


def test_nginx_demo_responses_keep_security_headers_despite_add_header_inheritance():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    # Match the complete directives, not just header names: a weakened CSP or
    # missing "always" must fail the contract check.
    security_headers = tuple(
        line.strip()
        for line in nginx.split("location = /api/v1/demo/investigation", 1)[0].splitlines()
        if line.strip().startswith("add_header ")
    )
    assert len(security_headers) == 4
    for route in ("correlation", "investigation"):
        block = nginx.split(f"location = /api/v1/demo/{route} {{", 1)[1]
        block = block.split("limit_except GET { deny all; }", 1)[0]
        directives = [line.strip() for line in block.splitlines()]
        assert directives.count('add_header Cache-Control "no-store" always;') == 1
        for directive in security_headers:
            assert directives.count(directive) == 1
