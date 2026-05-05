from forgeledger.schema import EventType
from forgeledger.validators import validate_event
from integrations.azul_ledger_adapter import AzulLedgerAdapter, azul_runtime_output_to_verdict_record
from integrations.types import AzulVerdictRecord


def _record(**overrides):
    data = dict(
        actor_id="azul.safety_engine",
        verdict="allow",
        reason="safe",
        tenant_id="tenant-001",
        customer_boundary="customer-a",
        data_residency="NZ",
        policy_id="azul-policy",
        policy_hash="hash",
        safety_score=0.97,
        flagged_categories=[],
        evidence_refs=["doc:safety"],
        frameworks=["SOC2"],
    )
    data.update(overrides)
    return AzulVerdictRecord(**data)


def test_azul_adapter_emits_verdict_summary_event_type(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record())
    assert event.event_type == EventType.AZUL_VERDICT_SUMMARY


def test_azul_adapter_deny_verdict_has_deny_decision_type(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record(verdict="deny"))
    assert event.decision.decision_type == "deny"


def test_azul_adapter_safety_score_in_payload(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record(safety_score=0.44))
    assert event.payload["safety_score"] == 0.44


def test_azul_adapter_flagged_categories_in_payload(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record(flagged_categories=["privacy"]))
    assert event.payload["flagged_categories"] == ["privacy"]


def test_azul_adapter_evidence_refs_propagated(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record(evidence_refs=["doc:azul"]))
    assert event.evidence.evidence_refs == ["doc:azul"]


def test_azul_adapter_emitted_event_passes_schema_validation(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record())
    assert validate_event(event) == []


def test_azul_adapter_allow_verdict_has_low_risk_level(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record(verdict="allow"))
    assert event.decision.risk_level == "low"


def test_azul_adapter_deny_verdict_has_high_risk_level(backend):
    event = AzulLedgerAdapter(backend).emit_verdict_record(_record(verdict="deny"))
    assert event.decision.risk_level == "high"


def test_azul_runtime_output_to_verdict_record():
    record = azul_runtime_output_to_verdict_record({
        "actor_id": "azul.runtime",
        "verdict": "deny",
        "reason": "unsafe",
        "tenant_id": "tenant-runtime",
        "policy_id": "p",
        "policy_hash": "h",
        "safety_score": 0.1,
        "flagged_categories": ["safety"],
    })
    assert record.actor_id == "azul.runtime"
    assert record.verdict == "deny"
    assert record.flagged_categories == ["safety"]
