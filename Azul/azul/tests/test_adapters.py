"""
test_adapters.py — Entry adapter tests (Phase 4)
================================================
Tests all 5 adapters: ci_webhook, cli, api, event, distillation.
Uses monkeypatched verify() so adapter logic is tested in isolation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import pytest
from pathlib import Path
from typing import Any, Dict

from azul.ticket import TicketStatus, TicketType


# ── Shared mock for verify() ─────────────────────────────────────────────────

def _make_verify_mock(verdict="pass", severity="ok", status="ok", xp=19, alerts=None):
    """Factory for a mock verify() that returns a configurable result."""
    def _mock_verify(ticket, store=None, ledger=None):
        # Mutate the ticket's status as the real verify() would
        from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete, reject, warn
        begin_provisioning(ticket)
        begin_evaluation(ticket)
        begin_gating(ticket)
        if verdict == "pass" and severity == "warn":
            warn(ticket, xp=xp)
        elif verdict == "pass":
            complete(ticket, xp=xp)
        else:
            from azul.lifecycle import reject as do_reject
            do_reject(ticket)

        # Persist, just like real verify() does
        if store is not None:
            store.save(ticket)

        return {
            "status":        status,
            "verdict":       ticket.verdict,
            "severity":      severity,
            "ticket_id":     ticket.ticket_id,
            "ticket_status": ticket.status.value,
            "alerts":        alerts or [],
            "xp_awarded":    ticket.xp_awarded,
        }
    return _mock_verify


@pytest.fixture
def mock_verify(monkeypatch):
    """Patch verify() to pass by default; tests override with their own mock."""
    import azul.adapters.ci_webhook as cw
    import azul.adapters.event      as ev
    import azul.adapters.distillation as ds
    import azul.adapters.api         as api_mod

    v = _make_verify_mock()
    monkeypatch.setattr(cw,      "verify", v)
    monkeypatch.setattr(ev,      "verify", v)
    monkeypatch.setattr(ds,      "verify", v)
    monkeypatch.setattr(api_mod, "verify", v)
    monkeypatch.setattr(cw, "AZUL_CI_STATUS_POST_ENABLED", False)
    monkeypatch.setattr(cw, "AZUL_CI_STATUS_FAIL_CLOSED", False)
    return v


# ─────────────────────────────────────────────────────────────────────────────
# CI Webhook Adapter
# ─────────────────────────────────────────────────────────────────────────────

class TestCiWebhook:
    def _good_payload(self, **overrides):
        p = {
            "repository":    "org/repo",
            "commit_sha":    "abc1234def",
            "branch":        "feature/auth",
            "changed_files": ["src/auth.py", "tests/test_auth.py"],
            "event_type":    "push",
            "author":        "dev@example.com",
        }
        p.update(overrides)
        return p

    def test_happy_path_returns_pass(self, monkeypatch, mock_verify):
        from azul.adapters.ci_webhook import handle_webhook
        result = handle_webhook(self._good_payload())
        assert result["verdict"] == "pass"
        assert result["ticket_id"] is not None

    def test_missing_field_returns_error(self, mock_verify):
        from azul.adapters.ci_webhook import handle_webhook
        result = handle_webhook({"commit_sha": "abc"})  # missing repository, changed_files
        assert result["verdict"] == "error"
        assert "repository" in result["reason"] or "changed_files" in result["reason"]

    def test_invalid_changed_files_type(self, mock_verify):
        from azul.adapters.ci_webhook import handle_webhook
        p = self._good_payload(changed_files="not-a-list")
        result = handle_webhook(p)
        assert result["verdict"] == "error"

    def test_main_branch_gets_high_priority(self, monkeypatch):
        """Main branch push should create a HIGH priority ticket."""
        from azul.adapters import ci_webhook as cw
        captured = []

        def capturing_verify(ticket, store=None, ledger=None):
            captured.append(ticket)
            from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
            begin_provisioning(ticket); begin_evaluation(ticket); begin_gating(ticket)
            complete(ticket, xp=10)
            return {"status": "ok", "verdict": "pass", "severity": "ok",
                    "ticket_id": ticket.ticket_id, "ticket_status": "COMPLETED",
                    "alerts": [], "xp_awarded": 10}

        monkeypatch.setattr(cw, "verify", capturing_verify)
        cw.handle_webhook(self._good_payload(branch="main"))
        assert captured[0].priority.value == "high"

    def test_pr_branch_gets_normal_priority(self, monkeypatch):
        from azul.adapters import ci_webhook as cw
        captured = []

        def capturing_verify(ticket, store=None, ledger=None):
            captured.append(ticket)
            from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
            begin_provisioning(ticket); begin_evaluation(ticket); begin_gating(ticket)
            complete(ticket, xp=10)
            return {"status": "ok", "verdict": "pass", "severity": "ok",
                    "ticket_id": ticket.ticket_id, "ticket_status": "COMPLETED",
                    "alerts": [], "xp_awarded": 10}

        monkeypatch.setattr(cw, "verify", capturing_verify)
        cw.handle_webhook(self._good_payload(branch="feature/x"))
        assert captured[0].priority.value == "normal"

    def test_reject_propagates(self, monkeypatch):
        from azul.adapters import ci_webhook as cw
        monkeypatch.setattr(cw, "verify", _make_verify_mock(verdict="reject", severity="critical"))
        result = cw.handle_webhook(self._good_payload())
        assert result["verdict"] == "reject"

    def test_status_post_fail_closed_on_post_error(self, monkeypatch):
        from azul.adapters import ci_webhook as cw
        monkeypatch.setattr(cw, "verify", _make_verify_mock(verdict="pass", severity="ok"))
        monkeypatch.setattr(cw, "AZUL_CI_STATUS_POST_ENABLED", True)
        monkeypatch.setattr(
            cw,
            "_post_commit_status",
            lambda **kwargs: {"status": "error", "reason": "api down", "provider": "github"},
        )
        monkeypatch.setattr(cw, "AZUL_CI_STATUS_FAIL_CLOSED", True)
        result = cw.handle_webhook(self._good_payload())
        assert result["verdict"] == "reject"
        assert any("CI_STATUS_POST_FAILED" in a for a in result["alerts"])

    def test_status_post_result_included(self, monkeypatch):
        from azul.adapters import ci_webhook as cw
        monkeypatch.setattr(cw, "verify", _make_verify_mock(verdict="pass", severity="ok"))
        monkeypatch.setattr(cw, "AZUL_CI_STATUS_POST_ENABLED", True)
        monkeypatch.setattr(
            cw,
            "_post_commit_status",
            lambda **kwargs: {"status": "posted", "provider": "github", "state": "success"},
        )
        result = cw.handle_webhook(self._good_payload())
        assert result["verdict"] == "pass"
        assert result["status_post"]["status"] == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# CLI Adapter
# ─────────────────────────────────────────────────────────────────────────────

class TestCliAdapter:
    def test_pass_exit_code_0(self, monkeypatch):
        import azul.adapters.cli as cli_mod
        monkeypatch.setattr(cli_mod, "verify", _make_verify_mock())
        monkeypatch.setattr(cli_mod, "ensure_data_dirs", lambda: None)
        monkeypatch.setattr(cli_mod, "AzulTicketStore", lambda: None)
        monkeypatch.setattr(cli_mod, "XPLedger", lambda: None)

        exit_code = cli_mod.run([
            "--summary", "Fix null check",
            "--no-persist",
        ])
        assert exit_code == 0

    def test_reject_exit_code_1(self, monkeypatch):
        import azul.adapters.cli as cli_mod
        monkeypatch.setattr(cli_mod, "verify", _make_verify_mock(verdict="reject", severity="critical"))
        exit_code = cli_mod.run(["--summary", "Bad change", "--no-persist"])
        assert exit_code == 1

    def test_invalid_payload_json_exit_code_2(self, monkeypatch):
        import azul.adapters.cli as cli_mod
        monkeypatch.setattr(cli_mod, "verify", _make_verify_mock())
        exit_code = cli_mod.run(["--summary", "x", "--payload", "not-json", "--no-persist"])
        assert exit_code == 2

    def test_json_output_flag(self, monkeypatch, capsys):
        import azul.adapters.cli as cli_mod
        monkeypatch.setattr(cli_mod, "verify", _make_verify_mock())
        cli_mod.run(["--summary", "Test", "--no-persist", "--json"])
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "verdict" in parsed

    def test_type_and_domain_flags(self, monkeypatch):
        import azul.adapters.cli as cli_mod
        captured = []

        def cap_verify(ticket, store=None, ledger=None):
            captured.append(ticket)
            from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
            begin_provisioning(ticket); begin_evaluation(ticket); begin_gating(ticket)
            complete(ticket, xp=5)
            return {"status": "ok", "verdict": "pass", "severity": "ok",
                    "ticket_id": ticket.ticket_id, "ticket_status": "COMPLETED",
                    "alerts": [], "xp_awarded": 5}

        monkeypatch.setattr(cli_mod, "verify", cap_verify)
        cli_mod.run([
            "--summary", "Runbook drift fix",
            "--type", "policy_compliance",
            "--domain", "it_ops_runbook",
            "--no-persist",
        ])
        t = captured[0]
        assert t.ticket_type == TicketType.POLICY_COMPLIANCE
        assert t.domain == "it_ops_runbook"


# ─────────────────────────────────────────────────────────────────────────────
# API Handler
# ─────────────────────────────────────────────────────────────────────────────

class TestApiHandler:
    @pytest.fixture
    def handler(self, monkeypatch, tmp_path):
        from azul.adapters.api import AzulAPIHandler
        import azul.adapters.api as api_mod
        monkeypatch.setattr(api_mod, "verify", _make_verify_mock())
        from azul.ticket_store import AzulTicketStore
        store = AzulTicketStore(
            active_dir=tmp_path / "active",
            completed_dir=tmp_path / "completed",
        )
        return AzulAPIHandler(store=store)

    def test_submit_happy_path(self, handler):
        resp = handler.handle({
            "action": "submit",
            "payload": {
                "ticket_type":    "ci_gate",
                "domain":         "ci_change_control",
                "change_summary": "Auth fix",
            },
        })
        assert resp["status"] == "ok"
        assert resp["data"]["verdict"] == "pass"

    def test_submit_missing_required_field(self, handler):
        resp = handler.handle({
            "action":  "submit",
            "payload": {"ticket_type": "ci_gate"},  # missing domain, change_summary
        })
        assert resp["status"] == "error"
        assert "domain" in resp["error"] or "change_summary" in resp["error"]

    def test_get_ticket(self, handler):
        # Submit first to create a ticket in the store
        handler.handle({
            "action": "submit",
            "payload": {
                "ticket_type": "ci_gate", "domain": "ci_change_control",
                "change_summary": "Store test",
            },
        })
        tickets = handler._store.list()
        assert len(tickets) == 1
        tid = tickets[0].ticket_id

        resp = handler.handle({"action": "get_ticket", "payload": {"ticket_id": tid}})
        assert resp["status"] == "ok"
        assert resp["data"]["ticket_id"] == tid

    def test_get_ticket_not_found(self, handler):
        resp = handler.handle({"action": "get_ticket", "payload": {"ticket_id": "azul-missing"}})
        assert resp["status"] == "error"
        assert resp["code"] == "NOT_FOUND"

    def test_list_returns_all_tickets(self, handler):
        for _ in range(3):
            handler.handle({
                "action": "submit",
                "payload": {"ticket_type": "ci_gate", "domain": "ci_change_control",
                            "change_summary": "X"},
            })
        resp = handler.handle({"action": "list", "payload": {}})
        assert resp["status"] == "ok"
        assert resp["data"]["count"] == 3

    def test_health_action(self, handler):
        resp = handler.handle({"action": "health", "payload": {}})
        assert resp["status"] == "ok"
        assert resp["data"]["healthy"] is True

    def test_unknown_action(self, handler):
        resp = handler.handle({"action": "explode", "payload": {}})
        assert resp["status"] == "error"
        assert resp["code"] == "UNKNOWN_ACTION"

    def test_invalid_request_type(self, handler):
        resp = handler.handle("not-a-dict")
        assert resp["status"] == "error"


# ─────────────────────────────────────────────────────────────────────────────
# Event Adapter
# ─────────────────────────────────────────────────────────────────────────────

class TestEventAdapter:
    def _good_event(self, **overrides):
        e = {
            "event_type":    "patch_proposed",
            "source_system": "sam_evolution",
            "ticket_type":   "ci_gate",
            "domain":        "ci_change_control",
            "change_summary": "Patch proposed by SAM",
            "change_payload": {"diff": "--- a/x.py"},
            "target_files":  ["src/x.py"],
        }
        e.update(overrides)
        return e

    def test_happy_path(self, monkeypatch):
        import azul.adapters.event as ev
        monkeypatch.setattr(ev, "verify", _make_verify_mock())
        result = ev.handle_event(self._good_event())
        assert result["status"] == "ok"
        assert result["data"]["verdict"] == "pass"

    def test_missing_fields_error(self, monkeypatch):
        import azul.adapters.event as ev
        monkeypatch.setattr(ev, "verify", _make_verify_mock())
        result = ev.handle_event({"event_type": "patch_proposed"})
        assert result["status"] == "error"

    def test_event_type_mapping(self, monkeypatch):
        """event_type=security_advisory maps to security_patch ticket type."""
        import azul.adapters.event as ev
        captured = []

        def cap(ticket, store=None, ledger=None):
            captured.append(ticket)
            from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
            begin_provisioning(ticket); begin_evaluation(ticket); begin_gating(ticket)
            complete(ticket, xp=5)
            return {"status": "ok", "verdict": "pass", "severity": "ok",
                    "ticket_id": ticket.ticket_id, "ticket_status": "COMPLETED",
                    "alerts": [], "xp_awarded": 5}

        monkeypatch.setattr(ev, "verify", cap)
        ev.handle_event(self._good_event(
            event_type="security_advisory",
            ticket_type="security_patch",  # explicit override
        ))
        assert captured[0].ticket_type == TicketType.SECURITY_PATCH

    def test_metadata_attached(self, monkeypatch):
        import azul.adapters.event as ev
        captured = []

        def cap(ticket, store=None, ledger=None):
            captured.append(ticket)
            from azul.lifecycle import begin_provisioning, begin_evaluation, begin_gating, complete
            begin_provisioning(ticket); begin_evaluation(ticket); begin_gating(ticket)
            complete(ticket, xp=5)
            return {"status": "ok", "verdict": "pass", "severity": "ok",
                    "ticket_id": ticket.ticket_id, "ticket_status": "COMPLETED",
                    "alerts": [], "xp_awarded": 5}

        monkeypatch.setattr(ev, "verify", cap)
        ev.handle_event(self._good_event())
        assert captured[0].metadata.get("event_type") == "patch_proposed"
        assert captured[0].metadata.get("source_system") == "sam_evolution"


# ─────────────────────────────────────────────────────────────────────────────
# Distillation Adapter
# ─────────────────────────────────────────────────────────────────────────────

class TestDistillationAdapter:
    def _good_payload(self, **overrides):
        p = {
            "input":  "What is gradient descent?",
            "output": "An optimization algorithm that iteratively moves toward the minimum of a function.",
            "domain": "ci_change_control",
            "quality_score": 0.88,
            "source_model":  "sam-7b",
        }
        p.update(overrides)
        return p

    def test_happy_path_returns_pass_and_pair_id(self, monkeypatch):
        import azul.adapters.distillation as ds
        monkeypatch.setattr(ds, "verify", _make_verify_mock())
        result = ds.submit_pair(self._good_payload())
        assert result["status"] == "ok"
        assert result["data"]["verdict"] == "pass"
        assert result["data"]["pair_id"] is not None
        assert result["data"]["pair_id"].startswith("tp-azul-")

    def test_missing_fields(self, monkeypatch):
        import azul.adapters.distillation as ds
        monkeypatch.setattr(ds, "verify", _make_verify_mock())
        result = ds.submit_pair({"input": "Q"})  # missing output, domain
        assert result["status"] == "error"

    def test_pre_filter_rejects_low_quality(self, monkeypatch):
        """quality_score below min_quality is rejected before hitting verify()."""
        import azul.adapters.distillation as ds
        called = []
        monkeypatch.setattr(ds, "verify", lambda *a, **k: called.append(1) or {})
        result = ds.submit_pair(self._good_payload(quality_score=0.3), min_quality=0.5)
        assert result["status"] == "ok"
        assert result["data"]["verdict"] == "reject"
        assert len(called) == 0  # verify() NOT called

    def test_rejected_pair_no_pair_id(self, monkeypatch):
        import azul.adapters.distillation as ds
        monkeypatch.setattr(ds, "verify", _make_verify_mock(verdict="reject", severity="critical"))
        result = ds.submit_pair(self._good_payload())
        assert result["data"]["pair_id"] is None
        assert result["data"]["verdict"] == "reject"
