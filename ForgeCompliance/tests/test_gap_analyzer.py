"""
Phase 2 tests 3, 4:
3. Missing required fields are detected.
4. Missing event types produce control evidence gaps.
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
from forgecompliance.gap_analyzer import GapAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    event_type: EventType,
    event_id: str = "evt-001",
    actor_id: str = "test.agent",
    decision_type: str = "allow",
) -> LedgerEvent:
    return attach_integrity(
        LedgerEvent(
            event_id=event_id,
            ledger_version=LEDGER_VERSION,
            event_type=event_type,
            event_time="2026-04-28T10:00:00Z",
            actor=Actor(actor_type="agent", actor_id=actor_id, role="test"),
            tenant=Tenant(tenant_id="t-001", customer_boundary="b", data_residency="NZ"),
            system_context=SystemContext(source_module="CONCORD", environment="local", deployment_id="test"),
            decision=Decision(decision_type=decision_type, reason="test_reason", risk_level="low"),
            evidence=Evidence(evidence_refs=[], evidence_gaps=[], assertion_classes=["FACT"]),
            policy=Policy(policy_id="p-001", policy_hash="abc", retention_class=RetentionClass.AUDIT_7Y),
            control_tags=[],
            integrity=Integrity(previous_hash=None, event_hash=""),
        ),
        None,
    )


def _make_event_missing_field(event_type: EventType, clear_field: str) -> LedgerEvent:
    """Build an event with a top-level field cleared to empty string."""
    import dataclasses
    base = _make_event(event_type)
    if clear_field == "actor.actor_id":
        return dataclasses.replace(base, actor=dataclasses.replace(base.actor, actor_id=""))
    if clear_field == "decision.decision_type":
        return dataclasses.replace(base, decision=dataclasses.replace(base.decision, decision_type=""))
    if clear_field == "policy.policy_hash":
        return dataclasses.replace(base, policy=dataclasses.replace(base.policy, policy_hash=""))
    return base


# ---------------------------------------------------------------------------
# Test 4: Missing event types produce control evidence gaps
# ---------------------------------------------------------------------------

def test_gap_when_no_events_provided():
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)
    report = analyzer.analyze("NZISM", [])

    gap_controls = [c for c in report.controls if c.status == "gap"]
    assert len(gap_controls) == report.total_controls
    assert report.coverage_percent == 0.0


def test_gap_report_detects_missing_event_type():
    """NZISM.ACCESS.AUTHORISATION requires concord.admission_decision.
    If only forgegate events are present, the control should be a gap."""
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)

    events = [_make_event(EventType.FORGEGATE_DECISION_RECORD, "e1")]
    report = analyzer.analyze("NZISM", events)

    auth_control = next(
        c for c in report.controls if c.control_id == "NZISM.ACCESS.AUTHORISATION"
    )
    assert auth_control.status == "gap"
    assert "concord.admission_decision" in auth_control.missing_event_types


def test_control_covered_when_all_types_present():
    """NZISM.LOGGING.TAMPER_PROTECTION requires only forgegate.decision_record."""
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)

    events = [_make_event(EventType.FORGEGATE_DECISION_RECORD, "e1")]
    report = analyzer.analyze("NZISM", events)

    tamper_control = next(
        c for c in report.controls if c.control_id == "NZISM.LOGGING.TAMPER_PROTECTION"
    )
    assert tamper_control.status == "covered"
    assert not tamper_control.missing_event_types


def test_partial_coverage_when_some_types_missing():
    """NZISM.LOGGING.EVENT_CAPTURE requires three event types.
    Supplying only one → partial."""
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)

    events = [_make_event(EventType.CONCORD_ADMISSION_DECISION, "e1")]
    report = analyzer.analyze("NZISM", events)

    capture_control = next(
        c for c in report.controls if c.control_id == "NZISM.LOGGING.EVENT_CAPTURE"
    )
    assert capture_control.status == "partial"
    assert "forgegate.decision_record" in capture_control.missing_event_types


def test_coverage_percent_reflects_covered_controls():
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)

    # Provide all events needed for NZISM.LOGGING.TAMPER_PROTECTION only
    events = [_make_event(EventType.FORGEGATE_DECISION_RECORD, "e1")]
    report = analyzer.analyze("NZISM", events)

    assert 0 < report.coverage_percent <= 100
    assert report.covered >= 1


# ---------------------------------------------------------------------------
# Test 3: Missing required fields are detected
# ---------------------------------------------------------------------------

def test_missing_required_field_detected_as_partial():
    """
    If events of the required type are present but a required field is empty,
    the control status should be partial, not covered.
    """
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)

    # NZISM.ACCESS.AUTHORISATION requires actor.actor_id — clear it
    broken_event = _make_event_missing_field(
        EventType.CONCORD_ADMISSION_DECISION, "actor.actor_id"
    )
    report = analyzer.analyze("NZISM", [broken_event])

    auth_control = next(
        c for c in report.controls if c.control_id == "NZISM.ACCESS.AUTHORISATION"
    )
    # event_type is present but field is missing → partial
    assert auth_control.status == "partial"
    assert "actor.actor_id" in auth_control.missing_required_fields


def test_missing_policy_hash_detected():
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)

    broken = _make_event_missing_field(
        EventType.CONCORD_ADMISSION_DECISION, "policy.policy_hash"
    )
    report = analyzer.analyze("NZISM", [broken])

    retention_control = next(
        (c for c in report.controls if c.control_id == "NZISM.LOGGING.RETENTION"),
        None,
    )
    if retention_control and "policy.policy_hash" in [
        ctrl.required_fields
        for ctrl in registry.get_profile("NZISM").controls
        if ctrl.control_id == "NZISM.LOGGING.RETENTION"
    ][0]:
        assert retention_control.status in ("partial", "gap")


# ---------------------------------------------------------------------------
# Misc gap analyzer properties
# ---------------------------------------------------------------------------

def test_analyze_all_returns_all_frameworks():
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)
    reports = analyzer.analyze_all([])
    assert set(reports.keys()) == set(registry.list_frameworks())


def test_gap_report_total_matches_control_list():
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)
    report = analyzer.analyze("SOC2", [])
    assert report.total_controls == len(report.controls)
    assert report.gaps + report.partial + report.covered == report.total_controls


def test_unknown_framework_raises():
    registry = ControlRegistry()
    analyzer = GapAnalyzer(registry)
    try:
        analyzer.analyze("NONEXISTENT_FRAMEWORK_XYZ", [])
        assert False, "Expected ValueError"
    except ValueError:
        pass
