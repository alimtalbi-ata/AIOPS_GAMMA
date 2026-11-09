"""Offline contract tests for the strict rootless runtime audit (mock Docker only)."""
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("audit-rootless-compose.sh")


class RootlessAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gamma-audit-test-", dir=pathlib.Path.home())
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.home = self.base / "gamma"
        (self.home / "data" / "postgres").mkdir(parents=True)
        self.fakebin = self.base / "bin"
        self.fakebin.mkdir()
        docker = self.fakebin / "docker"
        docker.write_text(
            """#!/bin/sh
case "$*" in
  *SecurityOptions*) echo '["name=rootless"]' ;;
  *DockerRootDir*) echo "$GAMMA_HOME/docker-data" ;;
  "compose "* "ps --all -q") echo mock-postgres ;;
  *".Name"*) echo /mock-postgres ;;
  *".State.Running"*) echo true ;;
  *".HostConfig.Privileged"*) echo false ;;
  *".Config.User"*) printf '%s\\n' "${MOCK_CONFIG_USER-999:999}" ;;
  *".Mounts"*) echo "$GAMMA_HOME/data/postgres" ;;
  "exec mock-postgres "*) printf 'Uid:\\t%s\\t%s\\t%s\\t%s\\n' "${MOCK_RUNTIME_UID:-999}" "${MOCK_RUNTIME_UID:-999}" "${MOCK_RUNTIME_UID:-999}" "${MOCK_RUNTIME_UID:-999}" | awk '/^Uid:/ {print $2}' ;;
  *) echo "unexpected mocked docker call: $*" >&2; exit 9 ;;
esac
""",
            encoding="utf-8",
        )
        docker.chmod(0o755)

    def audit(self, config_user="999:999", runtime_uid="999"):
        env = dict(
            os.environ,
            GAMMA_HOME=str(self.home),
            MOCK_CONFIG_USER=config_user,
            MOCK_RUNTIME_UID=runtime_uid,
            PATH=str(self.fakebin) + os.pathsep + os.environ["PATH"],
        )
        return subprocess.run(
            ["sh", str(SCRIPT)], env=env, capture_output=True, text=True,
            cwd=SCRIPT.parents[2],
        )

    def test_nonroot_config_and_process_pass(self):
        result = self.audit()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_root_config_rejected_even_if_process_nonroot(self):
        result = self.audit(config_user="root")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNQUALIFIED CONFIG USER", result.stderr)

    def test_empty_config_rejected_even_if_process_nonroot(self):
        result = self.audit(config_user="")
        self.assertNotEqual(result.returncode, 0)

    def test_root_process_rejected_even_if_config_nonroot(self):
        result = self.audit(runtime_uid="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROOT RUNTIME UID", result.stderr)

    def test_invalid_process_uid_rejected(self):
        result = self.audit(runtime_uid="invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INVALID RUNTIME UID", result.stderr)


if __name__ == "__main__":
    unittest.main()
