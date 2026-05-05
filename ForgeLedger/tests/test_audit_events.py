"""Phase 7d ledger governance audit event tests."""
from pathlib import Path

from forgeledger.backend import LedgerQuery
from forgeledger.checkpoint import CheckpointManager
from forgeledger.emitter import LedgerEmitter
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.redaction import IngestRedactor
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


def _audit_emitter(path: Path) -> tuple[JsonlBackend, LedgerEmitter]:
    backend = JsonlBackend(path)
    return backend, LedgerEmitter(backend)


def _emit_sensitive_event(primary: JsonlBackend, audit_emitter: LedgerEmitter | None = None):
    emitter = LedgerEmitter(primary, redactor=IngestRedactor(), audit_emitter=audit_emitter)
    emitter.emit(
        event_type=EventType.WARDEN_LLM_CALL_METADATA,
        actor=Actor(actor_type="system", actor_id="warden.llm", role="llm_gateway"),
        tenant=Tenant(tenant_id="tenant-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="Warden", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="recorded", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["LLM_METADATA"]),
        policy_id="p-001",
        policy_hash="abc",
        control_tags=["NZISM.LOGGING.EVENT_CAPTURE"],
        payload={
            "prompt": "Customer Jane Doe NZBN 9429040000000 needs payroll help",
            "response": "Use documented payroll process.",
            "data_sensitivity": "llm_prompt_pii_suspected",
            "prompt_class": "support",
            "response_class": "answer",
            "model_provider": "local",
        },
    )


def _make_chain(count: int) -> list[LedgerEvent]:
    events: list[LedgerEvent] = []
    previous_hash = None
    for index in range(count):
        event = LedgerEvent(
            event_id=f"evt-{index:03d}",
            ledger_version=LEDGER_VERSION,
            event_type=EventType.CONCORD_ADMISSION_DECISION,
            event_time="2026-04-29T00:00:00Z",
            actor=Actor(actor_type="agent", actor_id="concord", role="admission"),
            tenant=Tenant(tenant_id="tenant-001", customer_boundary="b", data_residency="NZ"),
            system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
            decision=Decision(decision_type="allow", reason="ok", risk_level="low"),
            evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
            policy=Policy(policy_id="p-001", policy_hash="abc", retention_class=RetentionClass.AUDIT_7Y),
            control_tags=[],
            integrity=Integrity(previous_hash=None, event_hash=""),
        )
        final = attach_integrity(event, previous_hash)
        events.append(final)
        previous_hash = final.integrity.event_hash
    return events


def _read_all(backend: JsonlBackend):
    return backend.read_events(LedgerQuery(max_results=100))


def test_redaction_emits_ledger_redaction_applied_event_to_audit_emitter(tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path / "audit.jsonl")
    _emit_sensitive_event(JsonlBackend(tmp_path / "primary.jsonl"), audit)

    assert _read_all(audit_backend)[0].event_type == EventType.LEDGER_REDACTION_APPLIED


def test_redaction_audit_event_contains_original_event_id(tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path / "audit.jsonl")
    _emit_sensitive_event(JsonlBackend(tmp_path / "primary.jsonl"), audit)

    assert _read_all(audit_backend)[0].payload["original_event_id"]


def test_redaction_audit_event_contains_field_receipts(tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path / "audit.jsonl")
    _emit_sensitive_event(JsonlBackend(tmp_path / "primary.jsonl"), audit)

    payload = _read_all(audit_backend)[0].payload
    assert "payload.prompt" in payload["fields_redacted"]
    assert payload["redaction_receipts"]


def test_redaction_audit_event_references_primary_event_hash_when_available(tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path / "audit.jsonl")
    _emit_sensitive_event(JsonlBackend(tmp_path / "primary.jsonl"), audit)

    payload = _read_all(audit_backend)[0].payload
    assert payload["primary_event_hash"]
    assert payload["original_event_hash"] == payload["primary_event_hash"]


def test_no_audit_event_when_no_audit_emitter_provided(tmp_path):
    audit_backend = JsonlBackend(tmp_path / "audit.jsonl")
    _emit_sensitive_event(JsonlBackend(tmp_path / "primary.jsonl"), None)

    assert _read_all(audit_backend) == []


def test_checkpoint_emits_ledger_checkpoint_created_event_to_audit_emitter(tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path / "audit.jsonl")
    CheckpointManager(tmp_path / "checkpoints.jsonl", interval=2, audit_emitter=audit).maybe_checkpoint(_make_chain(2))

    assert _read_all(audit_backend)[0].event_type == EventType.LEDGER_CHECKPOINT_CREATED


def test_checkpoint_audit_event_contains_checkpoint_id_and_hash(tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path / "audit.jsonl")
    checkpoint = CheckpointManager(
        tmp_path / "checkpoints.jsonl",
        interval=2,
        secret_key="secret",
        audit_emitter=audit,
    ).maybe_checkpoint(_make_chain(2))

    payload = _read_all(audit_backend)[0].payload
    assert payload["checkpoint_id"] == checkpoint.checkpoint_id
    assert payload["checkpoint_signature_present"] is True


def test_checkpoint_audit_event_contains_latest_event_hash(tmp_path):
    audit_backend, audit = _audit_emitter(tmp_path / "audit.jsonl")
    checkpoint = CheckpointManager(tmp_path / "checkpoints.jsonl", interval=2, audit_emitter=audit).maybe_checkpoint(_make_chain(2))

    assert _read_all(audit_backend)[0].payload["latest_event_hash"] == checkpoint.latest_event_hash


def test_no_checkpoint_audit_event_when_no_audit_emitter_provided(tmp_path):
    audit_backend = JsonlBackend(tmp_path / "audit.jsonl")
    CheckpointManager(tmp_path / "checkpoints.jsonl", interval=2).maybe_checkpoint(_make_chain(2))

    assert _read_all(audit_backend) == []
