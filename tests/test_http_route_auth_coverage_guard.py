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
                    self.assertFalse(
                        decorator.keywords,
                        "Unreviewed middleware decorator options need explicit review",
                    )
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
                self.assertEqual(
                    len(decorator.args), 1,
                    "Unreviewed positional route decorator arguments",
                )
                route = (func.attr.upper(), decorator.args[0].value)
                # Two existing creation endpoints intentionally return 201.
                # All other decorator options require explicit security review.
                allowed_options = {
                    ("POST", "/api/v1/topology/bindings"): {"status_code": 201},
                    ("POST", "/api/v1/incidents/{incident_id}/evidence"): {"status_code": 201},
                }
                actual_options = {}
                for keyword in decorator.keywords:
                    self.assertIsNotNone(
                        keyword.arg,
                        "Unreviewed route decorator keyword unpacking",
                    )
                    self.assertIsInstance(
                        keyword.value, ast.Constant,
                        "Unreviewed route decorator nonliteral option",
                    )
                    self.assertNotIn(
                        keyword.arg, actual_options,
                        "Unreviewed duplicate route decorator option",
                    )
                    actual_options[keyword.arg] = keyword.value.value
                self.assertEqual(
                    actual_options, allowed_options.get(route, {}),
                    "Unreviewed route decorator options need explicit review",
                )
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
                    and not default.keywords
                    and isinstance(default.args[0], ast.Name)
                    and default.args[0].id == "internal_principal"
                    for default in (*node.args.defaults, *node.args.kw_defaults)
                    if default is not None
                )
                # Raise directly: subTest captures AssertionError instead of
                # propagating it to the mutation tests' assertRaisesRegex.
                self.assertTrue(
                    depends_on_principal,
                    f"{route[0]} {route[1]}: "
                    "Route missing internal service auth dependency; "
                    "this is not a substitute for actor→tenant ACL",
                )
        self.assertIn(("POST", "/api/v1/observability/metrics/query"), found)
        self.assertIn(("GET", "/api/v1/canonical/{resource}/snapshot"), found)
        self.assertEqual(found & PUBLIC_ROUTES, PUBLIC_ROUTES)
        self.assertEqual(found, EXPECTED_ROUTES,
                         "HTTP route inventory changed; review ACL and update allowlist")

    def test_duplicate_public_and_private_route_registrations_are_rejected(self):
        """A set inventory must not hide a second route with the same method/path."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        source = MAIN.read_text(encoding="utf-8")
        for decorator in (
            '@app.get("/api/v1/demo/correlation")',
            '@app.post("/api/v1/observability/logs/search")',
        ):
            self.assertEqual(source.count(decorator), 1)
            with TemporaryDirectory() as directory:
                candidate = Path(directory) / "main.py"
                candidate.write_text(
                    source.replace(decorator, decorator + "\n" + decorator, 1),
                    encoding="utf-8",
                )
                with patch.dict(
                    self.test_all_non_public_http_routes_require_internal_principal.__globals__,
                    {"MAIN": candidate},
                ):
                    with self.assertRaisesRegex(AssertionError, "Duplicate HTTP route"):
                        self.test_all_non_public_http_routes_require_internal_principal()

    def test_unreviewed_route_decorator_options_are_rejected(self):
        """Decorator options must not silently change auth or route semantics."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        source = MAIN.read_text(encoding="utf-8")
        original = '@app.post("/api/v1/observability/logs/search")'
        self.assertEqual(source.count(original), 1)
        for changed in (
            '@app.post("/api/v1/observability/logs/search", dependencies=[])',
            '@app.post("/api/v1/observability/logs/search", include_in_schema=False)',
            '@app.post("/api/v1/observability/logs/search", 123)',
        ):
            with TemporaryDirectory() as directory:
                candidate = Path(directory) / "main.py"
                candidate.write_text(
                    source.replace(original, changed, 1), encoding="utf-8"
                )
                with patch.dict(
                    self.test_all_non_public_http_routes_require_internal_principal.__globals__,
                    {"MAIN": candidate},
                ):
                    with self.assertRaisesRegex(
                        AssertionError, "Unreviewed .*route decorator"
                    ):
                        self.test_all_non_public_http_routes_require_internal_principal()

    def test_reviewed_creation_status_cannot_be_changed(self):
        """Even previously approved decorator options are exact contracts."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        source = MAIN.read_text(encoding="utf-8")
        original = '@app.post("/api/v1/topology/bindings", status_code=201)'
        self.assertEqual(source.count(original), 1)
        for changed in (
            '@app.post("/api/v1/topology/bindings", status_code=200)',
            '@app.post("/api/v1/topology/bindings")',
            '@app.post("/api/v1/topology/bindings", status_code=201, tags=["public"])',
        ):
            with TemporaryDirectory() as directory:
                candidate = Path(directory) / "main.py"
                candidate.write_text(source.replace(original, changed, 1), encoding="utf-8")
                with patch.dict(
                    self.test_all_non_public_http_routes_require_internal_principal.__globals__,
                    {"MAIN": candidate},
                ):
                    with self.assertRaisesRegex(AssertionError, "Unreviewed route decorator"):
                        self.test_all_non_public_http_routes_require_internal_principal()

    def test_internal_principal_dependency_options_require_review(self):
        """A modified Depends call must not pass this exact auth guard."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        source = MAIN.read_text(encoding="utf-8")
        original = "Depends(internal_principal)"
        self.assertIn(original, source)
        for changed in (
            "Depends(internal_principal, use_cache=False)",
            "Depends(internal_principal, scope='read')",
            "Depends(get_session)",
            "None",
        ):
            with TemporaryDirectory() as directory:
                candidate = Path(directory) / "main.py"
                candidate.write_text(
                    source.replace(original, changed, 1), encoding="utf-8"
                )
                with patch.dict(
                    self.test_all_non_public_http_routes_require_internal_principal.__globals__,
                    {"MAIN": candidate},
                ):
                    with self.assertRaisesRegex(
                        AssertionError, "Route missing internal service auth dependency"
                    ):
                        self.test_all_non_public_http_routes_require_internal_principal()

    def test_middleware_decorator_options_require_review(self):
        """Middleware registration changes must not bypass route guard review."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        source = MAIN.read_text(encoding="utf-8")
        original = '@app.middleware("http")'
        self.assertEqual(source.count(original), 1)
        for changed in (
            '@app.middleware("http", unexpected=True)',
            '@app.middleware("http", **{"unexpected": True})',
        ):
            with TemporaryDirectory() as directory:
                candidate = Path(directory) / "main.py"
                candidate.write_text(
                    source.replace(original, changed, 1), encoding="utf-8"
                )
                with patch.dict(
                    self.test_all_non_public_http_routes_require_internal_principal.__globals__,
                    {"MAIN": candidate},
                ):
                    with self.assertRaisesRegex(
                        AssertionError, "Unreviewed middleware decorator options"
                    ):
                        self.test_all_non_public_http_routes_require_internal_principal()

    def test_middleware_decorator_positional_mutations_require_review(self):
        """The reviewed HTTP middleware must not accept alternate registration forms."""
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        source = MAIN.read_text(encoding="utf-8")
        original = '@app.middleware("http")'
        self.assertEqual(source.count(original), 1)
        for changed in (
            '@app.middleware("websocket")',
            '@app.middleware("http", "unexpected")',
            '@app.middleware(*("http",))',
        ):
            with TemporaryDirectory() as directory:
                candidate = Path(directory) / "main.py"
                candidate.write_text(
                    source.replace(original, changed, 1), encoding="utf-8"
                )
                with patch.dict(
                    self.test_all_non_public_http_routes_require_internal_principal.__globals__,
                    {"MAIN": candidate},
                ):
                    with self.assertRaises(AssertionError):
                        self.test_all_non_public_http_routes_require_internal_principal()

    def test_public_route_allowlist_is_narrow(self):
        self.assertEqual(PUBLIC_ROUTES, {
            ("GET", "/api/v1/health/live"),
            ("GET", "/api/v1/demo/correlation"),
            ("GET", "/api/v1/demo/investigation"),
        })


if __name__ == "__main__":
    unittest.main()
