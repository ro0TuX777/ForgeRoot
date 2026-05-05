"""
Phase 1 tests 9–10:
9.  CONCORD event adapter emits a valid ledger event.
10. ForgeGate DecisionRecord adapter emits a valid ledger event.
"""
from integrations.concord_ledger_adapter import build_ledger_event_from_concord
from integrations.forgegate_ledger_adapter import build_ledger_event_from_forgegate
from forgeledger.hash_chain import attach_integrity, verify_chain
from forgeledger.schema import EventType, RetentionClass
from forgeledger.validators import validate_event


# ---------------------------------------------------------------------------
# Fixtures (plain dicts — no CONCORD or ForgeGate imports needed)
# ---------------------------------------------------------------------------

CONCORD_ADMISSION_ALLOWED = {
    "intent_id": "intent-abc-123",
    "agent_class": "SolutionDesigner",
    "trust_tier": "TIER_2",
    "admitted": True,
    "reason": "within_capability_budget",
    "risk_level": "low",
    "policy_id": "concord_policy_v0.5",
    "policy_hash": "sha256_concord_policy_hash",
    "capabilities_checked": ["SOLUTION_DESIGN", "DOCUMENT_READ"],
    "tenant_id": "tenant-demo",
    "customer_boundary": "synthetic_a",
    "data_residency": "NZ",
    "deployment_id": "forgeroot-demo",
}

CONCORD_ADMISSION_DENIED = {
    "intent_id": "intent-blocked-456",
    "agent_class": "RemediationAgent",
    "trust_tier": "TIER_1",
    "admitted": False,
    "reason": "capability_not_granted",
    "risk_level": "high",
    "policy_id": "concord_policy_v0.5",
    "policy_hash": "sha256_concord_policy_hash",
    "tenant_id": "tenant-demo",
    "customer_boundary": "synthetic_a",
    "data_residency": "NZ",
    "deployment_id": "forgeroot-demo",
}

FORGEGATE_DECISION_DENY = {
    "decision_id": "dec-xyz-456",
    "agent_class": "RemediationAgent",
    "action_type": "FILE_WRITE",
    "decision": "deny",
    "reason": "exceeds_blast_radius_threshold",
    "risk_level": "high",
    "policy_id": "forgegate_policy_nz_msp_v0.1",
    "policy_hash": "sha256_forgegate_policy_hash",
    "blast_radius_score": 0.87,
    "tenant_id": "tenant-demo",
    "customer_boundary": "synthetic_a",
    "data_residency": "NZ",
    "deployment_id": "forgeroot-demo",
}

FORGEGATE_DECISION_ALLOW = {
    "decision_id": "dec-allow-789",
    "agent_class": "SolutionDesigner",
    "action_type": "DOCUMENT_READ",
    "decision": "allow",
    "reason": "within_policy_bounds",
    "risk_level": "low",
    "policy_id": "forgegate_policy_nz_msp_v0.1",
    "policy_hash": "sha256_forgegate_policy_hash",
    "blast_radius_score": 0.1,
    "tenant_id": "tenant-demo",
    "customer_boundary": "synthetic_a",
    "data_residency": "NZ",
    "deployment_id": "forgeroot-demo",
}


# ---------------------------------------------------------------------------
# Test 9: CONCORD adapter
# ---------------------------------------------------------------------------

def test_concord_adapter_emits_valid_ledger_event():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    errors = validate_event(attach_integrity(event, None))
    assert errors == [], f"Validation errors: {errors}"


def test_concord_adapter_sets_correct_event_type():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert event.event_type == EventType.CONCORD_ADMISSION_DECISION


def test_concord_adapter_sets_source_module():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert event.system_context.source_module == "CONCORD"


def test_concord_adapter_maps_admitted_true_to_allow():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert event.decision.decision_type == "allow"


def test_concord_adapter_maps_admitted_false_to_deny():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_DENIED)
    assert event.decision.decision_type == "deny"


def test_concord_adapter_preserves_policy_hash():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert event.policy.policy_hash == "sha256_concord_policy_hash"


def test_concord_adapter_sets_tenant():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert event.tenant.tenant_id == "tenant-demo"
    assert event.tenant.data_residency == "NZ"


def test_concord_adapter_classifies_retention_as_audit_7y():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert event.policy.retention_class == RetentionClass.AUDIT_7Y


def test_concord_adapter_sets_control_tags():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert any("NZISM" in tag for tag in event.control_tags)


def test_concord_adapter_stores_intent_id_in_payload():
    event = build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED)
    assert event.payload is not None
    assert event.payload["intent_id"] == "intent-abc-123"


# ---------------------------------------------------------------------------
# Test 10: ForgeGate adapter
# ---------------------------------------------------------------------------

def test_forgegate_adapter_emits_valid_ledger_event():
    event = build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY)
    errors = validate_event(attach_integrity(event, None))
    assert errors == [], f"Validation errors: {errors}"


def test_forgegate_adapter_sets_correct_event_type():
    event = build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY)
    assert event.event_type == EventType.FORGEGATE_DECISION_RECORD


def test_forgegate_adapter_sets_source_module():
    event = build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY)
    assert event.system_context.source_module == "ForgeGate"


def test_forgegate_adapter_maps_decision_type():
    deny = build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY)
    allow = build_ledger_event_from_forgegate(FORGEGATE_DECISION_ALLOW)
    assert deny.decision.decision_type == "deny"
    assert allow.decision.decision_type == "allow"


def test_forgegate_adapter_preserves_policy_hash():
    event = build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY)
    assert event.policy.policy_hash == "sha256_forgegate_policy_hash"


def test_forgegate_adapter_high_blast_radius_creates_evidence_gap():
    event = build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY)
    # blast_radius_score=0.87 exceeds the 0.7 threshold
    assert any(g.gap_type == "high_blast_radius" for g in event.evidence.evidence_gaps)


def test_forgegate_adapter_low_blast_radius_no_gap():
    event = build_ledger_event_from_forgegate(FORGEGATE_DECISION_ALLOW)
    # blast_radius_score=0.1 is below threshold
    assert not any(g.gap_type == "high_blast_radius" for g in event.evidence.evidence_gaps)


def test_forgegate_adapter_classifies_retention_as_audit_7y():
    event = build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY)
    assert event.policy.retention_class == RetentionClass.AUDIT_7Y


def test_adapters_produce_chainable_events():
    """Events from both adapters can be chained together correctly."""
    e1 = attach_integrity(build_ledger_event_from_concord(CONCORD_ADMISSION_ALLOWED), None)
    e2 = attach_integrity(build_ledger_event_from_forgegate(FORGEGATE_DECISION_DENY), e1.integrity.event_hash)

    report = verify_chain([e1, e2])
    assert report.valid is True
    assert report.total_events == 2
