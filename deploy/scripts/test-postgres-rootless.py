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
        self.assertIn("capabilities", module.check({"postgres": pg}))

    def test_missing_drop_all_refused(self):
        for value in (None, [], ["NET_RAW"]):
            with self.subTest(value=value):
                pg = {"user": "10001:10001", "cap_add": []}
                if value is not None:
                    pg["cap_drop"] = value
                self.assertIn("drop ALL", module.check({"postgres": pg}))

    def test_missing_service_refused(self):
        self.assertIsNotNone(module.check({}))


if __name__ == "__main__":
    unittest.main()
