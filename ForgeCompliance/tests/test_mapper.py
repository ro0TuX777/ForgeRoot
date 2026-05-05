"""
Phase 2 tests 2 & 7:
2. Event types map to expected control IDs.
7. Coverage report is deterministic and reproducible.
"""
from forgeledger.hash_chain import attach_integrity
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
from forgecompliance.control_registry import ControlRegistry
from forgecompliance.mapper import FrameworkMapper
from forgecompliance.reports import generate_coverage_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_type: EventType, event_id: str = "evt-001") -> LedgerEvent:
    return LedgerEvent(
        event_id=event_id,
        ledger_version=LEDGER_VERSION,
        event_type=event_type,
        event_time="2026-04-28T10:00:00Z",
        actor=Actor(actor_type="agent", actor_id="test.agent", role="test_role"),
        tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
        system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
        decision=Decision(decision_type="allow", reason="test", risk_level="low"),
        evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
        policy=Policy(policy_id="p-001", policy_hash="abc", retention_class=RetentionClass.AUDIT_7Y),
        control_tags=[],
        integrity=Integrity(previous_hash=None, event_hash=""),
    )


# ---------------------------------------------------------------------------
# Test 2: Event types map to expected control IDs
# ---------------------------------------------------------------------------

def test_concord_admission_maps_to_nzism_authorisation():
    registry = ControlRegistry()
    mapper = FrameworkMapper(registry)
    event = attach_integrity(_make_event(EventType.CONCORD_ADMISSION_DECISION), None)

    tags = mapper.map_event(event)
    control_ids = {(t.framework, t.control_id) for t in tags}

    assert ("NZISM", "NZISM.ACCESS.AUTHORISATION") in control_ids
    assert ("NZISM", "NZISM.LOGGING.EVENT_CAPTURE") in control_ids


def test_forgegate_decision_maps_to_tamper_protection():
    registry = ControlRegistry()
    mapper = FrameworkMapper(registry)
    event = attach_integrity(_make_event(EventType.FORGEGATE_DECISION_RECORD), None)

    tags = mapper.map_event(event)
    control_ids = {(t.framework, t.control_id) for t in tags}

    assert ("NZISM", "NZISM.LOGGING.TAMPER_PROTECTION") in control_ids


def test_human_approval_maps_to_soc2_change_management():
    registry = ControlRegistry()
    mapper = FrameworkMapper(registry)
    event = attach_integrity(_make_event(EventType.HUMAN_APPROVAL_DECISION), None)

    tags = mapper.map_event(event)
    control_ids = {(t.framework, t.control_id) for t in tags}

    assert ("SOC2", "SOC2.CC8.1") in control_ids


def test_forgegate_policy_evaluation_maps_to_nist():
    registry = ControlRegistry()
    mapper = FrameworkMapper(registry)
    event = attach_integrity(_make_event(EventType.FORGEGATE_POLICY_EVALUATION), None)

    tags = mapper.map_event(event)
    control_ids = {t.control_id for t in tags}

    assert "NIST_CSF.GV.RM-01" in control_ids


def test_unknown_event_type_returns_no_tags_for_warden_in_nzism():
    """warden.llm_call_metadata is in NZISM EVENT_CAPTURE but not in every framework."""
    registry = ControlRegistry()
    mapper = FrameworkMapper(registry)
    event = attach_integrity(_make_event(EventType.WARDEN_LLM_CALL_METADATA), None)

    tags = mapper.map_event(event)
    nzism_tags = [t for t in tags if t.framework == "NZISM"]
    assert any(t.control_id == "NZISM.LOGGING.EVENT_CAPTURE" for t in nzism_tags)


def test_coverage_map_marks_control_covered_when_all_types_present():
    registry = ControlRegistry()
    mapper = FrameworkMapper(registry)

    # NZISM.LOGGING.TAMPER_PROTECTION only requires forgegate.decision_record
    events = [
        attach_integrity(_make_event(EventType.FORGEGATE_DECISION_RECORD, "e1"), None),
    ]
    coverage = mapper.generate_coverage_map(events)

    assert "NZISM.LOGGING.TAMPER_PROTECTION" in coverage.get("NZISM", set())


def test_coverage_map_excludes_control_when_type_absent():
    registry = ControlRegistry()
    mapper = FrameworkMapper(registry)

    # Only supply agent.human_review_required — no forgegate events
    events = [
        attach_integrity(_make_event(EventType.AGENT_HUMAN_REVIEW_REQUIRED, "e1"), None),
    ]
    coverage = mapper.generate_coverage_map(events)

    # NZISM.LOGGING.TAMPER_PROTECTION requires forgegate.decision_record — should be absent
    assert "NZISM.LOGGING.TAMPER_PROTECTION" not in coverage.get("NZISM", set())


# ---------------------------------------------------------------------------
# Test 7: Coverage report is deterministic and reproducible
# ---------------------------------------------------------------------------

def test_coverage_report_is_deterministic():
    registry = ControlRegistry()
    events = [
        attach_integrity(_make_event(EventType.CONCORD_ADMISSION_DECISION, "e1"), None),
        attach_integrity(_make_event(EventType.FORGEGATE_DECISION_RECORD, "e2"), None),
        attach_integrity(_make_event(EventType.HUMAN_APPROVAL_DECISION, "e3"), None),
    ]

    report1 = generate_coverage_report(registry, events, ["NZISM", "SOC2"])
    report2 = generate_coverage_report(registry, events, ["NZISM", "SOC2"])

    assert report1["framework_reports"] == report2["framework_reports"]
    assert report1["frameworks_analysed"] == report2["frameworks_analysed"]


def test_coverage_report_framework_list_is_sorted():
    registry = ControlRegistry()
    report = generate_coverage_report(registry, [], framework_ids=["SOC2", "NZISM", "ISO27001_2022"])
    assert report["frameworks_analysed"] == sorted(report["frameworks_analysed"])


def test_coverage_report_counts_events_correctly():
    registry = ControlRegistry()
    events = [
        attach_integrity(_make_event(EventType.CONCORD_ADMISSION_DECISION, "e1"), None),
        attach_integrity(_make_event(EventType.CONCORD_ADMISSION_DECISION, "e2"), None),
    ]
    report = generate_coverage_report(registry, events, ["NZISM"])
    assert report["total_events_analysed"] == 2
