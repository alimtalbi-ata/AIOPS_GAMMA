"""Static HOLD guard: not a substitute for runtime tenant authorization tests.

Until Core/Gateway provides verified actor-to-tenant ACL and versioned read
contracts, canonical/OpenSearch reads must remain opt-in and disconnected.
"""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TenantIntegrationHoldGuard(unittest.TestCase):
    def test_sensitive_integrations_default_disabled(self):
        tree = ast.parse((ROOT / "app/settings.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Settings")
        defaults = {
            n.target.id: n.value.value
            for n in cls.body
            if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and isinstance(n.value, ast.Constant)
        }
        for name in ("enable_canonical_reads", "enable_opensearch", "enable_glpi_reads"):
            with self.subTest(setting=name):
                self.assertIs(defaults.get(name), False, f"{name} must default fail-closed")

    def test_unqualified_canonical_entrypoints_cannot_open_network_clients(self):
        """Static tripwire: unqualified read entrypoints stay network-free."""
        cases = (
            ("app/reused/upstream.py", "fetch_canonical"),
            ("app/reused/glpi_read.py", "read_glpi_incident"),
        )
        for relative, function_name in cases:
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            function = next(
                node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == function_name
            )
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
            called_names = []
            for call in calls:
                if isinstance(call.func, ast.Attribute):
                    called_names.append(call.func.attr)
                elif isinstance(call.func, ast.Name):
                    called_names.append(call.func.id)
            with self.subTest(entrypoint=function_name):
                self.assertNotIn("AsyncClient", called_names)
                self.assertNotIn("get", called_names)
                self.assertNotIn("post", called_names)
                self.assertNotIn("request", called_names)
                self.assertIn("HTTPException", called_names)
                self.assertTrue(
                    any(isinstance(node, ast.Raise) for node in ast.walk(function)),
                    "unqualified entrypoint must fail closed",
                )

    def test_provisional_upstream_paths_not_silently_mapped_to_global_core_routes(self):
        tree = ast.parse((ROOT / "app/reused/upstream.py").read_text(encoding="utf-8"))
        allowed = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "ALLOWED_RESOURCES"
                               for t in n.targets))
        routes = ast.literal_eval(allowed)
        self.assertEqual(set(routes), {"core", "evidence", "twin"})
        for resource, (_, path) in routes.items():
            with self.subTest(resource=resource):
                self.assertTrue(path.startswith("/api/v1/"), "unreviewed global route remap")
        self.assertEqual(routes["core"][1], "/api/v1/incidents")
        self.assertEqual(routes["evidence"][1], "/api/v1/evidence")
        self.assertEqual(routes["twin"][1], "/api/v1/topology")


if __name__ == "__main__":
    unittest.main()
