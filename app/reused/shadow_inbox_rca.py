"""Offline P2 contract: join synthetic inbox identities to RCA evidence.

No database, external reads, or operational authorization.
"""
from dataclasses import dataclass
from app.reused.shadow_investigation import Evidence, InvestigationInput, investigate_shadow


@dataclass(frozen=True)
class SyntheticInboxReceipt:
    tenant_id: str
    incident_id: str
    event_id: str
    evidence_refs: tuple[str, ...]


def evaluate_inbox_evidence(receipt: SyntheticInboxReceipt, investigation: InvestigationInput) -> dict:
    if type(receipt) is not SyntheticInboxReceipt or type(investigation) is not InvestigationInput:
        raise ValueError("Invalid synthetic input")
    if any(type(x) is not str or not x.strip() for x in
           (receipt.tenant_id, receipt.incident_id, receipt.event_id)):
        raise ValueError("Missing receipt identity")
    if (receipt.tenant_id, receipt.incident_id) != (investigation.tenant_id, investigation.incident_id):
        raise ValueError("Receipt identity mismatch")
    refs = receipt.evidence_refs
    if type(refs) is not tuple or any(type(x) is not str or not x.strip() for x in refs):
        raise ValueError("Malformed receipt references")
    if len(set(refs)) != len(refs):
        raise ValueError("Duplicate receipt references")
    if type(investigation.evidence) is not tuple or any(type(e) is not Evidence for e in investigation.evidence):
        raise ValueError("Malformed evidence")
    if set(refs) != {e.ref for e in investigation.evidence}:
        raise ValueError("Evidence reference mismatch")
    result = investigate_shadow(investigation)
    return {
        "mode": "synthetic_shadow",
        "event_id": receipt.event_id,
        "tenant_id": receipt.tenant_id,
        "incident_id": receipt.incident_id,
        "investigation": result,
        "authoritative": False,
        "live_execution_authorized": False,
        "itsm_mutations_performed": False,
    }
