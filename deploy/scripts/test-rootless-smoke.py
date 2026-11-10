"""Offline tests for fail-closed disposable rootless smoke startup guards."""
import os
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).with_name("smoke-rootless.sh")


class DisposableSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gamma-smoke-test-", dir=pathlib.Path.home())
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.home = self.base / "gamma"
        self.home.mkdir()
        self.fakebin = self.base / "bin"
        self.fakebin.mkdir()
        self.marker = self.base / "compose-called"
        docker = self.fakebin / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  *SecurityOptions*) echo '[\"name=rootless\"]' ;;\n"
            "  *DockerRootDir*) echo \"$GAMMA_HOME/docker-data\" ;;\n"
            "  compose*) case \"$*\" in\n"
            "    *\"ps --all -q\"*) printf '%s' \"$MOCK_EXISTING_CONTAINERS\"; exit 0 ;;\n"
            "    *) touch \"$MOCK_COMPOSE_MARKER\"; exit 77 ;;\n"
            "  esac ;;\n"
            "  *) exit 9 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        docker.chmod(0o755)

    def run_smoke(self, opt_in=None, existing=""):
        env = dict(
            os.environ,
            GAMMA_HOME=str(self.home),
            POSTGRES_PASSWORD="ci-only",
            INTERNAL_API_KEY="ci-only",
            MOCK_COMPOSE_MARKER=str(self.marker),
            MOCK_EXISTING_CONTAINERS=existing,
            PATH=str(self.fakebin) + os.pathsep + os.environ["PATH"],
        )
        env.pop("GAMMA_ROOTLESS_SMOKE_DISPOSABLE", None)
        if opt_in is not None:
            env["GAMMA_ROOTLESS_SMOKE_DISPOSABLE"] = opt_in
        return subprocess.run(
            ["sh", str(SCRIPT)], env=env, cwd=SCRIPT.parents[2],
            capture_output=True, text=True,
        )

    def test_missing_opt_in_does_not_start_compose(self):
        result = self.run_smoke()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("GAMMA_ROOTLESS_SMOKE_DISPOSABLE", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_wrong_opt_in_does_not_start_compose(self):
        result = self.run_smoke("yes")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.marker.exists())

    def test_existing_postgres_data_is_preserved(self):
        pg = self.home / "data" / "postgres"
        pg.mkdir(parents=True)
        sentinel = pg / ".existing-data"
        sentinel.write_text("preserve", encoding="utf-8")
        result = self.run_smoke("YES")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("not empty", result.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
        self.assertFalse(self.marker.exists())

    def test_existing_compose_project_is_not_reused(self):
        result = self.run_smoke("YES", existing="existing-container")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("already has containers", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_empty_disposable_home_reaches_compose(self):
        result = self.run_smoke("YES")
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertTrue(self.marker.exists())
        self.assertTrue((self.home / "data" / "postgres").is_dir())


if __name__ == "__main__":
    unittest.main()
