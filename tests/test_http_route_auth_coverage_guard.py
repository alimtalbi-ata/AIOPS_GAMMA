"""Static route coverage guard; NOT a human actor→tenant ACL test.

Ensures new GAMMA API routes do not accidentally omit the existing internal
service-key dependency. This dependency is insufficient for human tenant ACL.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app/main.py"
PUBLIC_ROUTES = {("GET", "/api/v1/health/live")}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


class InternalRouteDependencyGuard(unittest.TestCase):
    def test_all_non_health_http_routes_require_internal_principal(self):
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
        found = set()
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                if not (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "app"
                        and func.attr in HTTP_METHODS
                        and decorator.args
                        and isinstance(decorator.args[0], ast.Constant)
                        and isinstance(decorator.args[0].value, str)):
                    continue
                route = (func.attr.upper(), decorator.args[0].value)
                found.add(route)
                if route in PUBLIC_ROUTES:
                    continue
                depends_on_principal = any(
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id == "Depends"
                    and len(default.args) == 1
                    and isinstance(default.args[0], ast.Name)
                    and default.args[0].id == "internal_principal"
                    for default in (*node.args.defaults, *node.args.kw_defaults)
                    if default is not None
                )
                with self.subTest(method=route[0], path=route[1]):
                    self.assertTrue(
                        depends_on_principal,
                        "Route missing internal service auth dependency; "
                        "this is not a substitute for actor→tenant ACL",
                    )
        self.assertIn(("POST", "/api/v1/observability/metrics/query"), found)
        self.assertIn(("GET", "/api/v1/canonical/{resource}/snapshot"), found)
        self.assertEqual(found & PUBLIC_ROUTES, PUBLIC_ROUTES)

    def test_public_route_allowlist_is_narrow(self):
        self.assertEqual(PUBLIC_ROUTES, {("GET", "/api/v1/health/live")})


if __name__ == "__main__":
    unittest.main()
