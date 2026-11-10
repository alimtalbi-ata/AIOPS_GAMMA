"""Offline tests for PostgreSQL configured UID preflight."""
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).with_name("check-postgres-rootless.py")
spec = importlib.util.spec_from_file_location("pg_rootless_preflight", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PostgresRootlessPreflightTests(unittest.TestCase):
    def test_current_upstream_configuration_refused(self):
        self.assertIsNotNone(module.check({"postgres": {"image": "postgres:16-alpine"}}))

    def test_root_uid_variants_refused(self):
        for user in ("0", "00:1000", "000:000"):
            with self.subTest(user=user):
                self.assertIsNotNone(module.check({"postgres": {"user": user}}))

    def test_named_or_malformed_user_refused(self):
        for user in ("postgres", "10001:", "10001:postgres", "10001:2:3"):
            with self.subTest(user=user):
                self.assertIsNotNone(module.check({"postgres": {"user": user}}))

    def test_numeric_nonroot_accepted_statically(self):
        for user in ("70", "10001:10001", "08:08"):
            with self.subTest(user=user):
                self.assertIsNone(module.check({"postgres": {"user": user, "cap_drop": ["ALL"], "cap_add": []}}))

    def test_inherited_capability_additions_refused(self):
        pg = {"user": "10001:10001", "cap_drop": ["ALL"], "cap_add": ["CHOWN", "SETUID"]}
        self.assertIn("cap_add", module.check({"postgres": pg}))

    def test_malformed_cap_add_refused(self):
        for value in (None, False, "", {}, "CHOWN", ["CHOWN"]):
            with self.subTest(value=value):
                pg = {"user": "10001:10001", "cap_drop": ["ALL"], "cap_add": value}
                self.assertIn("cap_add", module.check({"postgres": pg}))

    def test_missing_drop_all_refused(self):
        for value in (None, [], ["NET_RAW"]):
            with self.subTest(value=value):
                pg = {"user": "10001:10001", "cap_add": []}
                if value is not None:
                    pg["cap_drop"] = value
                self.assertIn("drop ALL", module.check({"postgres": pg}))

    def test_malformed_services_mapping_refused(self):
        for services in (None, [], "postgres", 7):
            with self.subTest(services=services):
                self.assertIn("mapping", module.check(services))

    def test_missing_service_refused(self):
        self.assertIsNotNone(module.check({}))


class PostgresRootlessCliTests(unittest.TestCase):
    def run_cli(self, payload):
        import subprocess
        import sys
        return subprocess.run([sys.executable, str(SCRIPT)], input=payload,
                              text=True, capture_output=True, timeout=10)

    def test_valid_effective_compose_document_passes(self):
        result = self.run_cli('{"services":{"postgres":{"user":"10001:10001","cap_drop":["ALL"],"cap_add":[]}}}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("runtime unverified", result.stdout)

    def test_root_config_fails_with_code_two(self):
        result = self.run_cli('{"services":{"postgres":{"user":"0","cap_drop":["ALL"]}}}')
        self.assertEqual(result.returncode, 2)
        self.assertIn("REFUSED", result.stderr)

    def test_invalid_json_fails_with_code_two(self):
        result = self.run_cli('{invalid')
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid Compose configuration", result.stderr)

    def test_malformed_services_fails_without_traceback(self):
        result = self.run_cli('{"services":[]}')
        self.assertEqual(result.returncode, 2)
        self.assertIn("mapping", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
