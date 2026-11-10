#!/usr/bin/env python3
"""Print synthetic OpenSearch Bulk NDJSON for a disposable staging index.

Offline only: no network, no credentials, no writes. A staging operator must
review the output and import it using a separate, authorized workflow.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID


def canonical_uuid(value):
    result = str(UUID(value))
    if value != result:
        raise argparse.ArgumentTypeError("Canonical UUID required")
    return result


def generate(tenant_a, tenant_b, service_a, service_b, marker, index, at):
    if tenant_a == tenant_b or service_a == service_b:
        raise ValueError("Distinct tenants and services required")
    if len(marker) < 8 or not marker.isascii() or not marker.replace("-", "").isalnum():
        raise ValueError("Use a unique ASCII alphanumeric/hyphen marker of >=8 characters")
    if not index.startswith("staging-") or any(c in index for c in "*?,/ "):
        raise ValueError("Explicit staging- index name required (no wildcards)")
    if at.tzinfo is None:
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
    at = datetime.fromisoformat(args.at)
    for line in generate(
        args.tenant_a, args.tenant_b, args.service_a, args.service_b,
        args.marker, args.index, at,
    ):
        print(json.dumps(line, separators=(",", ":"), ensure_ascii=True))


if __name__ == "__main__":
    main()
