"""Conservative AIOps 2.0 run/evidence projection (no production attestation)."""
from typing import Any

from app.reused.tenant_scope import reject_unqualified_tenant_scope


def project_run_evidence(run: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(run, dict):
        raise ValueError("invalid run")
    reject_unqualified_tenant_scope(run)
    if run.get("mode") not in ("DEMO", "REPLAY", "STORY"):
        raise ValueError("LIVE run cannot be projected without independently qualified ACL")
    if not isinstance(run.get("run_id"), str) or not run["run_id"]:
        raise ValueError("invalid run_id")
    if not isinstance(run.get("incident_id"), str) or not run["incident_id"]:
        raise ValueError("invalid incident_id")
    return {
        "run_id": run["run_id"],
        "incident_id": run["incident_id"],
        "mode": run["mode"],
        "status": run.get("status", "UNKNOWN"),
        "source": "AIOPS2_CANONICAL_RUN_UNATTESTED",
        "runtime_authenticated": False,
        "live_remediation_authorized": False,
    }
