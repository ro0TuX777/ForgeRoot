"""
Phase 4 tests:
1. Backend interface contract — all backends satisfy LedgerBackend.
2. Write failure fails closed — emitter raises LedgerWriteFailedError.
3. Export/import preserves chain integrity.
4. WORM backend rejects mutation where supported.
"""
import pytest

from forgeledger.backend import (
    AppendResult,
    ExportSelector,
    HoldSelector,
    LedgerBackend,
    LedgerQuery,
)
from forgeledger.emitter import LedgerEmitter, LedgerWriteFailedError
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
from forgeledger.worm_backend import WormBackend, WormViolationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_id: str = "evt-001") -> LedgerEvent:
    return LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=EventType.CONCORD_ADMISSION_DECISION,
        event_time="2026-04-29T10:00:00Z",
        actor=Actor(actor_type="agent", actor_id="test.agent", role="test"),
        tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="test", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
        policy=Policy(policy_id="p-001", policy_hash="abc", retention_class=RetentionClass.AUDIT_7Y),
        control_tags=[],
        integrity=Integrity(previous_hash=None, event_hash=""),
    )


def _chain_and_append(backend: LedgerBackend, count: int = 3) -> list[LedgerEvent]:
    """Append `count` events forming a valid chain to `backend`."""
    events: list[LedgerEvent] = []
    prev_hash = None
    for i in range(count):
        e = attach_integrity(_make_event(f"evt-{i:03d}"), prev_hash)
        backend.append_event(e)
        events.append(e)
        prev_hash = e.integrity.event_hash
    return events


# ---------------------------------------------------------------------------
# Test 1: Backend interface contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("backend_cls", [JsonlBackend, WormBackend])
def test_backend_is_subclass_of_ledger_backend(backend_cls):
    assert issubclass(backend_cls, LedgerBackend)


@pytest.mark.parametrize("backend_cls", [JsonlBackend, WormBackend])
def test_backend_implements_all_abstract_methods(tmp_path, backend_cls):
    """Instantiation would raise TypeError if any abstract method is missing."""
    path = tmp_path / f"{backend_cls.__name__.lower()}.jsonl"
    backend = backend_cls(path)
    assert backend is not None


@pytest.mark.parametrize("backend_cls", [JsonlBackend, WormBackend])
def test_backend_append_and_read(tmp_path, backend_cls):
    path = tmp_path / "ledger.jsonl"
    backend = backend_cls(path)
    events = _chain_and_append(backend, 2)

    result = backend.read_events(LedgerQuery())
    assert len(result) == 2
    assert result[0].event_id == events[0].event_id


@pytest.mark.parametrize("backend_cls", [JsonlBackend, WormBackend])
def test_backend_verify_chain_on_clean_ledger(tmp_path, backend_cls):
    path = tmp_path / "ledger.jsonl"
    backend = backend_cls(path)
    _chain_and_append(backend, 3)

    report = backend.verify_chain()
    assert report.valid is True
    assert report.total_events == 3


@pytest.mark.parametrize("backend_cls", [JsonlBackend, WormBackend])
def test_backend_health_check_returns_healthy(tmp_path, backend_cls):
    path = tmp_path / "ledger.jsonl"
    backend = backend_cls(path)
    _chain_and_append(backend, 1)

    result = backend.health_check()
    assert result["healthy"] is True
    assert "backend_type" in result
    assert result["event_count"] == 1


def test_worm_health_check_reports_immutable(tmp_path):
    backend = WormBackend(tmp_path / "ledger.jsonl")
    result = backend.health_check()
    assert result.get("immutable") is True
    assert result["backend_type"] == "worm"


# ---------------------------------------------------------------------------
# Test 2: Write failure fails closed
# ---------------------------------------------------------------------------

class _AlwaysFailBackend(JsonlBackend):
    """Test double that always rejects append_event."""

    def append_event(self, event: LedgerEvent) -> AppendResult:
        return AppendResult(
            success=False,
            event_id=event.event_id,
            event_hash=event.integrity.event_hash,
            sequence_number=0,
            error="simulated disk failure",
        )


def test_emitter_raises_on_write_failure(tmp_path):
    backend = _AlwaysFailBackend(tmp_path / "ledger.jsonl")
    emitter = LedgerEmitter(backend)

    with pytest.raises(LedgerWriteFailedError) as exc_info:
        emitter.emit(
            event_type=EventType.CONCORD_ADMISSION_DECISION,
            actor=Actor(actor_type="agent", actor_id="test.agent", role="test"),
            tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
            system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
            decision=Decision(decision_type="allow", reason="test", risk_level="low"),
            evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=[]),
            policy_id="p-001",
            policy_hash="abc",
            control_tags=[],
        )

    assert "simulated disk failure" in str(exc_info.value)


def test_write_failure_error_carries_backend_message(tmp_path):
    backend = _AlwaysFailBackend(tmp_path / "ledger.jsonl")
    emitter = LedgerEmitter(backend)

    try:
        emitter.emit(
            event_type=EventType.FORGEGATE_DECISION_RECORD,
            actor=Actor(actor_type="system", actor_id="gate", role="policy"),
            tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
            system_context=SystemContext(source_module="ForgeGate", environment="local", deployment_id="test"),
            decision=Decision(decision_type="deny", reason="test", risk_level="high"),
            evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=[]),
            policy_id="p-001",
            policy_hash="abc",
            control_tags=[],
        )
        pytest.fail("Expected LedgerWriteFailedError")
    except LedgerWriteFailedError as exc:
        assert exc.backend_error == "simulated disk failure"


def test_successful_emit_does_not_raise(tmp_path):
    backend = JsonlBackend(tmp_path / "ledger.jsonl")
    emitter = LedgerEmitter(backend)

    result = emitter.emit(
        event_type=EventType.CONCORD_ADMISSION_DECISION,
        actor=Actor(actor_type="agent", actor_id="test.agent", role="test"),
        tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="test", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=[]),
        policy_id="p-001",
        policy_hash="abc",
        control_tags=[],
    )
    assert result.success is True


# ---------------------------------------------------------------------------
# Test 3: Export/import preserves chain integrity
# ---------------------------------------------------------------------------

def test_import_slice_preserves_chain(tmp_path):
    backend_a = JsonlBackend(tmp_path / "a.jsonl")
    _chain_and_append(backend_a, 3)

    slice_data = backend_a.export_slice(ExportSelector())
    assert slice_data["chain_valid"] is True

    backend_b = JsonlBackend(tmp_path / "b.jsonl")
    import_result = backend_b.import_slice(slice_data)

    assert import_result["imported_count"] == 3
    assert import_result["chain_valid_after_import"] is True
    assert import_result["errors"] == []


def test_imported_chain_validates_in_target(tmp_path):
    backend_a = JsonlBackend(tmp_path / "a.jsonl")
    events_a = _chain_and_append(backend_a, 3)

    slice_data = backend_a.export_slice(ExportSelector())
    backend_b = JsonlBackend(tmp_path / "b.jsonl")
    backend_b.import_slice(slice_data)

    report = backend_b.verify_chain()
    assert report.valid is True
    assert report.total_events == 3
    assert report.first_event_id == events_a[0].event_id
    assert report.last_event_id == events_a[-1].event_id


def test_import_slice_events_match_original(tmp_path):
    backend_a = JsonlBackend(tmp_path / "a.jsonl")
    events_a = _chain_and_append(backend_a, 3)

    slice_data = backend_a.export_slice(ExportSelector())
    backend_b = JsonlBackend(tmp_path / "b.jsonl")
    backend_b.import_slice(slice_data)

    events_b = backend_b.read_events(LedgerQuery())
    assert len(events_b) == len(events_a)
    for ea, eb in zip(events_a, events_b):
        assert ea.event_id == eb.event_id
        assert ea.integrity.event_hash == eb.integrity.event_hash


def test_import_slice_rejects_corrupt_slice(tmp_path):
    backend_a = JsonlBackend(tmp_path / "a.jsonl")
    _chain_and_append(backend_a, 2)

    slice_data = backend_a.export_slice(ExportSelector())
    # corrupt: reverse event order so chain breaks
    slice_data["events"] = list(reversed(slice_data["events"]))

    backend_b = JsonlBackend(tmp_path / "b.jsonl")
    result = backend_b.import_slice(slice_data)

    assert result["imported_count"] == 0
    assert result["chain_valid_after_import"] is False
    assert result["errors"]


# ---------------------------------------------------------------------------
# Test 4: WORM backend rejects mutation
# ---------------------------------------------------------------------------

def test_worm_rejects_release_legal_hold(tmp_path):
    backend = WormBackend(tmp_path / "ledger.jsonl")
    _chain_and_append(backend, 2)

    hold_result = backend.apply_legal_hold(
        HoldSelector(tenant_id="t-001", reason="regulatory_investigation")
    )
    assert hold_result.applied_count == 2

    with pytest.raises(WormViolationError):
        backend.release_legal_hold(hold_result.hold_id, "case_closed")


def test_worm_chain_stays_valid_after_failed_release(tmp_path):
    backend = WormBackend(tmp_path / "ledger.jsonl")
    _chain_and_append(backend, 2)

    hold_result = backend.apply_legal_hold(
        HoldSelector(tenant_id="t-001", reason="regulatory_investigation")
    )

    try:
        backend.release_legal_hold(hold_result.hold_id, "case_closed")
    except WormViolationError:
        pass

    report = backend.verify_chain()
    assert report.valid is True


def test_worm_allows_append_after_hold(tmp_path):
    """Applying a hold must not block further appends — events are still written."""
    backend = WormBackend(tmp_path / "ledger.jsonl")
    events = _chain_and_append(backend, 2)

    backend.apply_legal_hold(HoldSelector(tenant_id="t-001", reason="test"))

    # Append a third event after the hold
    e3 = attach_integrity(_make_event("evt-003"), events[-1].integrity.event_hash)
    result = backend.append_event(e3)
    assert result.success is True

    report = backend.verify_chain()
    assert report.valid is True
    assert report.total_events == 3


def test_worm_violation_error_message_contains_hold_id(tmp_path):
    backend = WormBackend(tmp_path / "ledger.jsonl")
    _chain_and_append(backend, 1)

    hold = backend.apply_legal_hold(HoldSelector(tenant_id="t-001", reason="test"))

    with pytest.raises(WormViolationError, match=hold.hold_id):
        backend.release_legal_hold(hold.hold_id, "reason")
