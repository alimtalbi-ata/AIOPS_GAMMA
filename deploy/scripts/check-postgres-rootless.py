#!/usr/bin/env python3
"""Fail closed before rootless startup if PostgreSQL lacks explicit numeric non-root UID."""
import json
import re
import sys


def check(services):
    if not isinstance(services, dict):
        return "services must be a mapping"
    pg = services.get("postgres")
    if not isinstance(pg, dict):
        return "postgres service missing"
    user = pg.get("user", "")
    if not isinstance(user, str) or not re.fullmatch(r"[0-9]+(?::[0-9]+)?", user):
        return f"postgres must configure an explicit numeric non-root UID (got {user!r})"
    uid = int(user.split(":", 1)[0], 10)
    if uid == 0:
        return f"postgres configured root UID ({user})"
    # Check the effective, merged Compose config, not individual overlay files:
    # an empty cap_add list in a later overlay may retain earlier additions.
    if pg.get("cap_add"):
        return f"postgres retains added capabilities: {pg['cap_add']!r}"
    if pg.get("cap_drop") != ["ALL"]:
        return "postgres must drop ALL capabilities"
    return None


def main():
    try:
        document = json.load(sys.stdin)
        error = check(document["services"])
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Invalid Compose configuration: {exc}", file=sys.stderr)
        return 2
    if error:
        print(f"Rootless PostgreSQL preflight REFUSED: {error}", file=sys.stderr)
        return 2
    print("PostgreSQL configured non-root UID preflight passed (runtime unverified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
