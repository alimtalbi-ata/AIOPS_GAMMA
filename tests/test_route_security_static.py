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
    assert len(routes) >= 19, "Route inventory unexpectedly shrank: review the security guard"
    public = {("GET", "/api/v1/health/live")}
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
