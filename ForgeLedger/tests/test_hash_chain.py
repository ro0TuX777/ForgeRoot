"""
Phase 1 tests 1–5: hash-chain integrity properties.

1. Appending an event creates a deterministic event hash.
2. A valid hash chain passes validation.
3. Editing an event causes chain validation failure.
4. Deleting an event causes chain validation failure.
5. Reordering events causes chain validation failure.
"""
import dataclasses

from forgeledger.hash_chain import attach_integrity, compute_event_hash, verify_chain
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

def _make_event(event_id: str = "evt-001") -> LedgerEvent:
    return LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=EventType.CONCORD_ADMISSION_DECISION,
        event_time="2026-04-28T00:00:00Z",
        actor=Actor(actor_type="agent", actor_id="concord.admission", role="admission_engine"),
        tenant=Tenant(tenant_id="tenant-001", customer_boundary="b-a", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="policy_satisfied", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
        policy=Policy(policy_id="p-001", policy_hash="abc123", retention_class=RetentionClass.AUDIT_7Y),
        control_tags=["NZISM.LOGGING"],
        integrity=Integrity(previous_hash=None, event_hash=""),
    )


def _make_chain(n: int) -> list[LedgerEvent]:
    events = []
    prev_hash = None
    for i in range(n):
        e = attach_integrity(_make_event(f"evt-{i:03d}"), prev_hash)
        events.append(e)
        prev_hash = e.integrity.event_hash
    return events


# ---------------------------------------------------------------------------
# Test 1
# ---------------------------------------------------------------------------

def test_append_event_creates_deterministic_hash():
    """Same event input always produces the same event_hash."""
    e = attach_integrity(_make_event(), None)
    h1 = compute_event_hash(e)
    h2 = compute_event_hash(e)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest length


def test_different_events_produce_different_hashes():
    e1 = attach_integrity(_make_event("evt-001"), None)
    e2 = attach_integrity(_make_event("evt-002"), None)
    assert compute_event_hash(e1) != compute_event_hash(e2)


def test_changing_previous_hash_changes_event_hash():
    base = _make_event()
    e_no_prev  = attach_integrity(base, None)
    e_with_prev = attach_integrity(base, "deadbeef" * 8)
    assert e_no_prev.integrity.event_hash != e_with_prev.integrity.event_hash


# ---------------------------------------------------------------------------
# Test 2
# ---------------------------------------------------------------------------

def test_valid_chain_passes_validation():
    """An untampered chain of N events passes verification."""
    events = _make_chain(5)
    report = verify_chain(events)
    assert report.valid is True
    assert report.total_events == 5
    assert report.broken_at_sequence is None
    assert report.error is None


def test_empty_chain_passes_validation():
    report = verify_chain([])
    assert report.valid is True
    assert report.total_events == 0


def test_single_event_chain_passes_validation():
    events = _make_chain(1)
    report = verify_chain(events)
    assert report.valid is True


# ---------------------------------------------------------------------------
# Test 3
# ---------------------------------------------------------------------------

def test_tampered_event_fails_chain_validation():
    """Mutating any field of an event invalidates the chain at that position."""
    events = _make_chain(3)
    tampered_decision = dataclasses.replace(events[1].decision, reason="TAMPERED")
    events[1] = dataclasses.replace(events[1], decision=tampered_decision)
    report = verify_chain(events)
    assert report.valid is False
    assert report.broken_at_sequence == 1


def test_tampered_first_event_fails():
    events = _make_chain(3)
    tampered_actor = dataclasses.replace(events[0].actor, actor_id="ATTACKER")
    events[0] = dataclasses.replace(events[0], actor=tampered_actor)
    report = verify_chain(events)
    assert report.valid is False
    assert report.broken_at_sequence == 0


# ---------------------------------------------------------------------------
# Test 4
# ---------------------------------------------------------------------------

def test_deleted_event_fails_chain_validation():
    """Removing an event breaks the previous_hash link in the successor."""
    events = _make_chain(4)
    # Remove index 1; index 2's previous_hash now points to nothing valid
    events_with_gap = [events[0], events[2], events[3]]
    report = verify_chain(events_with_gap)
    assert report.valid is False


def test_deleted_last_event_does_not_affect_remainder():
    """Dropping the tail event doesn't break the remaining chain."""
    events = _make_chain(4)
    report = verify_chain(events[:-1])
    assert report.valid is True
    assert report.total_events == 3


# ---------------------------------------------------------------------------
# Test 5
# ---------------------------------------------------------------------------

def test_reordered_events_fail_chain_validation():
    """Swapping any two adjacent events breaks the previous_hash chain."""
    events = _make_chain(3)
    reordered = [events[1], events[0], events[2]]
    report = verify_chain(reordered)
    assert report.valid is False


def test_reversed_chain_fails_validation():
    events = _make_chain(4)
    report = verify_chain(list(reversed(events)))
    assert report.valid is False
