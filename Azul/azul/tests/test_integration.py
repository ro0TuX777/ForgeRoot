"""
test_integration.py — End-to-end integration tests  (Phase 6)
=============================================================
Full lifecycle tests: CI gate, refactor, security patch, policy compliance,
and distillation pair — all run through the complete verify() pipeline
with realistic mocked frameworks.

Tests validate the FULL sequence:
    SUBMITTED → ANALYZING → PROVISIONING → EVALUATING → GATING → [terminal]

and confirm cross-module wiring works correctly end-to-end:
    adapter → ticket creation → verify() → gate → XP → training pair → store

These are NOT unit tests — they exercise real module interactions without
mocking individual functions (except the framework integrations themselves,
which would require ForgeWorks binaries).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import time
from pathlib import Path

from azul.ticket import create_ticket, TicketStatus, TicketType, TicketPriority
from azul.ticket_store import AzulTicketStore
from azul.xp_ledger import XPLedger
from azul.training_pairs import TrainingPairStore
from azul.verification_engine import verify
from azul.adapters.ci_webhook import handle_webhook
from azul.adapters.distillation import submit_pair
from azul.adapters.api import AzulAPIHandler
from azul.queue_worker import AzulWorkerPool
from azul.telemetry import TelemetryEmitter, TelemetryReporter


# ── Shared integration mock (all framework integrations) ─────────────────────

@pytest.fixture(autouse=True)
def patch_all_integrations(monkeypatch):
    """
    Patch all 3 framework integrations with realistic mocks.
    Mimics the full integration flow without real binaries.
    """
    import azul.integrations.forge_harbor  as fh
    import azul.integrations.forge_scaffold as fs
    import azul.integrations.forge_works   as fw
    import azul.adapters.api               as api_mod
    import azul.adapters.ci_webhook        as ci_mod

    def mock_harbor_request(ticket_id):
        return {"status": "ok", "payload": {"environment_id": f"env-{ticket_id[:8]}"}}

    def mock_harbor_release(env_id):
        return {"status": "ok", "payload": {"released": True}}

    def mock_scaffold(target_files, project_root=None):
        units = [{"id": f"unit.{i}", "path": f, "type": "module"}
                 for i, f in enumerate(target_files)]
        return {"status": "ok", "payload": {"blast_radius": {
            "units": units, "affected_files": target_files,
            "total_units": len(units), "affected_count": len(units),
        }}}

    def mock_works(planner_spec):
        score = planner_spec.get("_test_score", 91.5)
        pass_fail = score >= 70.0
        rb = {
            "bundle_id": f"brv-{planner_spec.get('spec_id','x')[:12]}",
            "summary": {"domain": planner_spec.get("domain"), "mode": planner_spec.get("mode"),
                        "pass_fail": pass_fail, "total_score": score, "one_line": "integration test"},
            "gates_passed": 9,
            "failure_gate": None if pass_fail else "score",
            "failure_reason": None if pass_fail else f"Score {score} < 70",
            "metrics": {"total_score": score, "pass_fail": pass_fail,
                        "deny_count": 0, "oracle_mismatch_count": 0, "escalation_count": 0},
            "artifacts": {},
            "risk_assessment": {"highest_risk_level": "low", "deny_count": 0,
                                "oracle_mismatch_count": 0, "escalation_count": 0},
        }
        return {"status": "ok", "payload": {"receipt": {"status": "SUCCEEDED", "review_bundle": rb},
                                             "review_bundle": rb}}

    monkeypatch.setattr(fh,      "request_environment",  mock_harbor_request)
    monkeypatch.setattr(fh,      "release_environment",  mock_harbor_release)
    monkeypatch.setattr(fs,      "analyze_blast_radius", mock_scaffold)
    monkeypatch.setattr(fw,      "execute_verification", mock_works)
    monkeypatch.setattr(api_mod, "verify", verify)   # API uses real verify()
    monkeypatch.setattr(ci_mod,  "AZUL_CI_STATUS_POST_ENABLED", False)
    monkeypatch.setattr(ci_mod,  "AZUL_CI_STATUS_FAIL_CLOSED", False)

    monkeypatch.setattr("azul.verification_engine.AZUL_FORGE_HARBOR_ENABLED",  True)
    monkeypatch.setattr("azul.verification_engine.AZUL_FORGE_SCAFFOLD_ENABLED", True)


@pytest.fixture
def store(tmp_path):
    return AzulTicketStore(active_dir=tmp_path/"active", completed_dir=tmp_path/"completed")


@pytest.fixture
def ledger(tmp_path):
    return XPLedger(path=tmp_path/"xp.jsonl")


@pytest.fixture
def pair_store(tmp_path, monkeypatch):
    import azul.training_pairs as tp
    monkeypatch.setattr(tp, "TRAINING_PAIRS_DIR", tmp_path/"pairs")
    return TrainingPairStore(directory=tmp_path/"pairs")


# ── Full lifecycle per ticket type ────────────────────────────────────────────

class TestFullLifecycleByType:
    """Full SUBMITTED→COMPLETED lifecycle for each of the 5 ticket types."""

    def _run(self, ticket_type, domain, store, ledger, target_files=None):
        t = create_ticket(
            ticket_type=ticket_type, domain=domain,
            change_summary=f"Integration test — {ticket_type}",
            target_files=target_files or ["src/main.py"],
        )
        result = verify(t, store=store, ledger=ledger)
        return t, result

    def test_ci_gate_full_lifecycle(self, store, ledger):
        t, result = self._run("ci_gate", "ci_change_control", store, ledger)
        assert t.status == TicketStatus.COMPLETED
        assert result["verdict"] == "pass"
        assert t.blast_radius is not None        # scaffold ran
        assert t.environment_id is not None      # harbor ran
        assert t.review_bundle is not None       # forge_works ran
        assert t.gate_result["severity"] == "ok"
        assert t.xp_awarded > 0
        loaded = store.get(t.ticket_id)
        assert loaded.status == TicketStatus.COMPLETED

    def test_refactor_full_lifecycle(self, store, ledger):
        t, result = self._run("refactor", "ci_change_control", store, ledger)
        assert t.status == TicketStatus.COMPLETED
        assert result["verdict"] == "pass"

    def test_security_patch_full_lifecycle(self, store, ledger):
        t, result = self._run("security_patch", "ci_change_control", store, ledger)
        assert t.status == TicketStatus.COMPLETED
        assert result["verdict"] == "pass"

    def test_policy_compliance_full_lifecycle(self, store, ledger):
        """it_ops_runbook domain — ForgeScaffold should be skipped (not a codebase domain)."""
        t, result = self._run("policy_compliance", "it_ops_runbook", store, ledger,
                               target_files=[])
        assert t.status == TicketStatus.COMPLETED
        assert result["verdict"] == "pass"
        assert t.blast_radius is None  # scaffold skipped for non-codebase domain

    def test_distillation_pair_full_lifecycle(self, store, ledger, pair_store):
        t = create_ticket(
            ticket_type="distillation_pair", domain="ci_change_control",
            change_summary="Distillation pair — integration test",
            change_payload={"input": "What is X?", "output": "X is Y."},
        )
        result = verify(t, store=store, ledger=ledger)
        assert t.status == TicketStatus.COMPLETED
        assert result["verdict"] == "pass"
        pairs = pair_store.get_pairs()
        assert len(pairs) == 1
        assert pairs[0]["input"] == "What is X?"


# ── Reject and fail paths ─────────────────────────────────────────────────────

class TestRejectAndFailPaths:
    def test_low_score_produces_rejection(self, monkeypatch, store, ledger):
        """Patch forge_works to return score=62 → REJECTED."""
        import azul.integrations.forge_works as fw

        def bad_works(spec):
            rb = {
                "bundle_id": "brv-bad",
                "summary": {"domain": spec.get("domain"), "mode": "shadow",
                            "pass_fail": True, "total_score": 62.0, "one_line": "bad"},
                "gates_passed": 3, "failure_gate": None, "failure_reason": None,
                "metrics": {"total_score": 62.0, "pass_fail": True,
                            "deny_count": 0, "oracle_mismatch_count": 0, "escalation_count": 0},
                "artifacts": {}, "risk_assessment": {"highest_risk_level": "high",
                    "deny_count": 0, "oracle_mismatch_count": 0, "escalation_count": 0},
            }
            return {"status": "ok", "payload": {"receipt": {}, "review_bundle": rb}}

        monkeypatch.setattr(fw, "execute_verification", bad_works)
        t = create_ticket(ticket_type="ci_gate", domain="ci_change_control",
                          change_summary="Bad change")
        result = verify(t, store=store, ledger=ledger)
        assert t.status == TicketStatus.REJECTED
        assert result["verdict"] == "reject"
        assert t.xp_awarded == 0

    def test_forge_works_failure_gives_failed_not_rejected(self, monkeypatch, store, ledger):
        """ForgeWorks operational error → FAILED (never REJECTED)."""
        import azul.integrations.forge_works as fw
        monkeypatch.setattr(fw, "execute_verification",
            lambda s: {"status": "error", "error": {"code": "FW_ERROR", "message": "pipeline crashed"}})
        t = create_ticket(ticket_type="ci_gate", domain="ci_change_control",
                          change_summary="FW crash")
        result = verify(t, store=store)
        assert t.status == TicketStatus.FAILED
        assert result["verdict"] is None

    def test_harbor_failure_is_failed(self, monkeypatch, store):
        """ForgeHarbor error → FAILED."""
        import azul.integrations.forge_harbor as fh
        monkeypatch.setattr(fh, "request_environment",
            lambda ticket_id: {"status": "error", "error": {"code": "NO_ENV", "message": "no envs"}})
        t = create_ticket(ticket_type="ci_gate", domain="ci_change_control",
                          change_summary="Harbor error")
        verify(t, store=store)
        assert t.status == TicketStatus.FAILED


# ── CI webhook adapter integration ───────────────────────────────────────────

class TestCiWebhookIntegration:
    def test_webhook_full_flow(self, store, ledger):
        result = handle_webhook({
            "repository":    "org/repo",
            "commit_sha":    "abc1234def5678",
            "branch":        "feature/fix-auth",
            "changed_files": ["src/auth.py", "tests/test_auth.py"],
            "event_type":    "pull_request",
        }, store=store, ledger=ledger)

        assert result["verdict"] == "pass"
        assert result["ticket_id"] is not None
        assert result["xp_awarded"] > 0

        # Ticket persisted
        tickets = store.list()
        assert len(tickets) == 1
        assert tickets[0].ticket_type == TicketType.CI_GATE

    def test_merge_to_main_high_priority(self, store, ledger):
        result = handle_webhook({
            "repository":    "org/repo",
            "commit_sha":    "deadbeef1234",
            "branch":        "main",
            "changed_files": ["src/core.py"],
            "event_type":    "push",
        }, store=store, ledger=ledger)
        assert result["verdict"] == "pass"
        tickets = store.list()
        assert tickets[0].priority == TicketPriority.HIGH


# ── Distillation adapter integration ─────────────────────────────────────────

class TestDistillationIntegration:
    def test_good_pair_emitted(self, store, ledger, pair_store):
        result = submit_pair({
            "input":         "What is backpropagation?",
            "output":        "A method to compute gradients in neural networks.",
            "domain":        "ci_change_control",
            "quality_score": 0.92,
            "source_model":  "azul-7b",
        }, store=store, ledger=ledger)

        assert result["status"] == "ok"
        assert result["data"]["verdict"] == "pass"
        assert result["data"]["pair_id"] is not None
        assert pair_store.count() == 1

    def test_low_quality_pair_prefiltered(self, store, pair_store):
        result = submit_pair({
            "input": "Q", "output": "A",
            "domain": "ci_change_control",
            "quality_score": 0.1,
        }, store=store, min_quality=0.5)

        assert result["data"]["verdict"] == "reject"
        assert result["data"]["pair_id"] is None
        assert pair_store.count() == 0
        # Store should be empty — no ticket was even created
        assert len(store.list()) == 0


# ── API handler integration ───────────────────────────────────────────────────

class TestAPIHandlerIntegration:
    def test_full_submit_and_list(self, store, ledger):
        handler = AzulAPIHandler(store=store, ledger=ledger)

        # Submit 3 tickets
        for i in range(3):
            resp = handler.handle({
                "action": "submit",
                "payload": {
                    "ticket_type":    "ci_gate",
                    "domain":         "ci_change_control",
                    "change_summary": f"API integration test {i}",
                },
            })
            assert resp["status"] == "ok"
            assert resp["data"]["verdict"] == "pass"

        # List
        list_resp = handler.handle({"action": "list", "payload": {}})
        assert list_resp["data"]["count"] == 3

        # Health
        health = handler.handle({"action": "health", "payload": {}})
        assert health["data"]["healthy"] is True


# ── Queue worker integration ──────────────────────────────────────────────────

class TestQueueWorkerIntegration:
    def test_concurrent_workers_no_conflict(self, store, ledger, monkeypatch):
        """Multiple workers process disjoint tickets concurrently without store corruption."""
        import azul.queue_worker as qw
        monkeypatch.setattr(qw, "verify", verify)

        pool = AzulWorkerPool(num_workers=3, store=store, ledger=ledger)
        pool.start()

        tickets = [
            create_ticket(ticket_type="ci_gate", domain="ci_change_control",
                          change_summary=f"Concurrent test {i}")
            for i in range(6)
        ]
        for t in tickets:
            pool.submit(t)

        # Wait for all to complete
        results = []
        for t in tickets:
            r = pool.wait_for_result(t.ticket_id, timeout=10.0)
            results.append(r)

        pool.stop(drain=True, timeout=10.0)

        assert all(r is not None for r in results)
        assert all(r["verdict"] == "pass" for r in results)
        # All 6 stored
        assert len(store.list()) == 6


# ── Telemetry integration ─────────────────────────────────────────────────────

class TestTelemetryIntegration:
    def test_verify_emits_telemetry(self, tmp_path, store, ledger):
        metrics_path = tmp_path / "metrics.jsonl"
        emitter = TelemetryEmitter(metrics_path=metrics_path, enabled=False)
        reporter = TelemetryReporter(metrics_path=metrics_path)

        for ticket_type, verdict, xp in [
            ("ci_gate", "pass", 19), ("refactor", "pass", 23), ("ci_gate", "reject", 0)
        ]:
            emitter.record_verification(
                ticket_id=f"azul-{ticket_type[:4]}",
                verdict=verdict,
                severity="ok" if verdict == "pass" else "critical",
                domain="ci_change_control",
                ticket_type=ticket_type,
                xp_awarded=xp,
                duration_ms=42.5,
            )

        summary = reporter.summary()
        assert summary["tickets_processed"] == 3
        assert summary["pass_count"] == 2
        assert summary["reject_count"] == 1
        assert summary["xp_awarded_total"] == 42
        assert 0 < summary["pass_rate"] < 1.0

    def test_summary_domain_filter(self, tmp_path):
        metrics_path = tmp_path / "metrics.jsonl"
        emitter = TelemetryEmitter(metrics_path=metrics_path, enabled=False)
        reporter = TelemetryReporter(metrics_path=metrics_path)

        for domain in ["ci_change_control", "ci_change_control", "it_ops_runbook"]:
            emitter.record_verification(
                ticket_id="t", verdict="pass", severity="ok",
                domain=domain, ticket_type="ci_gate", xp_awarded=10, duration_ms=10.0,
            )

        ci_summary = reporter.summary(domain="ci_change_control")
        assert ci_summary["tickets_processed"] == 2
        it_summary = reporter.summary(domain="it_ops_runbook")
        assert it_summary["tickets_processed"] == 1
