"""Phase 7a ingest-time redaction and signing tests."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from forgeledger.backend import LedgerQuery
from forgeledger.canonical_json import canonical_json
from forgeledger.emitter import LedgerEmitter
from forgeledger.hash_chain import attach_integrity
from forgeledger.jsonl_backend import JsonlBackend
from forgeledger.redaction import IngestRedactor
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
    event_from_dict,
)
from forgeledger.signing import sign_event, verify_signature
from forgeledger.validators import validate_event


RAW_PROMPT = "Customer Jane Doe NZBN 9429040000000 needs payroll help"
SECRET_KEY = "phase-7a-test-secret"
FIXED_REDACTED_AT = datetime(2026, 4, 29, 0, 0, 0, tzinfo=timezone.utc)


def _base_event(payload: dict | None = None) -> LedgerEvent:
    return LedgerEvent(
        event_id="evt-redaction-001",
        ledger_version=LEDGER_VERSION,
        event_type=EventType.WARDEN_LLM_CALL_METADATA,
        event_time="2026-04-29T00:00:00+00:00",
        actor=Actor(actor_type="agent", actor_id="warden.llm", role="llm_boundary"),
        tenant=Tenant(tenant_id="tenant-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="Warden", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="metadata_recorded", risk_level="medium"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["LLM_METADATA"]),
        policy=Policy(policy_id="p-001", policy_hash="abc123", retention_class=RetentionClass.AUDIT_7Y),
        control_tags=["NZISM.LOGGING"],
        integrity=Integrity(previous_hash=None, event_hash=""),
        payload=payload,
    )


def _sensitive_payload() -> dict:
    return {
        "prompt": RAW_PROMPT,
        "response": "Use documented payroll process.",
        "data_sensitivity": "llm_prompt_pii_suspected",
        "prompt_class": "customer_support",
        "response_class": "operational_guidance",
        "model_provider": "local-test-provider",
        "latency_ms": 42,
    }


def _emit_sensitive_event(path: Path, secret_key: str | None = None) -> tuple[JsonlBackend, Path]:
    backend = JsonlBackend(path)
    emitter = LedgerEmitter(
        backend,
        redactor=IngestRedactor(now_factory=lambda: FIXED_REDACTED_AT),
        secret_key=secret_key,
    )
    emitter.emit(
        event_type=EventType.WARDEN_LLM_CALL_METADATA,
        actor=Actor(actor_type="agent", actor_id="warden.llm", role="llm_boundary"),
        tenant=Tenant(tenant_id="tenant-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="Warden", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="metadata_recorded", risk_level="medium"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["LLM_METADATA"]),
        policy_id="p-001",
        policy_hash="abc123",
        control_tags=["NZISM.LOGGING"],
        payload=_sensitive_payload(),
    )
    return backend, path


def _read_all(backend: JsonlBackend) -> list[LedgerEvent]:
    return backend.read_events(LedgerQuery(max_results=100))


def test_sensitive_event_is_redacted_before_append():
    event = _base_event(_sensitive_payload())
    redacted = IngestRedactor(now_factory=lambda: FIXED_REDACTED_AT).redact(event)

    assert redacted.payload["prompt"].startswith("[REDACTED:sha256:")
    assert redacted.payload["response"].startswith("[REDACTED:sha256:")
    assert redacted.payload["prompt_class"] == "customer_support"
    assert redacted.payload["model_provider"] == "local-test-provider"
    assert redacted.payload["latency_ms"] == 42


def test_redaction_receipt_contains_sha256_of_original():
    event = _base_event(_sensitive_payload())
    redacted = IngestRedactor(now_factory=lambda: FIXED_REDACTED_AT).redact(event)
    receipt = next(r for r in redacted.redaction_receipts if r.field_path == "payload.prompt")

    assert receipt.sha256_of_original == hashlib.sha256(RAW_PROMPT.encode("utf-8")).hexdigest()
    assert receipt.redacted_at == FIXED_REDACTED_AT.isoformat()


def test_raw_prompt_never_enters_jsonl(tmp_path):
    _, ledger_path = _emit_sensitive_event(tmp_path / "ledger.jsonl")

    raw = ledger_path.read_text(encoding="utf-8")
    assert RAW_PROMPT not in raw
    assert "[REDACTED:sha256:" in raw


def test_non_sensitive_event_is_unchanged():
    payload = {"prompt": RAW_PROMPT, "data_sensitivity": "public"}
    event = _base_event(payload)
    redacted = IngestRedactor(now_factory=lambda: FIXED_REDACTED_AT).redact(event)

    assert redacted is event
    assert redacted.payload == payload
    assert redacted.redaction_receipts == []


def test_redacted_event_still_passes_schema_validation():
    redacted = IngestRedactor(now_factory=lambda: FIXED_REDACTED_AT).redact(
        _base_event(_sensitive_payload())
    )
    final = attach_integrity(redacted, None)

    assert validate_event(final) == []
    restored = event_from_dict(json.loads(canonical_json(final)))
    assert validate_event(restored) == []


def test_redaction_before_hashing_chain_verifies_stored_event(tmp_path):
    backend, _ = _emit_sensitive_event(tmp_path / "ledger.jsonl")

    report = backend.verify_chain()
    events = _read_all(backend)

    assert report.valid is True
    assert events[0].payload["prompt"].startswith("[REDACTED:sha256:")


def test_emitter_with_redactor_stores_redacted_event(tmp_path):
    backend, _ = _emit_sensitive_event(tmp_path / "ledger.jsonl")
    events = _read_all(backend)

    assert events[0].payload["redaction_applied"] is True
    assert events[0].redaction_receipts


def test_emitter_with_redactor_raw_value_absent_from_backend(tmp_path):
    backend, _ = _emit_sensitive_event(tmp_path / "ledger.jsonl")
    stored = json.dumps(json.loads(canonical_json(_read_all(backend)[0])))

    assert RAW_PROMPT not in stored


def test_emitter_signs_event_when_key_provided(tmp_path):
    backend, _ = _emit_sensitive_event(tmp_path / "ledger.jsonl", secret_key=SECRET_KEY)
    event = _read_all(backend)[0]

    assert event.integrity.signature is not None


def test_emitter_event_signature_is_verifiable_with_public_key(tmp_path):
    backend, _ = _emit_sensitive_event(tmp_path / "ledger.jsonl", secret_key=SECRET_KEY)
    event = _read_all(backend)[0]

    assert verify_signature(event, SECRET_KEY) is True


def test_emitter_redaction_then_signing_order_is_deterministic():
    redactor = IngestRedactor(now_factory=lambda: FIXED_REDACTED_AT)
    provisional = _base_event(_sensitive_payload())

    signed_once = sign_event(attach_integrity(redactor.redact(provisional), None), SECRET_KEY)
    signed_twice = sign_event(attach_integrity(redactor.redact(provisional), None), SECRET_KEY)

    assert signed_once.integrity.event_hash == signed_twice.integrity.event_hash
    assert signed_once.integrity.signature == signed_twice.integrity.signature
    assert signed_once.payload["prompt"] == signed_twice.payload["prompt"]
