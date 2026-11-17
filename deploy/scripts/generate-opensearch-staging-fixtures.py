#!/usr/bin/env python3
"""Print synthetic OpenSearch Bulk NDJSON for a disposable staging index.

Offline only: no network, no credentials, no writes. A staging operator must
review the output and import it using a separate, authorized workflow.
"""
import argparse
import json
from datetime import datetime, timedelta
import re
from uuid import UUID


def canonical_uuid(value):
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("Valid tenant UUID required") from exc
    if parsed.int == 0:
        raise argparse.ArgumentTypeError("Nil tenant UUID is forbidden")
    result = str(parsed)
    if value != result:
        raise argparse.ArgumentTypeError("Canonical UUID required")
    return result


def generate(tenant_a, tenant_b, service_a, service_b, marker, index, at):
    tenant_a = canonical_uuid(tenant_a)
    tenant_b = canonical_uuid(tenant_b)
    if tenant_a == tenant_b or service_a == service_b:
        raise ValueError("Distinct tenants and services required")
    if not re.fullmatch(r"[A-Za-z0-9-]{8,128}", marker):
        raise ValueError("Use a unique ASCII alphanumeric/hyphen marker of >=8 characters")
    if not re.fullmatch(r"staging-[a-z0-9][a-z0-9._-]{0,127}", index):
        raise ValueError("Explicit staging- index name required (no wildcards)")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", service) for service in (service_a, service_b)):
        raise ValueError("Invalid service name")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    cases = [
        (tenant_a, service_a, "ERROR", at),
        (tenant_a, service_b, "WARN", at),
        (tenant_b, service_a, "ERROR", at),
        (tenant_b, service_b, "WARN", at),
        (tenant_a, service_a, "ERROR", at - timedelta(days=2)),
    ]
    for i, (tenant, service, severity, timestamp) in enumerate(cases, 1):
        yield {"index": {"_index": index, "_id": f"{marker}-{i}"}}
        yield {
            "@timestamp": timestamp.isoformat(),
            "tenant": {"id": tenant},
            "resource": {"attributes": {"service": {"name": service}}},
            "severityText": severity,
            "body": f"synthetic staging fixture {marker} {i}",
            "gamma_fixture_marker": marker,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-a", required=True, type=canonical_uuid)
    parser.add_argument("--tenant-b", required=True, type=canonical_uuid)
    parser.add_argument("--service-a", required=True)
    parser.add_argument("--service-b", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--at", required=True, help="ISO-8601 timestamp inside test window")
    args = parser.parse_args()
    try:
        at = datetime.fromisoformat(args.at)
        # Materialize and validate the entire fixture before printing anything.
        lines = list(generate(
            args.tenant_a, args.tenant_b, args.service_a, args.service_b,
            args.marker, args.index, at,
        ))
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))
    for line in lines:
        print(json.dumps(line, separators=(",", ":"), ensure_ascii=True))


if __name__ == "__main__":
    main()
