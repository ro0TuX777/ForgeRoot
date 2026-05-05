"""
test_verification_engine.py — verify() integration tests  (P0-6, P0-7)
=======================================================================
Uses monkeypatched mocks for all 3 framework integrations.
Tests all verdict paths (pass/reject/warn/fail) and environmental rules.

Acceptance criteria from Implementation Plan §3:
    - Happy path → COMPLETED, verdict="pass", xp > 0
    - Score < 70 → REJECTED, verdict="reject", xp = 0
    - Score 70-80 or deny > 0 → WARNED, verdict="pass", xp > 0
    - ForgeWorks error → FAILED, NOT REJECTED
    - ForgeHarbor env ALWAYS released (even on failure)
    - ForgeScaffold called for codebase domains only
    - Training pair emitted for distillation_pair + pass
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import tempfile
from pathlib import Path
from typing import Any, Dict

from azul.ticket import create_ticket, TicketStatus
from azul.ticket_store import AzulTicketStore
from azul.xp_ledger import XPLedger
from azul.training_pairs import TrainingPairStore
from azul.verification_engine import verify

from azul.tests.mocks.mock_integrations import MockForgeHarbor, MockForgeScaffold, MockForgeWorks


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_integrations(monkeypatch):
    """
    Replace all 3 real integrations with mocks for every test.
    Returns the mock set so tests can configure failure modes.
    """
    import azul.integrations.forge_harbor as fh_mod
    import azul.integrations.forge_scaffold as fs_mod
    import azul.integrations.forge_works as fw_mod

    mock_harbor   = MockForgeHarbor()
    mock_scaffold = MockForgeScaffold()
    mock_works    = MockForgeWorks()

    monkeypatch.setattr(fh_mod, "request_environment",   mock_harbor.request_environment)
    monkeypatch.setattr(fh_mod, "release_environment",   mock_harbor.release_environment)
    monkeypatch.setattr(fs_mod, "analyze_blast_radius",  mock_scaffold.analyze_blast_radius)
    monkeypatch.setattr(fw_mod, "execute_verification",  mock_works.execute_verification)

    # Enable ForgeHarbor and ForgeScaffold for tests by default
    import azul.verification_engine as ve_mod
    monkeypatch.setattr(ve_mod, "AZUL_FORGE_HARBOR_ENABLED",   True)
    monkeypatch.setattr(ve_mod, "AZUL_FORGE_SCAFFOLD_ENABLED",  True)

    yield mock_harbor, mock_scaffold, mock_works


@pytest.fixture
def tmp_store(tmp_path):
    return AzulTicketStore(
        active_dir=tmp_path / "active",
        completed_dir=tmp_path / "completed",
    )


@pytest.fixture
def tmp_ledger(tmp_path):
    return XPLedger(path=tmp_path / "xp_ledger.jsonl")


@pytest.fixture
def tmp_pair_store(tmp_path, monkeypatch):
    import azul.training_pairs as tp
    monkeypatch.setattr(tp, "TRAINING_PAIRS_DIR", tmp_path / "pairs")
    return TrainingPairStore(directory=tmp_path / "pairs")


def make_ticket(
    ticket_type="ci_gate",
    domain="ci_change_control",
    target_files=None,
    **kwargs
):
    return create_ticket(
        ticket_type=ticket_type,
        domain=domain,
        change_summary="Test change",
        target_files=target_files or ["src/auth.py"],
        **kwargs,
    )


# ── Happy path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    def test_full_pass_ci_gate(self, patch_integrations, tmp_store, tmp_ledger):
        """Full flow: SUBMITTED→ANALYZING→PROVISIONING→EVALUATING→GATING→COMPLETED."""
        mock_harbor, mock_scaffold, mock_works = patch_integrations
        mock_works.score = 91.5
        mock_works.pass_fail = True

        t = make_ticket()
        result = verify(t, store=tmp_store, ledger=tmp_ledger)

        assert result["status"] == "ok"
        assert result["verdict"] == "pass"
        assert result["ticket_status"] == TicketStatus.COMPLETED.value
        assert t.xp_awarded > 0
        assert t.review_bundle is not None
        assert t.gate_result["severity"] == "ok"
        assert len(result["alerts"]) == 0

    def test_ticket_persisted_in_completed(self, patch_integrations, tmp_store, tmp_ledger):
        t = make_ticket()
        verify(t, store=tmp_store)
        loaded = tmp_store.get(t.ticket_id)
        assert loaded is not None
        assert loaded.status == TicketStatus.COMPLETED

    def test_environment_released_on_pass(self, patch_integrations, tmp_store):
        mock_harbor, _, _ = patch_integrations
        t = make_ticket()
        verify(t, store=tmp_store)
        assert len(mock_harbor.releases_made) == 1
        assert mock_harbor.releases_made[0] == mock_harbor.env_id

    def test_xp_recorded_in_ledger(self, patch_integrations, tmp_store, tmp_ledger):
        mock_harbor, _, mock_works = patch_integrations
        mock_works.score = 91.5
        t = make_ticket(ticket_type="refactor")
        verify(t, store=tmp_store, ledger=tmp_ledger)
        records = tmp_ledger.records()
        assert len(records) == 1
        assert records[0]["ticket_id"] == t.ticket_id

    def test_forge_scaffold_called_for_codebase_domain(self, patch_integrations, tmp_store):
        mock_harbor, mock_scaffold, _ = patch_integrations
        t = make_ticket(domain="ci_change_control", target_files=["src/auth.py"])
        verify(t, store=tmp_store)
        assert len(mock_scaffold.calls_made) == 1

    def test_blast_radius_stored_on_ticket(self, patch_integrations, tmp_store):
        t = make_ticket(domain="ci_change_control", target_files=["src/auth.py"])
        verify(t, store=tmp_store)
        assert t.blast_radius is not None
        assert "units" in t.blast_radius

    def test_planner_spec_stored_on_ticket(self, patch_integrations, tmp_store):
        t = make_ticket()
        verify(t, store=tmp_store)
        assert t.planner_spec is not None
        assert t.planner_spec["schema_version"] == "0.1"


# ── Rejection (REJECTED) ─────────────────────────────────────────────────────

class TestRejection:
    def test_rejected_when_score_below_min(self, patch_integrations, tmp_store):
        """score < 70 → REJECTED (behavioral failure, not operational)."""
        _, _, mock_works = patch_integrations
        mock_works.score = 62.0
        mock_works.pass_fail = True

        t = make_ticket()
        result = verify(t, store=tmp_store)

        assert result["verdict"] == "reject"
        assert result["ticket_status"] == TicketStatus.REJECTED.value
        assert t.xp_awarded == 0

    def test_rejected_when_pass_fail_false(self, patch_integrations, tmp_store):
        """pass_fail=False → REJECTED."""
        _, _, mock_works = patch_integrations
        mock_works.score = 88.0
        mock_works.pass_fail = False

        t = make_ticket()
        result = verify(t, store=tmp_store)

        assert result["verdict"] == "reject"
        assert result["ticket_status"] == TicketStatus.REJECTED.value

    def test_rejected_ticket_has_no_xp(self, patch_integrations, tmp_store, tmp_ledger):
        _, _, mock_works = patch_integrations
        mock_works.score = 60.0
        mock_works.pass_fail = False

        t = make_ticket()
        verify(t, store=tmp_store, ledger=tmp_ledger)
        # No XP records
        assert len(tmp_ledger.records()) == 0
        assert t.xp_awarded == 0

    def test_environment_released_on_reject(self, patch_integrations, tmp_store):
        """Environment must be released even when verdict=reject."""
        mock_harbor, _, mock_works = patch_integrations
        mock_works.score = 60.0

        t = make_ticket()
        verify(t, store=tmp_store)
        assert len(mock_harbor.releases_made) == 1

    def test_rejected_on_subprocess_guard_violation(
        self,
        patch_integrations,
        tmp_store,
        monkeypatch,
        tmp_path,
    ):
        _, _, mock_works = patch_integrations
        mock_works.score = 95.0
        mock_works.pass_fail = True

        guard_path = tmp_path / "action_catalogs" / "subprocess_guard.yaml"
        guard_path.parent.mkdir(parents=True, exist_ok=True)
        guard_path.write_text(
            """\
domain: "system_operations"
unit_id: "external.subprocess"
actions:
  - id: "check_call"
    description: "Execute a system command"
    guard_predicates:
      - "args[0] in ['ls', 'git status', 'whoami']"
      - "kwargs.get('shell') == False"
    risk_tier: 3
    consistency_profile: "atomic"
""",
            encoding="utf-8",
        )
        monkeypatch.setenv("FORGE_ATLAS_CATALOG_PATH", str(guard_path.parent))

        malicious_diff = """\
--- a/src/app/__init__.py
+++ b/src/app/__init__.py
@@ -1,1 +1,2 @@
+import subprocess
+subprocess.check_call(['rm', '-rf', '/'], shell=True)
"""

        t = make_ticket(change_payload={"diff": malicious_diff})
        result = verify(t, store=tmp_store)

        assert result["verdict"] == "reject"
        assert result["ticket_status"] == TicketStatus.REJECTED.value
        assert t.verdict_reason is not None
        assert "Guard Predicate Violation" in t.verdict_reason
        assert "args[0] 'rm' not in ['ls', 'git status', 'whoami']" in t.verdict_reason
        assert "kwargs.get('shell') expected False but got True" in t.verdict_reason

    def test_rejected_on_no_destructive_remediation_violation(self, patch_integrations, tmp_store):
        _, _, mock_works = patch_integrations
        mock_works.score = 95.0
        mock_works.pass_fail = True

        destructive_diff = """\
--- a/src/service.py
+++ b/src/service.py
@@ -1,13 +1,1 @@
-a
-b
-c
-d
-e
-f
-g
-h
-i
-j
-k
-l
-m
+k
"""
        t = make_ticket(change_payload={"diff": destructive_diff})
        result = verify(t, store=tmp_store)

        assert result["verdict"] == "reject"
        assert result["ticket_status"] == TicketStatus.REJECTED.value
        assert "No-Destructive-Remediation Violation" in (t.verdict_reason or "")


# ── Warning (WARNED) ─────────────────────────────────────────────────────────

class TestWarning:
    def test_warned_when_score_between_70_and_80(self, patch_integrations, tmp_store):
        """70 <= score < 80 → WARNED, verdict=pass."""
        _, _, mock_works = patch_integrations
        mock_works.score = 75.0
        mock_works.pass_fail = True

        t = make_ticket()
        result = verify(t, store=tmp_store)

        assert result["verdict"] == "pass"
        assert result["ticket_status"] == TicketStatus.WARNED.value
        assert t.xp_awarded > 0

    def test_warned_on_deny_count(self, patch_integrations, tmp_store):
        _, _, mock_works = patch_integrations
        mock_works.score = 88.0
        mock_works.deny_count = 1

        t = make_ticket()
        result = verify(t, store=tmp_store)

        assert result["ticket_status"] == TicketStatus.WARNED.value
        assert any("deny_count" in a for a in result["alerts"])

    def test_warned_xp_awarded(self, patch_integrations, tmp_store, tmp_ledger):
        _, _, mock_works = patch_integrations
        mock_works.score = 75.0

        t = make_ticket()
        verify(t, store=tmp_store, ledger=tmp_ledger)
        assert t.xp_awarded > 0
        assert len(tmp_ledger.records()) == 1


# ── Operational failures (FAILED ≠ REJECTED) ─────────────────────────────────

class TestOperationalFailures:
    def test_forge_works_error_gives_failed_not_rejected(self, patch_integrations, tmp_store):
        """ForgeWorks operational error → FAILED (never REJECTED)."""
        _, _, mock_works = patch_integrations
        mock_works.should_fail = True

        t = make_ticket()
        result = verify(t, store=tmp_store)

        assert result["status"] == "error"
        assert result["ticket_status"] == TicketStatus.FAILED.value
        assert result["verdict"] is None   # FAILED has no behavioral verdict
        assert t.metadata.get("manual_review_required") is True
        assert t.metadata.get("manual_review_reason") == "operational_fail_closed"

    def test_forge_harbor_error_gives_failed(self, patch_integrations, tmp_store):
        mock_harbor, _, _ = patch_integrations
        mock_harbor.should_fail = True

        t = make_ticket()
        result = verify(t, store=tmp_store)

        assert result["ticket_status"] == TicketStatus.FAILED.value
        assert t.metadata.get("manual_review_required") is True
        # No environment was obtained — release should not have been called with an env_id
        # (but release is still attempted with empty env_id — short-circuits OK)

    def test_degraded_forgeworks_payload_fails_closed(self, patch_integrations, tmp_store, monkeypatch):
        import azul.integrations.forge_works as fw_mod

        def _degraded(_planner_spec):
            return {
                "status": "ok",
                "payload": {
                    "receipt": {"status": "SUCCEEDED"},
                    "review_bundle": {"metrics": {"total_score": 95.0, "pass_fail": True}},
                    "degraded": True,
                    "degraded_reason": "dependency missing",
                },
            }

        monkeypatch.setattr(fw_mod, "execute_verification", _degraded)

        t = make_ticket()
        result = verify(t, store=tmp_store)
        assert result["status"] == "error"
        assert result["ticket_status"] == TicketStatus.FAILED.value
        assert "degraded" in (t.verdict_reason or "").lower()
        assert t.metadata.get("manual_review_required") is True

    def test_forge_scaffold_error_gives_failed(self, patch_integrations, tmp_store):
        _, mock_scaffold, _ = patch_integrations
        mock_scaffold.should_fail = True

        t = make_ticket(target_files=["src/auth.py"])
        result = verify(t, store=tmp_store)

        assert result["ticket_status"] == TicketStatus.FAILED.value

    def test_environment_released_even_on_forge_works_failure(self, patch_integrations, tmp_store):
        """Critical: environment ALWAYS released via finally block."""
        mock_harbor, _, mock_works = patch_integrations
        mock_works.should_fail = True

        t = make_ticket()
        verify(t, store=tmp_store)

        assert len(mock_harbor.releases_made) == 1

    def test_failed_ticket_xp_is_zero(self, patch_integrations, tmp_store, tmp_ledger):
        _, _, mock_works = patch_integrations
        mock_works.should_fail = True

        t = make_ticket()
        verify(t, store=tmp_store, ledger=tmp_ledger)
        assert t.xp_awarded == 0
        assert len(tmp_ledger.records()) == 0


# ── Feature flag behaviour ────────────────────────────────────────────────────

class TestFeatureFlags:
    def test_forge_scaffold_skipped_when_disabled(self, patch_integrations, monkeypatch, tmp_store):
        import azul.verification_engine as ve_mod
        monkeypatch.setattr(ve_mod, "AZUL_FORGE_SCAFFOLD_ENABLED", False)
        _, mock_scaffold, _ = patch_integrations

        t = make_ticket(domain="ci_change_control", target_files=["src/auth.py"])
        verify(t, store=tmp_store)
        # ForgeScaffold should NOT have been called
        assert len(mock_scaffold.calls_made) == 0

    def test_forge_scaffold_skipped_for_non_codebase_domain(self, patch_integrations, tmp_store):
        _, mock_scaffold, _ = patch_integrations

        t = make_ticket(
            ticket_type="policy_compliance",
            domain="it_ops_runbook",
            target_files=[],
        )
        verify(t, store=tmp_store)
        assert len(mock_scaffold.calls_made) == 0

    def test_forge_harbor_skipped_when_disabled(self, patch_integrations, monkeypatch, tmp_store):
        import azul.verification_engine as ve_mod
        monkeypatch.setattr(ve_mod, "AZUL_FORGE_HARBOR_ENABLED", False)
        mock_harbor, _, _ = patch_integrations

        t = make_ticket()
        result = verify(t, store=tmp_store)
        # Harbor should NOT have been called
        assert len(mock_harbor.requests_made) == 0
        # Should still complete successfully
        assert result["ticket_status"] == TicketStatus.COMPLETED.value


# ── Training pair emission ────────────────────────────────────────────────────

class TestTrainingPairEmission:
    def test_distillation_pair_emits_on_pass(self, patch_integrations, tmp_store, tmp_pair_store):
        _, _, mock_works = patch_integrations
        mock_works.score = 92.0

        t = make_ticket(
            ticket_type="distillation_pair",
            change_payload={"input": "What is X?", "output": "X is Y."},
        )
        verify(t, store=tmp_store)

        assert t.status == TicketStatus.COMPLETED
        pairs = tmp_pair_store.get_pairs()
        assert len(pairs) == 1
        assert pairs[0]["input"] == "What is X?"

    def test_ci_gate_does_not_emit_pair(self, patch_integrations, tmp_store, tmp_pair_store):
        t = make_ticket(ticket_type="ci_gate")
        verify(t, store=tmp_store)
        assert tmp_pair_store.count() == 0

    def test_distillation_pair_rejected_no_pair(self, patch_integrations, tmp_store, tmp_pair_store):
        _, _, mock_works = patch_integrations
        mock_works.score = 60.0
        t = make_ticket(
            ticket_type="distillation_pair",
            change_payload={"input": "Q", "output": "A"},
        )
        verify(t, store=tmp_store)
        assert tmp_pair_store.count() == 0
