"""
test_spec_builder.py — Planner spec construction tests  (P0-5)
==============================================================
Tests that build_verification_spec() produces valid planner_spec.v0_1 dicts
for all 5 ticket types and validates domain/mode/path resolution.

Validation criteria from Implementation Plan §2:
    - schema_version == "0.1"
    - domain resolved correctly per ticket type
    - mode defaults to "shadow"
    - source block picks source_path if present, else generator
    - run.out_path is a child of workcell.out_path
    - report.out_path is a child of run.out_path
    - loop_policy merged from ticket.metadata
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from pathlib import Path

from azul.ticket import create_ticket
from azul.spec_builder import build_verification_spec, DEFAULT_LOOP_POLICY
from azul.domain_config import resolve_oracle_path, resolve_scoring_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_ticket(ticket_type="ci_gate", domain="ci_change_control", change_summary="Test change", **kwargs):
    return create_ticket(
        ticket_type=ticket_type,
        domain=domain,
        change_summary=change_summary,
        **kwargs,
    )


def is_child_path(child: str, parent: str) -> bool:
    """Return True if child is at or under parent."""
    try:
        Path(child).relative_to(Path(parent))
        return True
    except ValueError:
        return False


# ── Schema and required keys ──────────────────────────────────────────────────

class TestSpecSchema:
    def test_schema_version(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert spec["schema_version"] == "0.1"

    def test_required_top_level_keys(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        for key in ("spec_id", "request_id", "goal", "domain", "mode",
                    "source", "workcell", "run", "score", "report", "loop_policy"):
            assert key in spec, f"Missing key: {key}"

    def test_request_id_matches_ticket_id(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert spec["request_id"] == t.ticket_id

    def test_goal_matches_change_summary(self):
        t = make_ticket(change_summary="Fix null check in auth module")
        spec = build_verification_spec(t)
        assert spec["goal"] == "Fix null check in auth module"

    def test_spec_id_contains_ticket_id(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert t.ticket_id in spec["spec_id"]


# ── Domain and mode resolution ────────────────────────────────────────────────

class TestDomainAndMode:
    def test_ci_gate_domain(self):
        t = make_ticket(ticket_type="ci_gate", domain="ci_change_control")
        spec = build_verification_spec(t)
        assert spec["domain"] == "ci_change_control"

    def test_refactor_domain(self):
        t = make_ticket(ticket_type="refactor", domain="ci_change_control")
        spec = build_verification_spec(t)
        assert spec["domain"] == "ci_change_control"

    def test_security_patch_domain(self):
        t = make_ticket(ticket_type="security_patch", domain="ci_change_control")
        spec = build_verification_spec(t)
        assert spec["domain"] == "ci_change_control"

    def test_policy_compliance_domain(self):
        t = make_ticket(ticket_type="policy_compliance", domain="it_ops_runbook")
        spec = build_verification_spec(t)
        assert spec["domain"] == "it_ops_runbook"

    def test_distillation_pair_uses_ticket_domain(self):
        t = make_ticket(ticket_type="distillation_pair", domain="ci_change_control")
        spec = build_verification_spec(t)
        assert spec["domain"] == "ci_change_control"

    def test_default_mode_is_shadow(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert spec["mode"] == "shadow"

    def test_mode_from_ticket(self):
        t = make_ticket(mode="supervised")
        spec = build_verification_spec(t)
        assert spec["mode"] == "supervised"


# ── Path alignment (ForgeWorks contract) ─────────────────────────────────────

class TestPathAlignment:
    def test_run_out_under_workcell(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert is_child_path(spec["run"]["out_path"], spec["workcell"]["out_path"])

    def test_report_out_under_run(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert is_child_path(spec["report"]["out_path"], spec["run"]["out_path"])

    def test_paths_contain_ticket_id(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert t.ticket_id in spec["workcell"]["out_path"]
        assert t.ticket_id in spec["run"]["out_path"]

    def test_oracle_path_resolves_for_ci(self):
        t = make_ticket(domain="ci_change_control")
        spec = build_verification_spec(t)
        assert "ci_change_control" in spec["score"]["oracle_path"]

    def test_scoring_path_resolves_for_it_ops(self):
        t = make_ticket(ticket_type="policy_compliance", domain="it_ops_runbook")
        spec = build_verification_spec(t)
        assert "it_ops_runbook" in spec["score"]["scoring_path"]


# ── Source block ──────────────────────────────────────────────────────────────

class TestSourceBlock:
    def test_source_path_when_provided(self):
        t = make_ticket(change_payload={"source_path": "/tmp/my_staged_data"})
        spec = build_verification_spec(t)
        assert "source_path" in spec["source"]
        assert spec["source"]["source_path"] == "/tmp/my_staged_data"

    def test_generator_when_no_source_path(self):
        t = make_ticket(change_payload={"diff": "--- a/foo.py"})
        spec = build_verification_spec(t)
        assert "generator" in spec["source"]
        assert "script_id" in spec["source"]["generator"]

    def test_ci_domain_uses_ci_generator(self):
        t = make_ticket(domain="ci_change_control")
        spec = build_verification_spec(t)
        assert spec["source"]["generator"]["script_id"] == "generate_ci_batch"

    def test_it_ops_domain_uses_it_ops_generator(self):
        t = make_ticket(ticket_type="policy_compliance", domain="it_ops_runbook")
        spec = build_verification_spec(t)
        assert spec["source"]["generator"]["script_id"] == "generate_it_ops_batch"


# ── Loop policy ───────────────────────────────────────────────────────────────

class TestLoopPolicy:
    def test_default_loop_policy(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        lp = spec["loop_policy"]
        assert lp["max_iterations"] == DEFAULT_LOOP_POLICY["max_iterations"]
        assert lp["target_score"] == DEFAULT_LOOP_POLICY["target_score"]

    def test_loop_policy_from_metadata(self):
        t = make_ticket(metadata={"loop_policy": {"max_iterations": 3, "target_score": 90.0}})
        spec = build_verification_spec(t)
        assert spec["loop_policy"]["max_iterations"] == 3
        assert spec["loop_policy"]["target_score"] == 90.0

    def test_metadata_overrides_not_overwritten(self):
        """Keys in metadata loop_policy override defaults; other keys remain."""
        t = make_ticket(metadata={"loop_policy": {"max_iterations": 2}})
        spec = build_verification_spec(t)
        assert spec["loop_policy"]["max_iterations"] == 2
        # Other default keys still present
        assert "target_score" in spec["loop_policy"]


# ── Drift plan (optional) ────────────────────────────────────────────────────

class TestDriftPlan:
    def test_no_drift_plan_by_default(self):
        t = make_ticket()
        spec = build_verification_spec(t)
        assert "drift_plan_path" not in spec["run"]

    def test_drift_plan_from_metadata(self):
        t = make_ticket(metadata={"drift_plan_path": "/tmp/drift.json"})
        spec = build_verification_spec(t)
        assert spec["run"]["drift_plan_path"] == "/tmp/drift.json"
