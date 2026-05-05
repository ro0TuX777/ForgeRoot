import pytest

from forgeledger.schema import EventType
from forgeledger.validators import validate_event
from integrations.concord_ledger_adapter import ConcordLedgerAdapter, concord_runtime_output_to_admission_result
from integrations.types import ConcordAdmissionResult


def _result(**overrides):
    data = dict(
        agent_id="agent.solution_designer",
        admitted=True,
        reason="within_capability_budget",
        risk_level="low",
        tenant_id="tenant-001",
        customer_boundary="customer-a",
        data_residency="NZ",
        policy_id="concord-policy",
        policy_hash="hash",
        frameworks=["NZISM", "SOC2"],
        evidence_refs=["doc:policy"],
        agent_class="solution_engineer",
    )
    data.update(overrides)
    return ConcordAdmissionResult(**data)


def test_concord_allow_emits_admission_decision_event_type(backend):
    event = ConcordLedgerAdapter(backend).emit_admission_result(_result(admitted=True))
    assert event.event_type == EventType.CONCORD_ADMISSION_DECISION


def test_concord_deny_emits_admission_decision_event_type(backend):
    event = ConcordLedgerAdapter(backend).emit_admission_result(_result(admitted=False))
    assert event.event_type == EventType.CONCORD_ADMISSION_DECISION
    assert event.decision.decision_type == "deny"


def test_concord_adapter_actor_type_is_agent(backend):
    event = ConcordLedgerAdapter(backend).emit_admission_result(_result())
    assert event.actor.actor_type == "agent"


def test_concord_adapter_decision_type_matches_result(backend):
    event = ConcordLedgerAdapter(backend).emit_admission_result(_result(admitted=True))
    assert event.decision.decision_type == "allow"


def test_concord_adapter_tenant_id_is_propagated(backend):
    event = ConcordLedgerAdapter(backend).emit_admission_result(_result(tenant_id="tenant-x"))
    assert event.tenant.tenant_id == "tenant-x"


def test_concord_adapter_control_tags_derived_from_frameworks(backend):
    event = ConcordLedgerAdapter(backend).emit_admission_result(_result(frameworks=["NZISM", "SOC2"]))
    assert "NZISM.LOGGING.EVENT_CAPTURE" in event.control_tags
    assert "SOC2.CC7.2" in event.control_tags


def test_concord_adapter_emitted_event_passes_schema_validation(backend):
    event = ConcordLedgerAdapter(backend).emit_admission_result(_result())
    assert validate_event(event) == []


def test_concord_adapter_raises_on_empty_agent_id(backend):
    with pytest.raises(ValueError, match="agent_id is required"):
        ConcordLedgerAdapter(backend).emit_admission_result(_result(agent_id=""))


def test_concord_runtime_output_to_admission_result():
    result = concord_runtime_output_to_admission_result({
        "agent_id": "agent.runtime",
        "admitted": True,
        "reason": "ok",
        "risk_level": "low",
        "tenant_id": "tenant-runtime",
        "policy_id": "p",
        "policy_hash": "h",
        "frameworks": ["NZISM"],
    })
    assert result.agent_id == "agent.runtime"
    assert result.admitted is True
    assert result.tenant_id == "tenant-runtime"
