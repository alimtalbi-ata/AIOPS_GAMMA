"""Static route coverage guard; NOT a human actor→tenant ACL test.

Ensures new GAMMA API routes do not accidentally omit the existing internal
service-key dependency. This dependency is insufficient for human tenant ACL.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app/main.py"
# Only these routes are intentionally unauthenticated. Independent AST
# guards constrain public demo handlers to reviewed synthetic helpers.
PUBLIC_ROUTES = {
    ("GET", "/api/v1/health/live"),
    ("GET", "/api/v1/demo/correlation"),
    ("GET", "/api/v1/demo/investigation"),
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
EXPECTED_ROUTES = {
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



class InternalRouteDependencyGuard(unittest.TestCase):
    def test_all_non_public_http_routes_require_internal_principal(self):
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
                        and func.value.id == "app"):
                    continue
                # Middleware is not an HTTP endpoint; review other decorators.
                if func.attr == "middleware":
                    self.assertEqual(len(decorator.args), 1)
                    self.assertIsInstance(decorator.args[0], ast.Constant)
                    self.assertEqual(decorator.args[0].value, "http")
                    continue
                # Fail closed if a new app route uses a registration form this
                # guard does not understand; otherwise it could be skipped.
                self.assertIn(func.attr, HTTP_METHODS,
                              "Unreviewed app decorator; update auth guard")
                self.assertTrue(decorator.args,
                                "Route must have a literal path")
                self.assertIsInstance(decorator.args[0], ast.Constant,
                                      "Dynamic route path needs review")
                self.assertIsInstance(decorator.args[0].value, str,
                                      "Route path must be a literal string")
                route = (func.attr.upper(), decorator.args[0].value)
                self.assertNotIn(
                    route, found,
                    "Duplicate HTTP route registration can shadow an authenticated handler",
                )
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
        self.assertEqual(found, EXPECTED_ROUTES,
                         "HTTP route inventory changed; review ACL and update allowlist")

    def test_public_route_allowlist_is_narrow(self):
        self.assertEqual(PUBLIC_ROUTES, {
            ("GET", "/api/v1/health/live"),
            ("GET", "/api/v1/demo/correlation"),
            ("GET", "/api/v1/demo/investigation"),
        })


if __name__ == "__main__":
    unittest.main()
