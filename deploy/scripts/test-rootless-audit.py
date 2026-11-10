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
  *"ps --all -q") echo mock-postgres ;;
  *".Name"*) echo /mock-postgres ;;
  *".State.Running"*) echo "${MOCK_RUNNING:-true}" ;;
  *".HostConfig.Privileged"*) echo "${MOCK_PRIVILEGED:-false}" ;;
  *".Config.User"*) printf '%s\\n' "${MOCK_CONFIG_USER-999:999}" ;;
  *".Mounts"*) printf '%s\\n' "${MOCK_MOUNT-$GAMMA_HOME/data/postgres}" ;;
  "exec mock-postgres "*) printf 'Uid:\\t%s\\t%s\\t%s\\t%s\\n' "${MOCK_RUNTIME_UID:-999}" "${MOCK_RUNTIME_UID:-999}" "${MOCK_RUNTIME_UID:-999}" "${MOCK_RUNTIME_UID:-999}" | awk '/^Uid:/ {print $2}' ;;
  *) echo "unexpected mocked docker call: $*" >&2; exit 9 ;;
esac
""",
            encoding="utf-8",
        )
        docker.chmod(0o755)

    def audit(self, config_user="999:999", runtime_uid="999", privileged="false", running="true", mount=None):
        env = dict(
            os.environ,
            GAMMA_HOME=str(self.home),
            MOCK_CONFIG_USER=config_user,
            MOCK_RUNTIME_UID=runtime_uid,
            MOCK_PRIVILEGED=privileged,
            MOCK_RUNNING=running,
            MOCK_MOUNT=mount if mount is not None else str(self.home / "data" / "postgres"),
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

    def test_numeric_root_with_group_rejected(self):
        for user in ("0:1000", "00:1000", "000"):
            with self.subTest(user=user):
                result = self.audit(config_user=user)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("UNQUALIFIED CONFIG USER", result.stderr)

    def test_nonroot_numeric_uid_with_group_passes(self):
        for user in ("10001:10001", "08:08"):
            with self.subTest(user=user):
                result = self.audit(config_user=user)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_configured_gid_rejected(self):
        for user in ("10001:", "10001:postgres", "10001:100:200"):
            with self.subTest(user=user):
                result = self.audit(config_user=user)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("UNQUALIFIED CONFIG USER", result.stderr)

    def test_zero_padded_runtime_root_rejected(self):
        result = self.audit(runtime_uid="000")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROOT RUNTIME UID", result.stderr)

    def test_named_user_is_not_accepted_without_numeric_uid(self):
        result = self.audit(config_user="postgres")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UNQUALIFIED CONFIG USER", result.stderr)

    def test_root_process_rejected_even_if_config_nonroot(self):
        result = self.audit(runtime_uid="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROOT RUNTIME UID", result.stderr)

    def test_privileged_container_rejected(self):
        result = self.audit(privileged="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PRIVILEGED", result.stderr)

    def test_stopped_container_rejected(self):
        result = self.audit(running="false")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NOT RUNNING", result.stderr)

    def test_out_of_tree_bind_rejected(self):
        result = self.audit(mount="/var/unsafe-postgres")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OUT-OF-TREE BIND", result.stderr)

    def test_symlink_bind_escape_rejected(self):
        external = self.base / "outside"
        external.mkdir()
        escaped = self.home / "data" / "indirect"
        escaped.symlink_to(external, target_is_directory=True)
        result = self.audit(mount=str(escaped))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BIND ESCAPES DATA ROOT", result.stderr)

    def test_missing_bind_source_rejected(self):
        result = self.audit(mount=str(self.home / "data" / "missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BIND SOURCE NOT DIRECTORY", result.stderr)

    def test_group_writable_bind_rejected(self):
        mount = self.home / "data" / "postgres"
        mount.chmod(0o770)
        result = self.audit()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BIND GROUP/OTHER WRITABLE", result.stderr)

    def test_world_writable_bind_rejected(self):
        mount = self.home / "data" / "postgres"
        mount.chmod(0o777)
        result = self.audit()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BIND GROUP/OTHER WRITABLE", result.stderr)

    def test_named_volume_rejected(self):
        result = self.audit(mount="NAMED_VOLUME")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NAMED VOLUME", result.stderr)

    def test_invalid_process_uid_rejected(self):
        result = self.audit(runtime_uid="invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("INVALID RUNTIME UID", result.stderr)


if __name__ == "__main__":
    unittest.main()
