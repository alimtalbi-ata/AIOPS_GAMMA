"""Static fail-closed guard for GAMMA's FastAPI route declarations.

This test deliberately uses only Python's AST: no database driver, tenant data,
network access, or application imports are required.
"""
import ast
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _routes():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            fn = decorator.func
            if not isinstance(fn, ast.Attribute) or not isinstance(fn.value, ast.Name):
                continue
            if fn.value.id != "app" or fn.attr not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            yield fn.attr.upper(), decorator.args[0].value, node


def _uses_internal_principal(node):
    """Require a real FastAPI dependency, not a nested/inert AST occurrence."""
    def is_dependency(value):
        return (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Depends"
            and len(value.args) == 1
            and not value.keywords
            and isinstance(value.args[0], ast.Name)
            and value.args[0].id == "internal_principal"
        )

    def is_annotated_dependency(annotation):
        return (
            isinstance(annotation, ast.Subscript)
            and isinstance(annotation.value, ast.Name)
            and annotation.value.id == "Annotated"
            and isinstance(annotation.slice, ast.Tuple)
            and any(is_dependency(item) for item in annotation.slice.elts[1:])
        )

    args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
    defaults = (
        [None] * (len(node.args.posonlyargs) + len(node.args.args) - len(node.args.defaults))
        + list(node.args.defaults)
        + list(node.args.kw_defaults)
    )
    return any(
        is_dependency(default) or is_annotated_dependency(arg.annotation)
        for arg, default in zip(args, defaults)
    )


def test_every_tenant_route_has_gateway_principal_dependency():
    routes = list(_routes())
    expected = {
        ("GET", "/api/v1/health/live"),
        ("GET", "/api/v1/demo/correlation"),
        ("GET", "/api/v1/demo/investigation"),
        ("POST", "/api/v1/observability/logs/search"),
        ("POST", "/api/v1/observability/metrics/query"),
        ("POST", "/api/v1/integrations/opensearch/alerts"),
        ("POST", "/api/v1/topology/bindings"),
        ("GET", "/api/v1/topology/bindings"),
        ("POST", "/api/v1/incidents/{incident_id}/evidence"),
        ("GET", "/api/v1/incidents/{incident_id}/evidence"),
        ("POST", "/api/v1/topology/impact/estimate"),
        ("POST", "/api/v1/policy/remediation/preview"),
        ("POST", "/api/v1/incidents/correlation/preview"),
        ("GET", "/api/v1/canonical/{resource}/snapshot"),
        ("POST", "/api/v1/itil4/workflow/preview"),
        ("POST", "/api/v1/itil4/incidents/sync-preview"),
        ("GET", "/api/v1/itil4/glpi/incidents/{ticket_id}/snapshot"),
        ("POST", "/api/v1/observability/llm/kpis/preview"),
        ("POST", "/api/v1/incidents/investigation/preview"),
        ("POST", "/api/v1/incidents/evidence/preview"),
        ("POST", "/api/v1/incidents/correlation-evidence/preview"),
    }
    actual = [(method, path) for method, path, _ in routes]
    assert len(actual) == len(set(actual)), "Duplicate method/path route registration"
    assert set(actual) == expected, "Route inventory changed: review the security guard"
    public = {
        ("GET", "/api/v1/health/live"),
        ("GET", "/api/v1/demo/correlation"),
        ("GET", "/api/v1/demo/investigation"),
    }
    assert {(method, path) for method, path, _ in routes if (method, path) in public} == public
    for method, path, node in routes:
        if (method, path) in public:
            continue
        assert path.startswith("/api/v1/"), (method, path)
        assert _uses_internal_principal(node), f"Unprotected route: {method} {path}"


def test_tenant_api_cache_middleware_is_present():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
    middleware = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "prevent_tenant_api_caching"
    ]
    assert len(middleware) == 1
    source = ast.get_source_segment(MAIN.read_text(encoding="utf-8"), middleware[0])
    assert '"/api/v1/"' in source
    assert '"Cache-Control"' in source
    assert '"no-store"' in source

def test_public_demo_routes_only_call_reviewed_synthetic_helpers():
    """Public demos must not gain database, network or tenant-data access."""
    expected_helpers = {
        "/api/v1/demo/correlation": "synthetic_correlation_demo",
        "/api/v1/demo/investigation": "synthetic_investigation_demo",
    }
    for method, path, node in _routes():
        if path not in expected_helpers:
            continue
        assert method == "GET"
        helper = expected_helpers[path]
        assert len(node.body) == 3, f"Public demo body changed: {path}"
        assert isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
        imported = node.body[1]
        assert isinstance(imported, ast.ImportFrom) and imported.module == "app.demo"
        assert len(imported.names) == 1 and imported.names[0].name == helper
        result = node.body[2]
        assert isinstance(result, ast.Return)
        assert isinstance(result.value, ast.Call)
        assert isinstance(result.value.func, ast.Name)
        assert result.value.func.id == helper
        assert not result.value.args and not result.value.keywords
        assert not any(isinstance(child, ast.Await) for child in ast.walk(node))

def _assert_no_unreviewed_route_registration(source):
    """Prevent bypassing the explicit @app route inventory."""
    tree = ast.parse(source)
    forbidden_calls = {"include_router", "add_api_route", "add_route", "mount", "api_route", "websocket", "websocket_route", "route"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "app"
                    and decorator.func.attr in {"get", "post", "put", "patch", "delete"}):
                    assert (len(decorator.args) == 1
                            and isinstance(decorator.args[0], ast.Constant)
                            and isinstance(decorator.args[0].value, str)
                            and decorator.args[0].value.startswith("/api/v1/")
                            and not any(keyword.arg == "path" for keyword in decorator.keywords)), (
                        "Unreviewed route declaration form"
                    )
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in forbidden_calls:
                raise AssertionError(f"Unreviewed dynamic route registration: {func.attr}")
            if isinstance(func, ast.Name) and func.id in {"APIRouter", "add_api_route"}:
                raise AssertionError(f"Unreviewed router registration: {func.id}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"get", "post", "put", "patch", "delete"}
                    and not (isinstance(decorator.func.value, ast.Name)
                             and decorator.func.value.id == "app")):
                    raise AssertionError("Unreviewed router decorator")


def test_no_alternate_route_registration_bypasses_inventory():
    _assert_no_unreviewed_route_registration(MAIN.read_text(encoding="utf-8"))


def test_alternate_route_registration_mutations_are_rejected():
    import pytest

    mutations = (
        'app.include_router(router)',
        'app.add_api_route("/api/v1/unsafe", handler)',
        'app.router.add_api_route("/api/v1/unsafe", handler)',
        'app.mount("/unsafe", subapp)',
        '@app.api_route("/api/v1/unsafe")\ndef handler():\n    return {}',
        '@app.websocket("/ws")\ndef handler():\n    return {}',
        'router = APIRouter()',
        '@app.get(path="/api/v1/unsafe")\ndef handler():\n    return {}',
        '@app.get("/api/v1/unsafe", path="/api/v1/health/live")\ndef handler():\n    return {}',
        '@router.get("/api/v1/unsafe")\ndef handler():\n    return {}',
    )
    for mutation in mutations:
        with pytest.raises(AssertionError):
            _assert_no_unreviewed_route_registration(mutation)

def test_gateway_dependency_shape_mutations():
    import pytest

    cases = (
        ("async def route(p=Depends(internal_principal)): pass", True),
        ("async def route(p: Annotated[Principal, Depends(internal_principal)]): pass", True),
        ("async def route(p=(Depends(internal_principal), None)[1]): pass", False),
        ("async def route(p: tuple[Depends(internal_principal), str]): pass", False),
        ("async def route(p=Depends(internal_principal, use_cache=False)): pass", False),
        ("async def route(p=None): pass", False),
    )
    for source, expected in cases:
        node = ast.parse(source).body[0]
        assert _uses_internal_principal(node) is expected, source

def _assert_exact_cache_middleware(source):
    """Fail closed if the tenant cache-control middleware changes semantics."""
    expected = '''
@app.middleware("http")
async def prevent_tenant_api_caching(request, call_next):
    """Apply no-store to tenant API responses, including rejected requests."""
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/") and request.url.path != "/api/v1/health/live":
        response.headers["Cache-Control"] = "no-store"
    return response
'''
    tree = ast.parse(source)
    found = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "prevent_tenant_api_caching"
    ]
    assert len(found) == 1, "Missing or duplicate tenant cache middleware"
    assert ast.dump(found[0], include_attributes=False) == ast.dump(
        ast.parse(expected).body[0], include_attributes=False
    ), "Tenant cache middleware semantics changed: explicit review required"


def test_tenant_cache_middleware_exact_semantics():
    _assert_exact_cache_middleware(MAIN.read_text(encoding="utf-8"))


def test_tenant_cache_middleware_mutations_rejected():
    import pytest

    source = '''
@app.middleware("http")
async def prevent_tenant_api_caching(request, call_next):
    """Apply no-store to tenant API responses, including rejected requests."""
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/") and request.url.path != "/api/v1/health/live":
        response.headers["Cache-Control"] = "no-store"
    return response
'''
    _assert_exact_cache_middleware(source)
    for mutated in (
        source.replace('response.headers["Cache-Control"] = "no-store"', 'unused = ("Cache-Control", "no-store")'),
        source.replace('response = await call_next(request)', 'response = None'),
        source.replace('and request.url.path != "/api/v1/health/live"', 'and False'),
        source.replace('return response', 'return None'),
    ):
        with pytest.raises(AssertionError):
            _assert_exact_cache_middleware(mutated)


def test_gateway_assertion_helm_wiring_is_optional_and_fail_closed():
    """Chart may mount an owner-provisioned HMAC secret, never embed key material."""
    root = Path(__file__).resolve().parents[1]
    values = (root / "deploy/helm/gamma/values.yaml").read_text(encoding="utf-8")
    api = (root / "deploy/helm/gamma/templates/api.yaml").read_text(encoding="utf-8")
    security = (root / "app/security.py").read_text(encoding="utf-8")

    for setting in (
        "gatewayAssertionSecret:",
        "gatewayAssertionSecretKey:",
        "gatewayAssertionIssuer:",
        "gatewayAssertionAudience:",
        "gatewayAssertionMaxTtlSeconds:",
    ):
        assert setting in values, f"Missing Helm setting: {setting}"

    assert 'if .Values.api.gatewayAssertionSecret' in api
    assert "name: GATEWAY_ASSERTION_SECRET" in api
    assert ".Values.api.gatewayAssertionSecretKey" in api
    assert "name: GATEWAY_ASSERTION_ISSUER" in api
    assert "name: GATEWAY_ASSERTION_AUDIENCE" in api
    assert "name: GATEWAY_ASSERTION_MAX_TTL_SECONDS" in api
    assert 'gatewayAssertionSecret: ""' in values, "HMAC Secret must remain unconfigured by default"
    assert 'settings.gateway_assertion_secret' in security
    assert 'Gateway assertion verification not configured' in security


def test_api_network_policy_denies_ingress_until_gateway_peer_selectors_exist():
    """API ingress is deny-all by default and gateway-only when selectors are set."""
    root = Path(__file__).resolve().parents[1]
    values = (root / "deploy/helm/gamma/values.yaml").read_text(encoding="utf-8")
    policy = (root / "deploy/helm/gamma/templates/networkpolicy.yaml").read_text(
        encoding="utf-8"
    )
    assert "gatewayNamespaceLabels: {}" in values
    assert "gatewayPodLabels: {}" in values
    assert "and (gt (len .Values.api.gatewayNamespaceLabels) 0)" in policy
    assert "(gt (len .Values.api.gatewayPodLabels) 0)" in policy
    assert "namespaceSelector:" in policy
    assert "podSelector:" in policy
    assert "ingress: []" in policy
    assert "deny all API ingress until the gateway" in policy
