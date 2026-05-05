"""Tests for schema serialization and round-trip deserialization."""
import json

from forgeledger.canonical_json import canonical_json
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    Evidence,
    EvidenceGap,
    EventType,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
    event_from_dict,
)


def make_full_event() -> LedgerEvent:
    return LedgerEvent(
        event_id="evt-test-001",
        ledger_version=LEDGER_VERSION,
        event_type=EventType.FORGEGATE_DECISION_RECORD,
        event_time="2026-04-28T12:00:00Z",
        actor=Actor(actor_type="agent", actor_id="forgegate.evaluator", role="policy_engine"),
        tenant=Tenant(tenant_id="tenant-demo", customer_boundary="synthetic_a", data_residency="NZ"),
        system_context=SystemContext(source_module="ForgeGate", environment="local", deployment_id="demo-001"),
        decision=Decision(decision_type="deny", reason="risk_threshold_exceeded", risk_level="high"),
        evidence=Evidence(
            evidence_refs=["doc:policy_manual#s4"],
            evidence_gaps=[EvidenceGap(gap_type="missing_approval", blocking=True)],
            assertion_classes=["FACT", "APPROVAL_REQUIRED"],
        ),
        policy=Policy(
            policy_id="forgegate_policy_nz_msp_v0.1",
            policy_hash="sha256_placeholder",
            retention_class=RetentionClass.AUDIT_7Y,
            legal_hold=False,
        ),
        control_tags=["NZISM.LOGGING", "SOC2.CC6.1"],
        integrity=Integrity(previous_hash=None, event_hash="placeholder"),
    )


def test_event_serialises_to_json():
    event = make_full_event()
    raw = canonical_json(event)
    parsed = json.loads(raw)
    assert parsed["event_id"] == "evt-test-001"
    assert parsed["event_type"] == "forgegate.decision_record"
    assert parsed["policy"]["retention_class"] == "audit_7y"
    assert parsed["integrity"]["previous_hash"] is None


def test_event_round_trip():
    event = make_full_event()
    restored = event_from_dict(json.loads(canonical_json(event)))
    assert restored.event_id == event.event_id
    assert restored.event_type == event.event_type
    assert restored.policy.retention_class == event.policy.retention_class
    assert restored.integrity.event_hash == event.integrity.event_hash
    assert len(restored.evidence.evidence_gaps) == 1
    assert restored.evidence.evidence_gaps[0].gap_type == "missing_approval"
    assert restored.evidence.evidence_gaps[0].blocking is True


def test_canonical_json_is_deterministic():
    event = make_full_event()
    assert canonical_json(event) == canonical_json(event)


def test_canonical_json_keys_are_sorted():
    event = make_full_event()
    raw = canonical_json(event)
    parsed = json.loads(raw)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_all_event_types_have_string_values():
    for et in EventType:
        assert isinstance(et.value, str)
        assert "." in et.value  # all types use dotted namespace


def test_all_retention_classes_have_string_values():
    for rc in RetentionClass:
        assert isinstance(rc.value, str)


def test_payload_none_round_trip():
    event = make_full_event()
    event_no_payload = event.__class__(
        **{**event.__dict__, "payload": None}
    )
    restored = event_from_dict(json.loads(canonical_json(event_no_payload)))
    assert restored.payload is None
