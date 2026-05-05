"""
test_lifecycle.py — Status machine tests  (P0-2)
=================================================
Tests all valid transitions from Core Spec §4.3 and rejects all invalid ones.
Pattern follows ForgeHarbor test_lifecycle_engine.py.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from azul.ticket import (
    AzulTicket,
    TicketStatus,
    TicketType,
    TicketPriority,
    create_ticket,
    TERMINAL_STATUSES,
)
from azul.lifecycle import (
    can_transition,
    begin_analysis,
    begin_provisioning,
    begin_evaluation,
    begin_gating,
    complete,
    reject,
    warn,
    fail,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_ticket(**kwargs) -> AzulTicket:
    defaults = dict(
        ticket_type="ci_gate",
        domain="ci_change_control",
        change_summary="Test ticket",
    )
    defaults.update(kwargs)
    return create_ticket(**defaults)


def assert_error(result, code: str = None) -> None:
    assert isinstance(result, dict), f"Expected error dict, got {type(result)}"
    assert result["status"] == "error"
    if code:
        assert result["error"]["code"] == code


# ── can_transition guard ───────────────────────────────────────────────────────

class TestCanTransition:
    def test_submitted_to_analyzing(self):
        assert can_transition(TicketStatus.SUBMITTED, TicketStatus.ANALYZING)

    def test_submitted_to_provisioning(self):
        assert can_transition(TicketStatus.SUBMITTED, TicketStatus.PROVISIONING)

    def test_submitted_to_failed(self):
        assert can_transition(TicketStatus.SUBMITTED, TicketStatus.FAILED)

    def test_analyzing_to_provisioning(self):
        assert can_transition(TicketStatus.ANALYZING, TicketStatus.PROVISIONING)

    def test_analyzing_to_failed(self):
        assert can_transition(TicketStatus.ANALYZING, TicketStatus.FAILED)

    def test_provisioning_to_evaluating(self):
        assert can_transition(TicketStatus.PROVISIONING, TicketStatus.EVALUATING)

    def test_provisioning_to_failed(self):
        assert can_transition(TicketStatus.PROVISIONING, TicketStatus.FAILED)

    def test_evaluating_to_gating(self):
        assert can_transition(TicketStatus.EVALUATING, TicketStatus.GATING)

    def test_evaluating_to_failed(self):
        assert can_transition(TicketStatus.EVALUATING, TicketStatus.FAILED)

    def test_gating_to_completed(self):
        assert can_transition(TicketStatus.GATING, TicketStatus.COMPLETED)

    def test_gating_to_rejected(self):
        assert can_transition(TicketStatus.GATING, TicketStatus.REJECTED)

    def test_gating_to_warned(self):
        assert can_transition(TicketStatus.GATING, TicketStatus.WARNED)

    def test_gating_to_failed(self):
        assert can_transition(TicketStatus.GATING, TicketStatus.FAILED)

    # Invalid transitions
    def test_submitted_to_gating_invalid(self):
        assert not can_transition(TicketStatus.SUBMITTED, TicketStatus.GATING)

    def test_submitted_to_completed_invalid(self):
        assert not can_transition(TicketStatus.SUBMITTED, TicketStatus.COMPLETED)

    def test_analyzing_to_completed_invalid(self):
        assert not can_transition(TicketStatus.ANALYZING, TicketStatus.COMPLETED)

    def test_terminal_statuses_block_all_transitions(self):
        for terminal in TERMINAL_STATUSES:
            for any_status in TicketStatus:
                assert not can_transition(terminal, any_status), (
                    f"Terminal status {terminal} should not allow transition to {any_status}"
                )


# ── Named transition functions ────────────────────────────────────────────────

class TestTransitions:
    def test_begin_analysis_from_submitted(self):
        t = make_ticket()
        assert t.status == TicketStatus.SUBMITTED
        result = begin_analysis(t)
        assert isinstance(result, AzulTicket)
        assert result.status == TicketStatus.ANALYZING

    def test_begin_analysis_from_analyzing_invalid(self):
        t = make_ticket()
        begin_analysis(t)  # moves to ANALYZING
        result = begin_analysis(t)  # can't go ANALYZING→ANALYZING
        assert_error(result, "INVALID_TRANSITION")

    def test_begin_provisioning_from_submitted(self):
        t = make_ticket()
        result = begin_provisioning(t)
        assert isinstance(result, AzulTicket)
        assert result.status == TicketStatus.PROVISIONING

    def test_begin_provisioning_from_analyzing(self):
        t = make_ticket()
        begin_analysis(t)
        result = begin_provisioning(t)
        assert result.status == TicketStatus.PROVISIONING

    def test_begin_evaluation(self):
        t = make_ticket()
        begin_provisioning(t)
        result = begin_evaluation(t)
        assert result.status == TicketStatus.EVALUATING

    def test_begin_gating(self):
        t = make_ticket()
        begin_provisioning(t)
        begin_evaluation(t)
        result = begin_gating(t)
        assert result.status == TicketStatus.GATING

    def test_complete_awards_xp(self):
        t = make_ticket()
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        result = complete(t, xp=25)
        assert result.status == TicketStatus.COMPLETED
        assert result.xp_awarded == 25
        assert result.verdict == "pass"
        assert result.completed_at is not None

    def test_reject(self):
        t = make_ticket()
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        result = reject(t, reason="Score too low")
        assert result.status == TicketStatus.REJECTED
        assert result.verdict == "reject"
        assert result.xp_awarded == 0
        assert result.verdict_reason == "Score too low"

    def test_warn(self):
        t = make_ticket()
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        result = warn(t, reason="Deny count > 0", xp=15)
        assert result.status == TicketStatus.WARNED
        assert result.verdict == "pass"
        assert result.xp_awarded == 15

    def test_fail_from_any_non_terminal(self):
        # Fail from SUBMITTED
        t = make_ticket()
        result = fail(t, reason="Unexpected error")
        assert result.status == TicketStatus.FAILED
        assert result.verdict is None
        assert result.xp_awarded == 0

        # Fail from EVALUATING
        t2 = make_ticket()
        begin_provisioning(t2)
        begin_evaluation(t2)
        result2 = fail(t2, reason="ForgeWorks timed out")
        assert result2.status == TicketStatus.FAILED

    def test_cannot_transition_from_terminal(self):
        t = make_ticket()
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        complete(t, xp=10)
        # COMPLETED is terminal — all further transitions should fail
        assert_error(complete(t), "INVALID_TRANSITION")
        assert_error(fail(t), "INVALID_TRANSITION")
        assert_error(reject(t), "INVALID_TRANSITION")

    def test_full_happy_path_ci_gate(self):
        """Full flow: SUBMITTED→ANALYZING→PROVISIONING→EVALUATING→GATING→COMPLETED"""
        t = make_ticket(ticket_type="ci_gate", domain="ci_change_control")
        assert t.status == TicketStatus.SUBMITTED

        begin_analysis(t)
        assert t.status == TicketStatus.ANALYZING

        begin_provisioning(t)
        assert t.status == TicketStatus.PROVISIONING

        begin_evaluation(t)
        assert t.status == TicketStatus.EVALUATING

        begin_gating(t)
        assert t.status == TicketStatus.GATING

        complete(t, xp=25)
        assert t.status == TicketStatus.COMPLETED
        assert t.xp_awarded == 25
        assert t.verdict == "pass"

    def test_updated_at_changes_on_transition(self):
        t = make_ticket()
        original_updated = t.updated_at
        import time; time.sleep(0.01)
        begin_analysis(t)
        assert t.updated_at >= original_updated
