"""Phase 7b checkpoint tests."""
import dataclasses
import json

from forgeledger.checkpoint import ChainCheckpoint, CheckpointManager
from forgeledger.hash_chain import attach_integrity, verify_chain
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


SECRET_KEY = "checkpoint-test-secret"


def _make_event(event_id: str = "evt-001", reason: str = "policy_satisfied") -> LedgerEvent:
    return LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=EventType.CONCORD_ADMISSION_DECISION,
        event_time="2026-04-29T00:00:00Z",
        actor=Actor(actor_type="agent", actor_id="concord.admission", role="admission_engine"),
        tenant=Tenant(tenant_id="tenant-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason=reason, risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
        policy=Policy(policy_id="p-001", policy_hash="abc123", retention_class=RetentionClass.AUDIT_7Y),
        control_tags=["NZISM.LOGGING"],
        integrity=Integrity(previous_hash=None, event_hash=""),
    )


def _make_chain(n: int) -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    previous_hash = None
    for index in range(n):
        event = attach_integrity(_make_event(f"evt-{index:03d}"), previous_hash)
        events.append(event)
        previous_hash = event.integrity.event_hash
    return events


def _recompute_chain(events: list[LedgerEvent]) -> list[LedgerEvent]:
    recomputed: list[LedgerEvent] = []
    previous_hash = None
    for event in events:
        event_without_integrity = dataclasses.replace(
            event,
            integrity=Integrity(previous_hash=None, event_hash="", signature=None),
        )
        final = attach_integrity(event_without_integrity, previous_hash)
        recomputed.append(final)
        previous_hash = final.integrity.event_hash
    return recomputed


def test_checkpoint_written_at_interval_boundary(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3)

    checkpoint = manager.maybe_checkpoint(_make_chain(3))

    assert checkpoint is not None
    assert len(manager.load_checkpoints()) == 1


def test_checkpoint_not_written_before_interval(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3)

    checkpoint = manager.maybe_checkpoint(_make_chain(2))

    assert checkpoint is None
    assert manager.load_checkpoints() == []


def test_checkpoint_contains_correct_event_count(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3)
    checkpoint = manager.maybe_checkpoint(_make_chain(3))

    assert checkpoint is not None
    assert checkpoint.event_count == 3


def test_checkpoint_contains_latest_event_hash(tmp_path):
    events = _make_chain(3)
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3)

    checkpoint = manager.maybe_checkpoint(events)

    assert checkpoint is not None
    assert checkpoint.latest_event_hash == events[-1].integrity.event_hash


def test_checkpoint_signature_is_valid_with_secret_key(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3, secret_key=SECRET_KEY)
    checkpoint = manager.maybe_checkpoint(_make_chain(3))

    assert checkpoint is not None
    assert checkpoint.signature is not None
    assert len(checkpoint.signature) == 64
    assert CheckpointManager.verify_with_checkpoints(
        _make_chain(3),
        [checkpoint],
        secret_key=SECRET_KEY,
    ).signature_failures == 0


def test_checkpoint_unsigned_when_no_secret_key(tmp_path):
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3)
    checkpoint = manager.maybe_checkpoint(_make_chain(3))

    assert checkpoint is not None
    assert checkpoint.signature is None


def test_verify_passes_valid_chain_and_checkpoints(tmp_path):
    events = _make_chain(6)
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3, secret_key=SECRET_KEY)
    cp1 = manager.maybe_checkpoint(events[:3])
    cp2 = manager.maybe_checkpoint(events[:6])

    report = CheckpointManager.verify_with_checkpoints(events, [cp1, cp2], secret_key=SECRET_KEY)

    assert report.valid is True
    assert report.tail_truncation_detected is False
    assert report.recomputation_detected is False


def test_tail_truncation_detected_when_events_fewer_than_last_checkpoint(tmp_path):
    events = _make_chain(6)
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3)
    checkpoint = manager.maybe_checkpoint(events)
    truncated = events[:5]

    assert verify_chain(truncated).valid is True
    report = CheckpointManager.verify_with_checkpoints(truncated, [checkpoint])

    assert report.valid is False
    assert report.tail_truncation_detected is True


def test_recomputation_detected_when_chain_rebuilt_after_checkpoint(tmp_path):
    original = _make_chain(6)
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3)
    checkpoint = manager.maybe_checkpoint(original[:3])

    tampered = list(original)
    tampered[1] = dataclasses.replace(
        tampered[1],
        decision=dataclasses.replace(tampered[1].decision, reason="tampered_but_recomputed"),
    )
    recomputed = _recompute_chain(tampered)

    assert verify_chain(recomputed).valid is True
    report = CheckpointManager.verify_with_checkpoints(recomputed, [checkpoint])

    assert report.valid is False
    assert report.recomputation_detected is True


def test_signature_failure_reported_for_tampered_checkpoint(tmp_path):
    events = _make_chain(3)
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=3, secret_key=SECRET_KEY)
    checkpoint = manager.maybe_checkpoint(events)
    tampered = dataclasses.replace(checkpoint, latest_event_hash="0" * 64)

    report = CheckpointManager.verify_with_checkpoints(events, [tampered], secret_key=SECRET_KEY)

    assert report.valid is False
    assert report.signature_failures == 1


def test_load_checkpoints_restores_persisted_state(tmp_path):
    path = tmp_path / "checkpoints.jsonl"
    manager = CheckpointManager(path, interval=3, secret_key=SECRET_KEY)
    checkpoint = manager.maybe_checkpoint(_make_chain(3))

    restored = CheckpointManager(path, interval=3, secret_key=SECRET_KEY).load_checkpoints()

    assert restored == [checkpoint]


def test_checkpoint_file_is_append_only(tmp_path):
    path = tmp_path / "checkpoints.jsonl"
    manager = CheckpointManager(path, interval=3)
    first = manager.maybe_checkpoint(_make_chain(3))
    second = manager.maybe_checkpoint(_make_chain(6))

    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["checkpoint_id"] == first.checkpoint_id
    assert json.loads(lines[1])["checkpoint_id"] == second.checkpoint_id
    assert first.checkpoint_id != second.checkpoint_id
