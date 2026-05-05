"""
Phase 1 tests 6 & 8:
6. Every event gets a retention class.
8. Every policy decision records a policy hash.
"""
from forgeledger.hash_chain import attach_integrity
from forgeledger.retention import classify_event
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    Evidence,
    EventType,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type: EventType,
    legal_hold: bool = False,
    data_sensitivity: str | None = None,
    control_tags: list[str] | None = None,
) -> LedgerEvent:
    payload = {"data_sensitivity": data_sensitivity} if data_sensitivity else None
    return LedgerEvent(
        event_id="evt-r-001",
        ledger_version=LEDGER_VERSION,
        event_type=event_type,
        event_time="2026-04-28T00:00:00Z",
        actor=Actor(actor_type="agent", actor_id="test.agent", role="test"),
        tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="test", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=[]),
        policy=Policy(
            policy_id="p-001",
            policy_hash="test_policy_sha256",
            retention_class=RetentionClass.OPERATIONAL_30D,
            legal_hold=legal_hold,
        ),
        control_tags=control_tags or [],
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Test 6: Every event gets a retention class
# ---------------------------------------------------------------------------

def test_every_event_type_receives_a_retention_class():
    """classify_event must return a RetentionClass for every defined EventType."""
    for et in EventType:
        event = _make_event(et)
        rc = classify_event(event)
        assert isinstance(rc, RetentionClass), f"No retention class for {et}"


def test_concord_admission_classified_as_audit_7y():
    event = _make_event(EventType.CONCORD_ADMISSION_DECISION)
    assert classify_event(event) == RetentionClass.AUDIT_7Y


def test_forgegate_decision_classified_as_audit_7y():
    event = _make_event(EventType.FORGEGATE_DECISION_RECORD)
    assert classify_event(event) == RetentionClass.AUDIT_7Y


def test_agent_tool_call_classified_as_operational_30d():
    event = _make_event(EventType.AGENT_TOOL_CALL)
    assert classify_event(event) == RetentionClass.OPERATIONAL_30D


def test_warden_llm_call_classified_as_support_1y():
    event = _make_event(EventType.WARDEN_LLM_CALL_METADATA)
    assert classify_event(event) == RetentionClass.SUPPORT_1Y


# ---------------------------------------------------------------------------
# Test 6 — sensitivity overrides
# ---------------------------------------------------------------------------

def test_health_identifiable_data_overrides_to_health_10y():
    event = _make_event(EventType.AGENT_TOOL_CALL, data_sensitivity="health_identifiable")
    assert classify_event(event) == RetentionClass.HEALTH_10Y


def test_legal_hold_flag_overrides_everything():
    for et in EventType:
        event = _make_event(et, legal_hold=True)
        assert classify_event(event) == RetentionClass.LEGAL_HOLD, (
            f"Expected LEGAL_HOLD for {et} when legal_hold=True"
        )


# ---------------------------------------------------------------------------
# Test 8: Policy decision records a policy hash
# ---------------------------------------------------------------------------

def test_policy_hash_is_present_on_finalised_event():
    """Events emitted for policy decisions must include a non-empty policy_hash."""
    policy_event_types = [
        EventType.CONCORD_ADMISSION_DECISION,
        EventType.FORGEGATE_DECISION_RECORD,
        EventType.FORGEGATE_POLICY_EVALUATION,
    ]
    for et in policy_event_types:
        event = _make_event(et)
        event_with_chain = attach_integrity(event, None)
        assert event_with_chain.policy.policy_hash, (
            f"policy_hash must be non-empty for {et}"
        )


def test_policy_hash_is_preserved_through_serialisation():
    import json
    from forgeledger.canonical_json import canonical_json
    from forgeledger.schema import event_from_dict

    event = _make_event(EventType.FORGEGATE_DECISION_RECORD)
    chained = attach_integrity(event, None)
    restored = event_from_dict(json.loads(canonical_json(chained)))
    assert restored.policy.policy_hash == "test_policy_sha256"
