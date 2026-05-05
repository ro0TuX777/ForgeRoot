from forgeledger.schema import EventType
from forgeledger.validators import validate_event
from integrations.types import WardenCallRecord
from integrations.warden_ledger_adapter import WardenLedgerAdapter, warden_runtime_output_to_call_record


RAW_PROMPT = "Customer Jane Doe NZBN 9429040000000 needs payroll help"
RAW_RESPONSE = "Use documented payroll process."


def _record(**overrides):
    data = dict(
        actor_id="warden.llm_gateway",
        decision_type="allow",
        reason="llm_call_within_policy",
        risk_level="low",
        tenant_id="tenant-001",
        customer_boundary="customer-a",
        data_residency="NZ",
        policy_id="warden-policy",
        policy_hash="hash",
        prompt=RAW_PROMPT,
        response=RAW_RESPONSE,
        data_sensitivity="llm_prompt_pii_suspected",
        prompt_class="design_query",
        response_class="technical_recommendation",
        model_provider="anthropic",
        latency_ms=123,
        frameworks=["NZISM", "SOC2"],
    )
    data.update(overrides)
    return WardenCallRecord(**data)


def test_warden_adapter_emits_llm_call_metadata_event_type(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record())
    assert event.event_type == EventType.WARDEN_LLM_CALL_METADATA


def test_warden_adapter_model_provider_in_payload(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record())
    assert event.payload["model_provider"] == "anthropic"


def test_warden_adapter_pii_suspected_triggers_redaction_via_emitter(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record())
    assert event.payload["prompt"].startswith("[REDACTED:sha256:")
    assert event.payload["response"].startswith("[REDACTED:sha256:")


def test_warden_adapter_redacted_event_carries_receipt(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record())
    assert event.redaction_receipts


def test_warden_adapter_raw_prompt_absent_from_stored_event(tmp_path):
    from forgeledger.jsonl_backend import JsonlBackend

    path = tmp_path / "ledger.jsonl"
    backend = JsonlBackend(path)
    WardenLedgerAdapter(backend).emit_call_record(_record())
    assert RAW_PROMPT not in path.read_text(encoding="utf-8")


def test_warden_adapter_public_prompt_not_redacted(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record(data_sensitivity="public"))
    assert event.payload["prompt"] == RAW_PROMPT
    assert event.redaction_receipts == []


def test_warden_adapter_prompt_class_and_response_class_in_payload(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record())
    assert event.payload["prompt_class"] == "design_query"
    assert event.payload["response_class"] == "technical_recommendation"


def test_warden_adapter_emitted_event_passes_schema_validation(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record())
    assert validate_event(event) == []


def test_warden_adapter_latency_in_payload_when_provided(backend):
    event = WardenLedgerAdapter(backend).emit_call_record(_record(latency_ms=456))
    assert event.payload["latency_ms"] == 456


def test_warden_runtime_output_to_call_record():
    record = warden_runtime_output_to_call_record({
        "actor_id": "warden.runtime",
        "prompt": "hello",
        "response": "world",
        "data_sensitivity": "public",
        "prompt_class": "chat",
        "response_class": "answer",
        "model_provider": "local",
        "tenant_id": "tenant-runtime",
        "policy_id": "p",
        "policy_hash": "h",
    })
    assert record.actor_id == "warden.runtime"
    assert record.prompt == "hello"
    assert record.model_provider == "local"
