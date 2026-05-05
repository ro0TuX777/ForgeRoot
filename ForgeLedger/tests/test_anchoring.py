"""Phase 8a external checkpoint anchoring tests."""
import dataclasses
import json

from forgeledger.anchoring import AnchorRecord, LocalAnchorBackend
from forgeledger.backend import LedgerQuery
from forgeledger.checkpoint import CheckpointManager
from forgeledger.emitter import LedgerEmitter
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.schema import (
    LEDGER_VERSION,
    Actor,
    Decision,
    EventType,
    Evidence,
    Integrity,
    LedgerEvent,
    Policy,
    RetentionClass,
    SystemContext,
    Tenant,
)


SECRET_KEY = "anchor-test-secret"


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


def _checkpoint(tmp_path, event_count: int = 3):
    events = _make_chain(event_count)
    manager = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=event_count, secret_key=SECRET_KEY)
    checkpoint = manager.maybe_checkpoint(events)
    assert checkpoint is not None
    return checkpoint


def test_local_anchor_publishes_checkpoint_anchor(tmp_path):
    anchor_backend = LocalAnchorBackend(tmp_path / "anchors.jsonl")
    manager = CheckpointManager(
        tmp_path / "checkpoints.jsonl",
        interval=3,
        secret_key=SECRET_KEY,
        anchor_backend=anchor_backend,
    )

    manager.maybe_checkpoint(_make_chain(3))

    anchors = anchor_backend.load_anchors()
    assert len(anchors) == 1


def test_anchor_record_contains_checkpoint_id(tmp_path):
    checkpoint = _checkpoint(tmp_path)
    anchor = LocalAnchorBackend(tmp_path / "anchors.jsonl").publish_anchor(checkpoint)

    assert anchor.checkpoint_id == checkpoint.checkpoint_id


def test_anchor_record_contains_event_count(tmp_path):
    checkpoint = _checkpoint(tmp_path)
    anchor = LocalAnchorBackend(tmp_path / "anchors.jsonl").publish_anchor(checkpoint)

    assert anchor.event_count == checkpoint.event_count


def test_anchor_record_contains_latest_event_hash(tmp_path):
    checkpoint = _checkpoint(tmp_path)
    anchor = LocalAnchorBackend(tmp_path / "anchors.jsonl").publish_anchor(checkpoint)

    assert anchor.latest_event_hash == checkpoint.latest_event_hash


def test_anchor_file_is_append_only_jsonl(tmp_path):
    path = tmp_path / "anchors.jsonl"
    backend = LocalAnchorBackend(path)
    first = _checkpoint(tmp_path / "first")
    second = _checkpoint(tmp_path / "second")

    first_anchor = backend.publish_anchor(first)
    second_anchor = backend.publish_anchor(second)
    lines = path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["anchor_id"] == first_anchor.anchor_id
    assert json.loads(lines[1])["anchor_id"] == second_anchor.anchor_id
    assert first_anchor.anchor_id != second_anchor.anchor_id


def test_load_anchors_restores_anchor_records(tmp_path):
    path = tmp_path / "anchors.jsonl"
    checkpoint = _checkpoint(tmp_path)
    anchor = LocalAnchorBackend(path, secret_key=SECRET_KEY).publish_anchor(checkpoint)

    restored = LocalAnchorBackend(path, secret_key=SECRET_KEY).load_anchors()

    assert restored == [anchor]


def test_verify_anchor_passes_matching_checkpoint(tmp_path):
    backend = LocalAnchorBackend(tmp_path / "anchors.jsonl", secret_key=SECRET_KEY)
    checkpoint = _checkpoint(tmp_path)
    anchor = backend.publish_anchor(checkpoint)

    assert backend.verify_anchor(checkpoint, anchor) is True


def test_verify_anchor_fails_mismatched_latest_hash(tmp_path):
    backend = LocalAnchorBackend(tmp_path / "anchors.jsonl")
    checkpoint = _checkpoint(tmp_path)
    anchor = backend.publish_anchor(checkpoint)
    tampered = dataclasses.replace(checkpoint, latest_event_hash="0" * 64)

    assert backend.verify_anchor(tampered, anchor) is False


def test_verify_anchor_fails_mismatched_event_count(tmp_path):
    backend = LocalAnchorBackend(tmp_path / "anchors.jsonl")
    checkpoint = _checkpoint(tmp_path)
    anchor = backend.publish_anchor(checkpoint)
    tampered = dataclasses.replace(checkpoint, event_count=checkpoint.event_count + 1)

    assert backend.verify_anchor(tampered, anchor) is False


def test_verify_with_anchors_detects_missing_anchor_when_required(tmp_path):
    checkpoint = _checkpoint(tmp_path)

    report = CheckpointManager.verify_with_anchors([checkpoint], [], require_anchors=True)

    assert report.valid is False
    assert report.missing_anchors == [checkpoint.checkpoint_id]


def test_verify_with_anchors_detects_recomputed_checkpoint(tmp_path):
    backend = LocalAnchorBackend(tmp_path / "anchors.jsonl")
    checkpoint = _checkpoint(tmp_path)
    anchors = [backend.publish_anchor(checkpoint)]
    recomputed = dataclasses.replace(checkpoint, latest_event_hash="f" * 64)

    report = CheckpointManager.verify_with_anchors(
        [recomputed],
        anchors,
        anchor_backend=backend,
    )

    assert report.valid is False
    assert report.mismatched_anchors == [checkpoint.checkpoint_id]


def test_anchor_publish_emits_audit_event_if_audit_emitter_configured(tmp_path):
    audit_backend = JsonlBackend(tmp_path / "audit_ledger.jsonl")
    audit_emitter = LedgerEmitter(audit_backend)
    anchor_backend = LocalAnchorBackend(tmp_path / "anchors.jsonl", audit_emitter=audit_emitter)
    checkpoint = _checkpoint(tmp_path)

    anchor = anchor_backend.publish_anchor(checkpoint)
    audit_events = audit_backend.read_events(LedgerQuery(event_types=[EventType.LEDGER_ANCHOR_PUBLISHED.value]))

    assert len(audit_events) == 1
    assert audit_events[0].payload["anchor_id"] == anchor.anchor_id
    assert audit_events[0].payload["checkpoint_id"] == checkpoint.checkpoint_id
