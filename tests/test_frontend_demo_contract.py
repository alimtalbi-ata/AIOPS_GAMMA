"""No-Docker contract checks for the isolated synthetic frontend demo."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_correlation_demo_uses_local_fixture_without_api_fetch():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "const runSyntheticDemo=()=>{" in app
    assert "setDemoGroups(1);" in app
    assert "setDemoEvents(2);" in app
    assert "LOCAL DEMO · Corrélation illustrative uniquement" in app
    assert 'fetch("/api/v1/demo/correlation"' not in app


def test_investigation_demo_uses_local_unverified_fixtures_without_api_fetch():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "const runInvestigationDemo=()=>{" in app
    assert 'external_id:"demo-payment-timeout-1"' in app
    assert 'external_id:"demo-payment-timeout-2"' in app
    assert 'state:"UNVERIFIED"' in app
    assert "LOCAL DEMO · Jointure illustrative uniquement" in app
    assert 'fetch("/api/v1/demo/investigation"' not in app
    assert "Fixtures locales · non vérifiées" in app


def test_local_demo_fixtures_make_no_backend_request_or_live_claim():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert 'fetch("/api/v1/demo/correlation"' not in app
    assert 'fetch("/api/v1/demo/investigation"' not in app
    assert "Fixture locale · sans réseau" in app
    assert "LOCAL DEMO" in app


def test_investigation_local_fixture_cannot_claim_verified_or_live_evidence():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    handler = app.split("const runInvestigationDemo=()=>{", 1)[1].split("const [demoGroups", 1)[0]
    assert handler.count('state:"UNVERIFIED"') == 2
    assert "source NON VÉRIFIÉE" in handler
    assert "LOCAL DEMO · Jointure illustrative uniquement" in handler
    assert "authoritative" not in handler
    assert "persisted" not in handler
    assert "live_remediation_authorized" not in handler


def test_correlation_local_fixture_is_fixed_and_non_authoritative():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    handler = app.split("const runSyntheticDemo=()=>{", 1)[1].split("const [query,setQuery]", 1)[0]
    assert "setDemoGroups(1);" in handler
    assert "setDemoEvents(2);" in handler
    assert "LOCAL DEMO · Corrélation illustrative uniquement" in handler
    assert "fetch(" not in handler


def test_nginx_denies_all_api_paths_before_spa_fallback():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert 'location = /api {' in nginx
    assert 'location ^~ /api/ {' in nginx
    assert nginx.count("return 404;") == 2
    assert "proxy_pass" not in nginx
    assert nginx.index("location ^~ /api/") < nginx.index("location / { try_files")
    assert 'add_header Cache-Control "no-store" always;' in nginx


def test_vite_dev_server_denies_all_api_paths_without_proxy():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert 'name: "deny-all-api"' in vite
    assert 'if (path === "/api" || path.startsWith("/api/")) {' in vite
    assert "res.statusCode = 404;" in vite
    assert 'res.setHeader("Cache-Control", "no-store")' in vite
    assert "proxy:" not in vite
    assert "127.0.0.1:8000" not in vite


def test_frontend_dev_and_preview_bind_to_loopback_only():
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["dev"] == "vite --host 127.0.0.1"
    assert package["scripts"]["preview"] == "vite preview --host 127.0.0.1"


def test_compose_frontend_has_no_api_dependency():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    frontend = compose.split("  frontend:", 1)[1].split("\n  api:", 1)[0]
    assert "depends_on:" not in frontend
    assert "build: ./frontend" in frontend


def test_api_healthcheck_uses_actual_liveness_without_tenant_credentials():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    api = compose.split("\n  api:", 1)[1].split("\n  migrate:", 1)[0]
    assert "healthcheck:" in api
    assert "/api/v1/health/live" in api
    assert "127.0.0.1:8000" in api
    assert "INTERNAL_API_KEY" not in api.split("healthcheck:", 1)[1]
    assert "condition: service_completed_successfully" in api


def test_nginx_denied_api_responses_retain_security_headers():
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    security_headers = (
        "add_header X-Content-Type-Options nosniff always;",
        "add_header Referrer-Policy no-referrer always;",
        "add_header X-Frame-Options DENY always;",
        "add_header Content-Security-Policy ",
        'add_header Cache-Control "no-store" always;',
    )
    for location in ('location = /api {', 'location ^~ /api/ {'):
        block = nginx.split(location, 1)[1].split("}", 1)[0]
        for header in security_headers:
            assert header in block


def test_vite_preview_denies_api_namespace_using_same_middleware_as_dev():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert 'configureServer(server) {' in vite
    assert 'configurePreviewServer(server) {' in vite
    assert vite.count("server.middlewares.use(denyApi);") == 2
    assert 'if (path === "/api" || path.startsWith("/api/")) {' in vite
    assert 'res.statusCode = 404;' in vite
    assert 'res.setHeader("Cache-Control", "no-store")' in vite
    assert 'preview: { host: "127.0.0.1" }' in vite


def test_frontend_ci_smokes_preview_api_denial_over_real_http():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "Smoke Vite preview API denial and SPA availability" in workflow
    assert "spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview'" in workflow
    assert "expected 404, got " in workflow
    assert "missing no-store" in workflow
    assert "['GET', 'POST']" in workflow
    assert "'/api/v1/demo/correlation'" in workflow
    assert "'/api/v1/demo/investigation'" in workflow


def test_ui_image_smoke_does_not_require_api_dns_or_proxy():
    workflow = (ROOT / ".github/workflows/deployment-contract.yml").read_text(encoding="utf-8")
    ui_image = workflow.split("  ui-image:", 1)[1].split("\n  api-postgres-runtime:", 1)[0]
    assert "--add-host api:127.0.0.1" not in ui_image
    assert "The static UI has no API upstream" in ui_image
    assert 'test "$status" = 404' in ui_image


def test_frontend_app_has_no_network_fetch_or_api_route_dependency():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "fetch(" not in app
    assert "/api/" not in app
    assert "XMLHttpRequest" not in app
    assert "WebSocket(" not in app


def test_ci_preview_smoke_owns_and_terminates_vite_process():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    smoke = workflow.split("Smoke Vite preview API denial and SPA availability", 1)[1].split(
        "\n  gateway-replay-postgres:", 1
    )[0]
    assert "spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview'" in smoke
    assert "server.kill('SIGTERM')" in smoke
    assert "server.kill('SIGKILL')" in smoke
    assert "spawn('npm'" not in smoke
