#!/usr/bin/env python3
"""Run a bounded GAMMA source-only test suite in a disposable lab.

Requires an actual checked-out GAMMA repository and installed test dependencies.
Does not provision GitHub runners, PostgreSQL, Docker or external credentials.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

SAFE_TESTS = (
    "tests/test_canonical_acl_hard_hold_static.py",
    "tests/test_canonical_route_http_hold.py",
    "tests/test_resource_list_http_tenant_isolation.py",
    "tests/test_gateway_dependency_http_isolated.py",
    "tests/test_gateway_resource_acl_contract.py",
    "tests/test_upstream.py",
    "tests/test_upstream_fail_closed_extra.py",
    "tests/test_upstream_http_mock.py",
    "tests/test_upstream_transport_boundary.py",
    "tests/test_upstream_json_contract.py",
)
REQUIRED_FILES = (
    "pyproject.toml", "app/main.py", "app/security.py",
    "app/reused/upstream.py", *SAFE_TESTS,
)
UNSAFE_ENV_KEYS = (
    "DATABASE_URL", "GAMMA_REPLAY_TEST_DATABASE_URL",
    "GAMMA_REPLAY_TEST_ALLOW_WRITE",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=None,
                        help="Write machine-readable results outside the repo")
    parser.add_argument("--check-only", action="store_true",
                        help="Validate checkout and safety guards without running pytest")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        print("Refusing incomplete checkout: " + ", ".join(missing), file=sys.stderr)
        return 2
    if any(key in os.environ for key in UNSAFE_ENV_KEYS):
        print("Refusing inherited database/replay test environment", file=sys.stderr)
        return 2

    dest = args.report.resolve() if args.report else None
    if dest is not None and (dest == root or root in dest.parents):
        print("Report must be outside repository checkout", file=sys.stderr)
        return 2
    if args.check_only:
        print(json.dumps({
            "kind": "gamma-bounded-source-lab-preflight",
            "status": "ready",
            "test_files": list(SAFE_TESTS),
            "note": "No pytest tests executed",
        }, indent=2))
        return 0

    # An explicit fixed allowlist: never run the real-Postgres or staging tests
    # in a generic ChatGPT lab, even when they are present in the checkout.
    cmd = [sys.executable, "-m", "pytest", "-q", *SAFE_TESTS]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(cmd, cwd=root, env=env, check=False)
    finished = datetime.now(timezone.utc).isoformat()
    report = {
        "kind": "gamma-bounded-source-lab",
        "started_at_utc": started,
        "finished_at_utc": finished,
        "python": sys.version.split()[0],
        "tests": list(SAFE_TESTS),
        "command": cmd,
        "exit_code": result.returncode,
        "result": "pass" if result.returncode == 0 else "fail",
        "scope": "source-only; no real PostgreSQL, IdP, Docker or LIVE qualification",
    }
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
