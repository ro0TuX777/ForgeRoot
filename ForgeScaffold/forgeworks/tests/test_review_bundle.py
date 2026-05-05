"""
Unit tests for ForgeWorksReviewBundle (brief §5 validation criteria).

Covers:
  5.1 Happy path  — full pipeline success, all 9 gates, DONE status
  5.2 Partial failure — ingest failure, gates_passed=2, failure_gate="ingest"
  5.3 REPLAN scenario — score below target, risk_assessment.score_below_threshold=True
  5.4 Schema validity — assembled bundle passes review_bundle.v0_1.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from forgeworks.core.review_bundle import (
    ForgeWorksReviewBundle,
    _failure_gate_name,
    assemble_review_bundle,
)

# ---------------------------------------------------------------------------
# Load JSON schema once
# ---------------------------------------------------------------------------
_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "forgeworks" / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((_SCHEMAS_DIR / name).read_text())


BUNDLE_SCHEMA = _load_schema("review_bundle.v0_1.json")
RECEIPT_SCHEMA = _load_schema("planner_receipt.v0_1.json")
_bundle_validator = Draft202012Validator(BUNDLE_SCHEMA)
_receipt_validator = Draft202012Validator(RECEIPT_SCHEMA)


def _validate_bundle(bundle_dict: dict) -> None:
    errors = list(_bundle_validator.iter_errors(bundle_dict))
    assert not errors, f"review_bundle schema violations: {[e.message for e in errors]}"


def _validate_receipt(receipt: dict) -> None:
    errors = list(_receipt_validator.iter_errors(receipt))
    assert not errors, f"planner_receipt schema violations: {[e.message for e in errors]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_spec(target_score: float = 80.0, mode: str = "shadow") -> dict:
    return {
        "schema_version": "0.1",
        "spec_id": "test-spec-001",
        "request_id": "SAM-TICKET-42",
        "goal": "Verify CI pipeline handles broken dependency gracefully",
        "domain": "ci_change_control",
        "mode": mode,
        "source": {"source_path": "ingest/ci_change_control/batch_001"},
        "workcell": {"out_path": "packs/ci_change_control/test"},
        "run": {"out_path": "results/test_run"},
        "score": {"oracle_path": "packs/ci_change_control/test/oracle.json",
                  "scoring_path": "packs/ci_change_control/test/scoring.json"},
        "report": {"out_path": "results/test_run/report.md"},
        "loop_policy": {
            "max_iterations": 3,
            "target_score": target_score,
            "max_no_progress_iters": 2,
            "require_zero_oracle_mismatch": True,
            "require_zero_deny": True,
        },
    }


def _make_success_receipt(spec: dict) -> dict:
    """Minimal DONE receipt that passes planner_receipt schema."""
    return {
        "schema_version": "0.1",
        "spec_id": spec["spec_id"],
        "timestamp": "2026-03-06T00:00:00+00:00",
        "status": "DONE",
        "failure_reason": "NONE",
        "gates_passed": 9,
        "metrics": {
            "total_score": 91.5,
            "pass_fail": True,
            "deny_count": 0,
            "oracle_mismatch_count": 0,
            "escalation_count": 0,
            "drift_events_applied": 0,
        },
        "artifacts": {
            "run_summary": "results/test_run/run_summary.json",
            "decision_ledger": "results/test_run/decision_ledger.jsonl",
            "score_json": "results/test_run/score.json",
            "report_md": "results/test_run/report.md",
        },
    }


def _make_failure_receipt(spec: dict, gates_passed: int, failure_reason: str) -> dict:
    """REPLAN receipt for a pipeline that failed at a specific gate."""
    return {
        "schema_version": "0.1",
        "spec_id": spec["spec_id"],
        "timestamp": "2026-03-06T00:00:00+00:00",
        "status": "REPLAN",
        "failure_reason": failure_reason,
        "gates_passed": gates_passed,
        "metrics": {
            "total_score": 0.0,
            "pass_fail": False,
            "deny_count": 0,
            "oracle_mismatch_count": 0,
            "escalation_count": 0,
            "drift_events_applied": 0,
        },
        "artifacts": {},
    }


# ---------------------------------------------------------------------------
# §5.1 Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def setup_method(self) -> None:
        self.spec = _make_spec(target_score=80.0)
        self.receipt = _make_success_receipt(self.spec)
        self.run_summary = {
            "ticket_count": 42,
            "decision_count": 126,
            "approval_count": None,
            "mode": "shadow",
        }
        self.score_result = {"total_score": 91.5, "pass_fail": True}
        self.bundle = assemble_review_bundle(
            spec=self.spec,
            receipt=self.receipt,
            run_summary=self.run_summary,
            score_result=self.score_result,
        )
        self.bd = self.bundle.to_dict()

    def test_bundle_status_pending_review(self) -> None:
        assert self.bundle.bundle_status == "pending_review"

    def test_gates_passed_9(self) -> None:
        assert self.bundle.gates_passed == 9

    def test_failure_gate_null(self) -> None:
        assert self.bundle.failure_gate is None

    def test_failure_reason_null(self) -> None:
        assert self.bundle.failure_reason is None

    def test_artifacts_all_non_null(self) -> None:
        for key in ("run_summary", "decision_ledger", "score_json", "report_md"):
            assert self.bd["artifacts"][key] is not None, f"artifacts.{key} should not be null on happy path"

    def test_metrics_pass_fail_true(self) -> None:
        assert self.bundle.metrics["pass_fail"] is True

    def test_summary_one_line_format(self) -> None:
        one_line = self.bd["summary"]["one_line"]
        assert "shadow" in one_line
        assert "ci_change_control" in one_line
        assert "42" in one_line  # ticket_count
        assert "PASS" in one_line

    def test_summary_pipeline_status_done(self) -> None:
        assert self.bd["summary"]["pipeline_status"] == "DONE"

    def test_summary_failure_gate_none_string(self) -> None:
        assert self.bd["summary"]["failure_gate"] == "none"

    def test_risk_score_below_threshold_false(self) -> None:
        # 91.5 >= 80.0 so not below threshold
        assert self.bundle.risk_assessment["score_below_threshold"] is False

    def test_bundle_id_prefix(self) -> None:
        assert self.bundle.bundle_id.startswith("brv-")

    def test_schema_valid(self) -> None:
        _validate_bundle(self.bd)

    def test_receipt_with_bundle_passes_receipt_schema(self) -> None:
        receipt_copy = dict(self.receipt)
        receipt_copy["review_bundle"] = self.bd
        _validate_receipt(receipt_copy)


# ---------------------------------------------------------------------------
# §5.2 Partial failure (ingest failure at gate 3)
# ---------------------------------------------------------------------------

class TestPartialFailure:
    def setup_method(self) -> None:
        self.spec = _make_spec()
        # gates_passed=2 means spec passed (gate 1) + source compiled (gate 2)
        # but ingest failed (gate 3) → failure_gate should be "ingest"
        self.receipt = _make_failure_receipt(self.spec, gates_passed=2, failure_reason="MISSING_REQUIRED_RAW_FILE")
        self.bundle = assemble_review_bundle(
            spec=self.spec,
            receipt=self.receipt,
            run_summary=None,
            score_result=None,
        )
        self.bd = self.bundle.to_dict()

    def test_gates_passed(self) -> None:
        assert self.bundle.gates_passed == 2

    def test_failure_gate_is_ingest(self) -> None:
        assert self.bundle.failure_gate == "ingest"

    def test_failure_reason_set(self) -> None:
        assert self.bundle.failure_reason == "MISSING_REQUIRED_RAW_FILE"

    def test_artifacts_all_null(self) -> None:
        for key in ("run_summary", "decision_ledger", "score_json", "report_md"):
            assert self.bd["artifacts"][key] is None, f"artifacts.{key} should be null after ingest failure"

    def test_summary_one_line_mentions_failure_gate(self) -> None:
        one_line = self.bd["summary"]["one_line"]
        assert "ingest" in one_line

    def test_summary_pipeline_status_replan(self) -> None:
        assert self.bd["summary"]["pipeline_status"] == "REPLAN"

    def test_schema_valid(self) -> None:
        _validate_bundle(self.bd)

    def test_receipt_with_bundle_passes_receipt_schema(self) -> None:
        receipt_copy = dict(self.receipt)
        receipt_copy["review_bundle"] = self.bd
        _validate_receipt(receipt_copy)


# ---------------------------------------------------------------------------
# §5.3 REPLAN — score below target
# ---------------------------------------------------------------------------

class TestReplanScenario:
    def setup_method(self) -> None:
        self.spec = _make_spec(target_score=90.0)  # high bar
        # Pipeline completed all 9 gates but score was 72.0 < 90.0 → REPLAN
        self.receipt = {
            "schema_version": "0.1",
            "spec_id": self.spec["spec_id"],
            "timestamp": "2026-03-06T00:00:00+00:00",
            "status": "REPLAN",
            "failure_reason": "NONE",
            "gates_passed": 9,
            "metrics": {
                "total_score": 72.0,
                "pass_fail": False,
                "deny_count": 2,
                "oracle_mismatch_count": 1,
                "escalation_count": 0,
                "drift_events_applied": 0,
            },
            "artifacts": {
                "run_summary": "results/test_run/run_summary.json",
                "decision_ledger": "results/test_run/decision_ledger.jsonl",
                "score_json": "results/test_run/score.json",
                "report_md": "results/test_run/report.md",
            },
        }
        self.run_summary = {"ticket_count": 10, "decision_count": 30, "approval_count": None}
        self.score_result = {"total_score": 72.0, "pass_fail": False}
        self.bundle = assemble_review_bundle(
            spec=self.spec,
            receipt=self.receipt,
            run_summary=self.run_summary,
            score_result=self.score_result,
        )
        self.bd = self.bundle.to_dict()

    def test_metrics_total_score(self) -> None:
        assert self.bundle.metrics["total_score"] == 72.0

    def test_risk_score_below_threshold_true(self) -> None:
        assert self.bundle.risk_assessment["score_below_threshold"] is True

    def test_metrics_deny_count(self) -> None:
        assert self.bundle.metrics["deny_count"] == 2

    def test_metrics_oracle_mismatch_count(self) -> None:
        assert self.bundle.metrics["oracle_mismatch_count"] == 1

    def test_summary_pass_fail_false(self) -> None:
        assert self.bd["summary"]["pass_fail"] is False

    def test_summary_pipeline_status_replan(self) -> None:
        assert self.bd["summary"]["pipeline_status"] == "REPLAN"

    def test_summary_fields_all_populated(self) -> None:
        s = self.bd["summary"]
        for key in ("domain", "mode", "goal", "ticket_count", "decision_count",
                    "total_score", "pass_fail", "pipeline_status", "failure_gate", "one_line"):
            assert s.get(key) is not None, f"summary.{key} should not be None on REPLAN"

    def test_schema_valid(self) -> None:
        _validate_bundle(self.bd)


# ---------------------------------------------------------------------------
# Gate name helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gates_passed,expected", [
    (0, "spec_validation"),
    (1, "source_compile"),
    (2, "ingest"),
    (3, "normalize"),
    (4, "validate"),
    (5, "run"),
    (6, "score"),
    (7, "report"),
    (8, None),   # gate 9 failure would be RESULT_READER_FAILED; gates_passed=8 → failure at 9 → None (above map)
    (9, None),
])
def test_failure_gate_name(gates_passed: int, expected) -> None:
    result = _failure_gate_name(gates_passed)
    assert result == expected, f"gates_passed={gates_passed}: expected {expected!r}, got {result!r}"
