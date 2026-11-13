from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.reused.itil import IncidentAssessment, ITSMReference
from app.reused.itsm_contract import (
    IncidentSyncPreview, PriorityMatrix, PriorityRule, plan_incident_sync,
)


TENANT = uuid4()
LEVELS = ("high", "medium", "low")


def matrix():
    return PriorityMatrix(
        policy_id="enterprise-priority", version="v1",
        rules=[PriorityRule(impact=i, urgency=u, priority=f"P{a+b+1}")
               for a, i in enumerate(LEVELS) for b, u in enumerate(LEVELS)]
    )


def incident(*, tenant=TENANT, impact="high", urgency="medium", ref=None, evidence=None):
    return IncidentAssessment(
        tenant_id=tenant, incident_id="INC-123", impact=impact, urgency=urgency,
        evidence_refs=["trace-1"] if evidence is None else evidence, itsm_ref=ref,
    )


def test_enterprise_priority_is_explicit_and_no_side_effects():
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    result = plan_incident_sync(req, TENANT)
    assert result["priority"] == "P2"
    assert result["priority_state"] == "PROPOSED_BY_ENTERPRISE_MATRIX"
    assert result["itsm_mutations_performed"] is False
    assert result["live_remediation_authorized"] is False
    assert result["persistence_state"] == "NOT_PERSISTED"


def test_idempotency_key_stable_for_replay():
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    assert plan_incident_sync(req, TENANT)["idempotency_key"] == plan_incident_sync(req, TENANT)["idempotency_key"]


def test_no_universal_priority_for_unknown_impact():
    req = IncidentSyncPreview(incident=incident(impact="unknown"), matrix=matrix())
    assert plan_incident_sync(req, TENANT)["priority"] == "UNKNOWN"


def test_cross_tenant_denied():
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    with pytest.raises(ValueError, match="Tenant"):
        plan_incident_sync(req, uuid4())


def test_enrichment_requires_matching_ticket_reference():
    ref = ITSMReference(system="glpi", external_id="101")
    req = IncidentSyncPreview(
        incident=incident(ref=ref), matrix=matrix(), operation="propose_enrichment",
        expected_itsm_ref=ref,
    )
    assert plan_incident_sync(req, TENANT)["itsm_reference"]["external_id"] == "101"
    bad = req.model_copy(update={"expected_itsm_ref": ITSMReference(system="glpi", external_id="102")})
    with pytest.raises(ValueError, match="matching"):
        plan_incident_sync(bad, TENANT)


def test_existing_ticket_cannot_be_recreated():
    ref = ITSMReference(system="glpi", external_id="101")
    with pytest.raises(ValueError, match="Existing"):
        plan_incident_sync(IncidentSyncPreview(incident=incident(ref=ref), matrix=matrix()), TENANT)


def test_no_evidence_denied():
    with pytest.raises(ValueError, match="evidence"):
        plan_incident_sync(IncidentSyncPreview(incident=incident(evidence=[]), matrix=matrix()), TENANT)


def test_duplicate_matrix_pair_denied():
    m = matrix()
    rules = m.rules.copy()
    rules[-1] = rules[0]
    with pytest.raises(ValidationError, match="exactly once"):
        PriorityMatrix(policy_id="test", version="v1", rules=rules)


@pytest.mark.parametrize("field,value", [
    ("policy_id", " "), ("policy_id", "policy\nforged"),
    ("policy_id", "policy\tforged"), ("version", " "),
    ("version", "v1\rforged"), ("version", "v1\x7f"),
])
def test_priority_policy_identity_rejects_blank_or_control_characters(field, value):
    kwargs = {"policy_id": "enterprise", "version": "v1", "rules": matrix().rules}
    kwargs[field] = value
    with pytest.raises(ValidationError, match="Invalid priority policy identity"):
        PriorityMatrix(**kwargs)


def test_priority_policy_identity_accepts_normal_values():
    result = matrix()
    assert result.policy_id == "enterprise-priority"
    assert result.version == "v1"


@pytest.mark.parametrize("field,value", [
    ("policy_id", "   "), ("policy_id", "policy\nforged"),
    ("version", "\t"), ("version", "v2\rforged"),
])
def test_sync_rechecks_policy_identity_after_unvalidated_model_copy(field, value):
    altered = matrix().model_copy(update={field: value})
    req = IncidentSyncPreview(incident=incident(), matrix=altered)
    with pytest.raises(ValueError, match="Invalid priority policy identity"):
        plan_incident_sync(req, TENANT)


def test_sync_rechecks_policy_identity_after_mutation():
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    req.matrix.version = "v1\x7f"
    with pytest.raises(ValueError, match="Invalid priority policy identity"):
        plan_incident_sync(req, TENANT)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "extra"])
def test_sync_rejects_mutated_priority_matrix_mapping(mutation):
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    if mutation == "duplicate":
        req.matrix.rules[-1] = req.matrix.rules[0].model_copy()
    elif mutation == "missing":
        req.matrix.rules.pop()
    else:
        req.matrix.rules.append(req.matrix.rules[0].model_copy())
    with pytest.raises(ValueError, match="Invalid priority matrix mapping"):
        plan_incident_sync(req, TENANT)


def test_sync_accepts_complete_priority_matrix_after_revalidation():
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    result = plan_incident_sync(req, TENANT)
    assert result["priority"] == "P2"
    assert result["live_remediation_authorized"] is False


@pytest.mark.parametrize("invalid_priority", [
    "", " ", "P1\nforged", "P1\tforged", "P1/unsafe", "P" * 33, None,
])
def test_sync_rejects_mutated_priority_labels(invalid_priority):
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    req.matrix.rules[1].priority = invalid_priority
    with pytest.raises(ValueError, match="Invalid priority matrix rule"):
        plan_incident_sync(req, TENANT)


def test_sync_keeps_valid_mutated_priority_label():
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    req.matrix.rules[1].priority = "P2-REVIEW"
    result = plan_incident_sync(req, TENANT)
    assert result["priority"] == "P2-REVIEW"
    assert result["itsm_mutations_performed"] is False


@pytest.mark.parametrize("operation", [
    "propose_delete", "propose_enrichment\nforged", "", None,
])
def test_sync_rejects_unvalidated_operation_mutations(operation):
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    req.operation = operation
    with pytest.raises(ValueError, match="Invalid ITSM sync operation"):
        plan_incident_sync(req, TENANT)


def test_sync_accepts_supported_create_operation():
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    result = plan_incident_sync(req, TENANT)
    assert result["operation"] == "propose_create"
    assert result["itsm_mutations_performed"] is False


@pytest.mark.parametrize("field,value", [
    ("policy_id", None), ("policy_id", 123),
    ("version", None), ("version", ["v1"]),
])
def test_sync_rejects_nonstring_policy_identity_after_mutation(field, value):
    req = IncidentSyncPreview(incident=incident(), matrix=matrix())
    setattr(req.matrix, field, value)
    with pytest.raises(ValueError, match="Invalid priority policy identity"):
        plan_incident_sync(req, TENANT)


@pytest.mark.parametrize("field,value", [
    ("external_id", " "), ("external_id", "101\nforged"),
    ("external_id", "101|forged"), ("external_id", 123),
    ("system", "untrusted"),
])
def test_sync_rejects_mutated_authoritative_ticket_reference(field, value):
    ref = ITSMReference(system="glpi", external_id="101")
    req = IncidentSyncPreview(
        incident=incident(ref=ref), matrix=matrix(),
        operation="propose_enrichment", expected_itsm_ref=ref,
    )
    setattr(ref, field, value)
    with pytest.raises(ValueError, match="Invalid authoritative ITSM reference"):
        plan_incident_sync(req, TENANT)


def test_sync_rejects_mutated_expected_ticket_reference():
    authoritative = ITSMReference(system="glpi", external_id="101")
    expected = ITSMReference(system="glpi", external_id="101")
    req = IncidentSyncPreview(
        incident=incident(ref=authoritative), matrix=matrix(),
        operation="propose_enrichment", expected_itsm_ref=expected,
    )
    expected.external_id = "101\rforged"
    with pytest.raises(ValueError, match="Invalid authoritative ITSM reference"):
        plan_incident_sync(req, TENANT)
