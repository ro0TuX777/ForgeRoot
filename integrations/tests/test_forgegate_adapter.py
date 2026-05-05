from forgeledger.schema import EventType
from forgeledger.validators import validate_event
from integrations.forgegate_ledger_adapter import ForgeGateLedgerAdapter, forgegate_runtime_output_to_evaluation_result
from integrations.types import ForgeGateEvaluationResult


def _result(**overrides):
    data = dict(
        actor_id="forgegate.policy_engine",
        decision_type="allow",
        reason="policy_passed",
        risk_level="low",
        tenant_id="tenant-001",
        customer_boundary="customer-a",
        data_residency="NZ",
        policy_id="fg-policy",
        policy_hash="hash",
        blast_radius_score=0.2,
        evidence_refs=["doc:policy"],
        evidence_gaps=[],
        frameworks=["NZISM"],
        action_type="llm_call",
    )
    data.update(overrides)
    return ForgeGateEvaluationResult(**data)


def test_forgegate_allow_emits_decision_record_event_type(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result())
    assert event.event_type == EventType.FORGEGATE_DECISION_RECORD


def test_forgegate_review_emits_review_decision_type(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result(decision_type="review"))
    assert event.decision.decision_type == "review"


def test_forgegate_blast_radius_above_threshold_adds_high_blast_radius_gap(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result(blast_radius_score=0.82))
    assert any(g.gap_type == "high_blast_radius" for g in event.evidence.evidence_gaps)


def test_forgegate_evidence_gaps_propagated_to_event(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result(evidence_gaps=["missing_bom"]))
    assert any(g.gap_type == "missing_bom" for g in event.evidence.evidence_gaps)


def test_forgegate_blast_radius_score_in_payload(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result(blast_radius_score=0.42))
    assert event.payload["blast_radius_score"] == 0.42


def test_forgegate_policy_id_and_hash_in_policy_field(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result(policy_id="p1", policy_hash="h1"))
    assert event.policy.policy_id == "p1"
    assert event.policy.policy_hash == "h1"


def test_forgegate_adapter_emitted_event_passes_schema_validation(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result())
    assert validate_event(event) == []


def test_forgegate_low_risk_has_no_evidence_gaps(backend):
    event = ForgeGateLedgerAdapter(backend).emit_evaluation_result(_result(blast_radius_score=0.1))
    assert event.evidence.evidence_gaps == []


def test_forgegate_runtime_output_to_evaluation_result():
    result = forgegate_runtime_output_to_evaluation_result({
        "actor_id": "fg.runtime",
        "decision": "review",
        "reason": "blast",
        "risk_level": "high",
        "tenant_id": "tenant-runtime",
        "policy_id": "p",
        "policy_hash": "h",
        "blast_radius_score": 0.9,
    })
    assert result.actor_id == "fg.runtime"
    assert result.decision_type == "review"
    assert result.blast_radius_score == 0.9
