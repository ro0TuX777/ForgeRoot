"""
Integration tests for the JsonlBackend (append, read, chain, holds).
All tests use tmp_path so no shared state.
"""
from pathlib import Path

from forgeledger.backend import HoldSelector, LedgerQuery
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
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
        actor=Actor(actor_type="agent", actor_id="test.agent", role="test"),
        tenant=Tenant(tenant_id="tenant-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="test", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
        policy=Policy(policy_id="p-001", policy_hash="abcdef", retention_class=RetentionClass.AUDIT_7Y),
        control_tags=["NZISM.LOGGING"],
        integrity=Integrity(previous_hash=None, event_hash=""),
    )


def _fill_backend(backend: JsonlBackend, n: int) -> list[LedgerEvent]:
    events = []
    prev_hash = None
    for i in range(n):
        e = attach_integrity(_make_event(f"evt-{i:03d}"), prev_hash)
        backend.append_event(e)
        events.append(e)
        prev_hash = e.integrity.event_hash
    return events


# ---------------------------------------------------------------------------
# Basic append / read
# ---------------------------------------------------------------------------

def test_append_and_read(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    e = attach_integrity(_make_event("evt-001"), None)
    result = backend.append_event(e)

    assert result.success is True
    assert result.event_id == "evt-001"
    assert result.sequence_number == 0

    events = backend.read_events(LedgerQuery())
    assert len(events) == 1
    assert events[0].event_id == "evt-001"


def test_append_multiple_and_read_all(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    _fill_backend(backend, 5)

    events = backend.read_events(LedgerQuery())
    assert len(events) == 5


def test_read_empty_ledger(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    assert backend.read_events(LedgerQuery()) == []


def test_read_filter_by_event_type(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    _fill_backend(backend, 3)

    events = backend.read_events(LedgerQuery(
        event_types=["concord.admission_decision"]
    ))
    assert len(events) == 3

    events_none = backend.read_events(LedgerQuery(
        event_types=["forgegate.decision_record"]
    ))
    assert len(events_none) == 0


def test_read_respects_max_results(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    _fill_backend(backend, 10)

    events = backend.read_events(LedgerQuery(max_results=4))
    assert len(events) == 4


# ---------------------------------------------------------------------------
# Hash chain via backend
# ---------------------------------------------------------------------------

def test_hash_chain_validates_after_appends(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    _fill_backend(backend, 4)

    report = backend.verify_chain()
    assert report.valid is True
    assert report.total_events == 4


def test_get_latest_hash_empty(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    assert backend.get_latest_hash() is None


def test_get_latest_hash_matches_last_event(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    events = _fill_backend(backend, 3)
    assert backend.get_latest_hash() == events[-1].integrity.event_hash


def test_sequence_numbers_increment(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    r0 = backend.append_event(attach_integrity(_make_event("e0"), None))
    prev = r0.event_hash
    e1 = attach_integrity(_make_event("e1"), prev)
    r1 = backend.append_event(e1)

    assert r0.sequence_number == 0
    assert r1.sequence_number == 1


# ---------------------------------------------------------------------------
# Legal hold via backend
# ---------------------------------------------------------------------------

def test_backend_legal_hold_applied(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    e = attach_integrity(_make_event("evt-hold-001"), None)
    backend.append_event(e)

    result = backend.apply_legal_hold(
        HoldSelector(tenant_id="tenant-001", reason="test_hold", event_ids=["evt-hold-001"])
    )
    assert result.applied_count == 1
    assert result.error is None
    assert backend.is_on_hold("evt-hold-001")
    assert not backend.is_on_hold("evt-other-999")


def test_backend_hold_released(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    e = attach_integrity(_make_event("evt-001"), None)
    backend.append_event(e)

    hold_result = backend.apply_legal_hold(
        HoldSelector(tenant_id="tenant-001", reason="hold", event_ids=["evt-001"])
    )
    assert backend.is_on_hold("evt-001")

    release = backend.release_legal_hold(hold_result.hold_id, reason="closed")
    assert release.error is None
    assert not backend.is_on_hold("evt-001")


def test_holds_persist_across_backend_instances(tmp_path: Path):
    """Holds in the sidecar file survive backend re-instantiation."""
    path = tmp_path / "ledger.jsonl"
    b1 = JsonlBackend(path)
    e = attach_integrity(_make_event("evt-001"), None)
    b1.append_event(e)
    b1.apply_legal_hold(HoldSelector(tenant_id="t1", reason="r", event_ids=["evt-001"]))

    b2 = JsonlBackend(path)
    assert b2.is_on_hold("evt-001")


# ---------------------------------------------------------------------------
# Export slice
# ---------------------------------------------------------------------------

def test_export_slice_returns_all_events(tmp_path: Path):
    from forgeledger.backend import ExportSelector
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    _fill_backend(backend, 3)

    result = backend.export_slice(ExportSelector())
    assert result["event_count"] == 3
    assert result["chain_valid"] is True
    assert len(result["events"]) == 3


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_check_returns_healthy(tmp_path: Path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    health = backend.health_check()
    assert health["healthy"] is True
