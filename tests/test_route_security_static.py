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
    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "Depends"
        and len(child.args) == 1
        and isinstance(child.args[0], ast.Name)
        and child.args[0].id == "internal_principal"
        for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
        for child in ast.walk(arg.annotation) if arg.annotation is not None
    ) or any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == "Depends"
        and len(child.args) == 1
        and isinstance(child.args[0], ast.Name)
        and child.args[0].id == "internal_principal"
        for default in (*node.args.defaults, *node.args.kw_defaults)
        if default is not None
        for child in ast.walk(default)
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
