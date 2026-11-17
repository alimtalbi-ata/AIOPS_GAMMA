#!/usr/bin/env python3
"""Read-only smoke checks for an isolated local GAMMA Compose installation.

Never starts/stops containers, writes to a database, or calls tenant endpoints.
"""
import json
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def check_http(url: str, *, expect_json: bool) -> None:
    with urlopen(url, timeout=8) as response:
        if response.status != 200:
            raise RuntimeError(f"{url}: HTTP {response.status}")
        body = response.read(1024 * 1024)
        if expect_json:
            payload = json.loads(body)
            if payload != {"status": "ok"}:
                raise RuntimeError(f"{url}: unexpected health payload")
        elif b"<html" not in body.lower() and b"<!doctype html" not in body.lower():
            raise RuntimeError(f"{url}: frontend HTML missing")
    print(f"PASS HTTP {url}")


def check_migration() -> None:
    cmd = [
        "docker", "compose", "exec", "-T", "postgres", "psql",
        "-U", "aiops", "-d", "aiops", "-Atc",
        "SELECT version_num FROM alembic_version",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    if result.returncode != 0:
        raise RuntimeError("PostgreSQL migration check failed: " + result.stderr.strip()[:400])
    if result.stdout.strip() != "0002_gateway_replay":
        raise RuntimeError("Unexpected Alembic revision: " + repr(result.stdout.strip()))
    print("PASS PostgreSQL migration 0002_gateway_replay")


def main() -> int:
    try:
        check_http("http://127.0.0.1:8000/api/v1/health/live", expect_json=True)
        check_http("http://127.0.0.1:5173/", expect_json=False)
        check_migration()
    except (HTTPError, URLError, OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL GAMMA local smoke: {exc}", file=sys.stderr)
        return 1
    print("PASS GAMMA local smoke (not tenant ACL or production qualification)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
