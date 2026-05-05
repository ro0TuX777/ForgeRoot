"""Validator hardening tests for Phase 7a redaction metadata."""
import dataclasses

from forgeledger.hash_chain import attach_integrity
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
)
from forgeledger.signing import sign_event
from forgeledger.validators import validate_event


RAW_PROMPT = "Customer Jane Doe NZBN 9429040000000 needs payroll help"


def _event(payload: dict | None = None) -> LedgerEvent:
    return LedgerEvent(
        event_id="evt-validator-001",
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


def _valid_redacted_event() -> LedgerEvent:
    redacted = IngestRedactor().redact(_event(_sensitive_payload()))
    return attach_integrity(redacted, None)


def test_validator_accepts_valid_redaction_receipts():
    event = _valid_redacted_event()

    assert validate_event(event) == []


def test_validator_rejects_receipt_missing_field_path():
    event = _valid_redacted_event()
    receipt = dataclasses.replace(event.redaction_receipts[0], field_path="")
    event = dataclasses.replace(event, redaction_receipts=[receipt])

    assert "redaction_receipts[0].field_path is required" in validate_event(event)


def test_validator_rejects_non_hex_receipt_hash():
    event = _valid_redacted_event()
    receipt = dataclasses.replace(event.redaction_receipts[0], sha256_of_original="not-hex")
    event = dataclasses.replace(event, redaction_receipts=[receipt])

    assert "redaction_receipts[0].sha256_of_original must be 64 lowercase hex chars" in validate_event(event)


def test_validator_rejects_invalid_redacted_at_timestamp():
    event = _valid_redacted_event()
    receipt = dataclasses.replace(event.redaction_receipts[0], redacted_at="not-a-time")
    event = dataclasses.replace(event, redaction_receipts=[receipt])

    assert "redaction_receipts[0].redacted_at must be valid ISO-8601" in validate_event(event)


def test_validator_accepts_signature_shape_when_present():
    event = sign_event(_valid_redacted_event(), "validator-secret")

    assert validate_event(event) == []


def test_validator_rejects_invalid_signature_shape():
    event = _valid_redacted_event()
    event = dataclasses.replace(
        event,
        integrity=dataclasses.replace(event.integrity, signature="not-a-valid-hmac"),
    )

    assert "integrity.signature must be 64 lowercase hex chars when present" in validate_event(event)


def test_validator_rejects_redacted_marker_without_matching_receipt():
    event = _valid_redacted_event()
    event = dataclasses.replace(event, redaction_receipts=[])

    errors = validate_event(event)
    assert "payload.prompt has redacted marker without matching redaction receipt" in errors


def test_validator_rejects_receipt_without_redacted_payload_marker():
    event = _valid_redacted_event()
    payload = dict(event.payload or {})
    payload["prompt"] = RAW_PROMPT
    event = dataclasses.replace(event, payload=payload)

    errors = validate_event(event)
    assert "payload.prompt has redaction receipt without matching redacted payload marker" in errors
