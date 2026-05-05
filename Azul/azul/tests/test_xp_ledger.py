"""
test_xp_ledger.py — XP calculation and ledger tests  (P1-1)
============================================================
Tests XP formula (base * risk + score_bonus), JSONL appending,
and summary aggregation by domain / type.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import pytest
from pathlib import Path

from azul.ticket import create_ticket, TicketStatus, TicketType, TicketPriority
from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete, reject, fail, warn
from azul.xp_ledger import XPLedger, calculate_xp, XP_BY_TYPE, RISK_MULTIPLIERS


@pytest.fixture
def tmp_ledger(tmp_path):
    return XPLedger(path=tmp_path / "xp_ledger.jsonl")


def make_completed_ticket(
    ticket_type="ci_gate",
    domain="ci_change_control",
    priority="normal",
    score=91.5,
    xp=20,
):
    t = create_ticket(
        ticket_type=ticket_type,
        domain=domain,
        change_summary="Test",
        priority=priority,
    )
    t.review_bundle = {"metrics": {"total_score": score, "pass_fail": True}, "bundle_id": "b-001"}
    begin_provisioning(t)
    begin_evaluation(t)
    begin_gating(t)
    complete(t, xp=xp)
    return t


def make_warned_ticket(score=75.0, xp=8):
    t = create_ticket(
        ticket_type="ci_gate",
        domain="ci_change_control",
        change_summary="Warned ticket",
    )
    t.review_bundle = {"metrics": {"total_score": score, "pass_fail": True}, "bundle_id": "b-002"}
    begin_provisioning(t)
    begin_evaluation(t)
    begin_gating(t)
    warn(t, xp=xp)
    return t


def make_rejected_ticket():
    t = create_ticket(
        ticket_type="ci_gate",
        domain="ci_change_control",
        change_summary="Rejected ticket",
    )
    begin_provisioning(t)
    begin_evaluation(t)
    begin_gating(t)
    reject(t)
    return t


# ── XP calculation ────────────────────────────────────────────────────────────

class TestCalculateXP:
    def test_ci_gate_normal_priority(self):
        t = make_completed_ticket(ticket_type="ci_gate", priority="normal", score=91.5)
        xp = calculate_xp(t)
        # base=10, risk=1.0, score_bonus=int(91.5/10)=9 → 10*1.0+9=19
        assert xp == 19

    def test_refactor_high_priority(self):
        t = make_completed_ticket(ticket_type="refactor", priority="high", score=80.0)
        xp = calculate_xp(t)
        # base=15, risk=1.5, score_bonus=int(80/10)=8 → 15*1.5+8=30
        assert xp == 30

    def test_security_patch_critical_priority(self):
        t = make_completed_ticket(ticket_type="security_patch", priority="critical", score=90.0)
        xp = calculate_xp(t)
        # base=20, risk=2.0, score_bonus=9 → 20*2.0+9=49
        assert xp == 49

    def test_distillation_pair(self):
        t = make_completed_ticket(ticket_type="distillation_pair", priority="low", score=50.0)
        xp = calculate_xp(t)
        # base=5, risk=1.0, score_bonus=5 → 10
        assert xp == 10

    def test_zero_xp_for_rejected(self):
        t = make_rejected_ticket()
        assert calculate_xp(t) == 0

    def test_zero_xp_for_failed(self):
        t = create_ticket(ticket_type="ci_gate", domain="ci_change_control", change_summary="x")
        fail(t)
        assert calculate_xp(t) == 0

    def test_warned_ticket_earns_xp(self):
        t = make_warned_ticket(score=75.0)
        xp = calculate_xp(t)
        # base=10, risk=1.0, score_bonus=7 → 17
        assert xp == 17

    def test_no_review_bundle_gives_zero_bonus(self):
        t = create_ticket(ticket_type="ci_gate", domain="ci_change_control", change_summary="x")
        begin_provisioning(t)
        begin_evaluation(t)
        begin_gating(t)
        complete(t, xp=10)
        # review_bundle is None — score = 0
        xp = calculate_xp(t)
        assert xp == 10  # 10*1.0 + 0


# ── Ledger append and read ────────────────────────────────────────────────────

class TestXPLedger:
    def test_award_xp_creates_file(self, tmp_ledger, tmp_path):
        t = make_completed_ticket()
        tmp_ledger.award_xp(t)
        ledger_file = tmp_path / "xp_ledger.jsonl"
        assert ledger_file.exists()

    def test_award_xp_appends_record(self, tmp_ledger):
        t1 = make_completed_ticket()
        t2 = make_completed_ticket(domain="it_ops_runbook", ticket_type="policy_compliance")
        tmp_ledger.award_xp(t1)
        tmp_ledger.award_xp(t2)
        records = tmp_ledger.records()
        assert len(records) == 2

    def test_rejected_ticket_not_written(self, tmp_ledger):
        t = make_rejected_ticket()
        xp = tmp_ledger.award_xp(t)
        assert xp == 0
        assert len(tmp_ledger.records()) == 0

    def test_record_fields(self, tmp_ledger):
        t = make_completed_ticket(ticket_type="refactor", domain="ci_change_control", score=80.0)
        tmp_ledger.award_xp(t)
        records = tmp_ledger.records()
        r = records[0]
        assert r["ticket_id"] == t.ticket_id
        assert r["ticket_type"] == "refactor"
        assert r["domain"] == "ci_change_control"
        assert "xp" in r
        assert "timestamp" in r

    def test_empty_ledger_returns_empty_list(self, tmp_ledger):
        assert tmp_ledger.records() == []


# ── Summary ───────────────────────────────────────────────────────────────────

class TestXPSummary:
    def test_total_xp(self, tmp_ledger):
        t1 = make_completed_ticket(score=90.0)     # 10+9=19
        t2 = make_completed_ticket(score=80.0)     # 10+8=18
        tmp_ledger.award_xp(t1)
        tmp_ledger.award_xp(t2)
        summary = tmp_ledger.get_summary()
        assert summary["total_xp"] == 37
        assert summary["record_count"] == 2

    def test_summary_by_domain(self, tmp_ledger):
        t1 = make_completed_ticket(domain="ci_change_control", score=90.0)
        t2 = make_completed_ticket(domain="it_ops_runbook", ticket_type="policy_compliance", score=60.0)
        tmp_ledger.award_xp(t1)
        tmp_ledger.award_xp(t2)
        summary = tmp_ledger.get_summary()
        assert "ci_change_control" in summary["by_domain"]
        assert "it_ops_runbook" in summary["by_domain"]

    def test_domain_filter(self, tmp_ledger):
        t1 = make_completed_ticket(domain="ci_change_control")
        t2 = make_completed_ticket(domain="it_ops_runbook", ticket_type="policy_compliance")
        tmp_ledger.award_xp(t1)
        tmp_ledger.award_xp(t2)
        summary = tmp_ledger.get_summary(domain="ci_change_control")
        assert summary["record_count"] == 1

    def test_ticket_type_filter(self, tmp_ledger):
        t1 = make_completed_ticket(ticket_type="ci_gate")
        t2 = make_completed_ticket(ticket_type="refactor")
        tmp_ledger.award_xp(t1)
        tmp_ledger.award_xp(t2)
        summary = tmp_ledger.get_summary(ticket_type="ref actor")
        # "ref actor" doesn't match — 0 records
        assert summary["record_count"] == 0
        summary2 = tmp_ledger.get_summary(ticket_type="refactor")
        assert summary2["record_count"] == 1
