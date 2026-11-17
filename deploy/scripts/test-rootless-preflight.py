"""Offline negative/positive tests for the rootless home preflight (mock Docker only)."""
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("check-rootless-home.sh")


class RootlessPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gamma-rootless-test-", dir=pathlib.Path.home())
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.home = self.base / "gamma"
        self.home.mkdir()
        self.fakebin = self.base / "bin"
        self.fakebin.mkdir()
        docker = self.fakebin / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  *SecurityOptions*) echo '[\"name=rootless\"]' ;;\n"
            "  *DockerRootDir*) echo \"$GAMMA_HOME/docker-data\" ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)

    def run_check(self, home=None):
        env = dict(os.environ, GAMMA_HOME=str(home or self.home))
        env["PATH"] = str(self.fakebin) + os.pathsep + env["PATH"]
        return subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True)

    def test_accepts_owned_canonical_root(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_relative_root(self):
        self.assertNotEqual(self.run_check(pathlib.Path("relative")).returncode, 0)

    def test_rejects_symlink_outside_data(self):
        (self.home / "data").symlink_to(self.base, target_is_directory=True)
        self.assertNotEqual(self.run_check().returncode, 0)

    def test_rejects_symlink_outside_docker_data(self):
        (self.home / "docker-data").symlink_to(self.base, target_is_directory=True)
        self.assertNotEqual(self.run_check().returncode, 0)


if __name__ == "__main__":
    unittest.main()
