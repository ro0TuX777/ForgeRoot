"""
test_gate.py — AzulResultGate evaluation tests  (P0-4)
=======================================================
Tests all severity levels (ok / warn / critical), per-ticket policy overrides,
and edge cases (None bundle, empty metrics, partial bundles).

Validation criteria from Core Spec §5.3 and Implementation Plan §2:
    - score 91.5, pass_fail=True, 0 denies → ok, passed=True
    - score 65.0 → critical, passed=False
    - score 75.0 (< warn_score 80) → warn, passed=True
    - deny_count=1, score > 80 → warn, passed=True
    - pass_fail=False → critical, passed=False
    - per-ticket policy override
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from azul.gate import AzulResultGate, GateResult, DEFAULT_GATE_POLICY, get_azul_result_gate


@pytest.fixture
def gate():
    return AzulResultGate()


def make_bundle(
    total_score: float = 91.5,
    pass_fail: bool = True,
    deny_count: int = 0,
    oracle_mismatch_count: int = 0,
    escalation_count: int = 0,
    bundle_id: str = "brv-test123",
    domain: str = "ci_change_control",
) -> dict:
    return {
        "bundle_id": bundle_id,
        "summary":   {"domain": domain},
        "metrics": {
            "total_score":         total_score,
            "pass_fail":           pass_fail,
            "deny_count":          deny_count,
            "oracle_mismatch_count": oracle_mismatch_count,
            "escalation_count":    escalation_count,
        },
    }


# ── Severity logic ────────────────────────────────────────────────────────────

class TestSeverityLevels:
    def test_ok_all_passing(self, gate):
        bundle = make_bundle(total_score=91.5, pass_fail=True, deny_count=0)
        result = gate.evaluate(bundle)
        assert result.passed is True
        assert result.severity == "ok"
        assert result.alerts == []

    def test_critical_score_below_min(self, gate):
        """score < 70 → CRITICAL (hard block)."""
        bundle = make_bundle(total_score=65.0, pass_fail=True)
        result = gate.evaluate(bundle)
        assert result.passed is False
        assert result.severity == "critical"
        assert any("below minimum" in a for a in result.alerts)

    def test_critical_pass_fail_false(self, gate):
        """pass_fail=False AND score >= 70 → CRITICAL."""
        bundle = make_bundle(total_score=85.0, pass_fail=False)
        result = gate.evaluate(bundle)
        assert result.passed is False
        assert result.severity == "critical"

    def test_critical_both_conditions(self, gate):
        """Both score < 70 AND pass_fail=False → CRITICAL with 2 alerts."""
        bundle = make_bundle(total_score=60.0, pass_fail=False)
        result = gate.evaluate(bundle)
        assert result.passed is False
        assert result.severity == "critical"
        assert len(result.alerts) >= 2

    def test_warn_score_between_min_and_warn(self, gate):
        """score in [70, 80) → WARN (soft alert)."""
        bundle = make_bundle(total_score=75.0, pass_fail=True)
        result = gate.evaluate(bundle)
        assert result.passed is True
        assert result.severity == "warn"

    def test_warn_deny_count(self, gate):
        """deny_count > 0, score >= 80 → WARN."""
        bundle = make_bundle(total_score=88.0, pass_fail=True, deny_count=1)
        result = gate.evaluate(bundle)
        assert result.passed is True
        assert result.severity == "warn"
        assert any("deny_count" in a for a in result.alerts)

    def test_warn_oracle_mismatch(self, gate):
        bundle = make_bundle(total_score=88.0, pass_fail=True, oracle_mismatch_count=1)
        result = gate.evaluate(bundle)
        assert result.passed is True
        assert result.severity == "warn"
        assert any("oracle_mismatch" in a for a in result.alerts)

    def test_warn_escalation_count(self, gate):
        """escalation_count > 2 → WARN."""
        bundle = make_bundle(total_score=88.0, pass_fail=True, escalation_count=3)
        result = gate.evaluate(bundle)
        assert result.passed is True
        assert result.severity == "warn"

    def test_exact_min_score_is_ok(self, gate):
        """Score exactly at min_score (70.0) is NOT critical."""
        bundle = make_bundle(total_score=70.0, pass_fail=True)
        result = gate.evaluate(bundle)
        assert result.severity in ("ok", "warn")  # 70 < warn_score=80 → warn
        assert result.passed is True

    def test_exact_warn_score_is_ok(self, gate):
        """Score exactly at warn_score (80.0) is NOT warned."""
        bundle = make_bundle(total_score=80.0, pass_fail=True)
        result = gate.evaluate(bundle)
        assert result.severity == "ok"
        assert result.passed is True

    def test_critical_takes_precedence_over_warn(self, gate):
        """Score < 70 AND deny_count > 0 → still critical (not just warn)."""
        bundle = make_bundle(total_score=65.0, pass_fail=True, deny_count=2)
        result = gate.evaluate(bundle)
        assert result.severity == "critical"
        assert result.passed is False


# ── Per-ticket policy override ────────────────────────────────────────────────

class TestPolicyOverride:
    def test_custom_min_score(self, gate):
        """Per-ticket policy raises the min_score bar."""
        bundle = make_bundle(total_score=75.0, pass_fail=True)
        policy = {**DEFAULT_GATE_POLICY, "min_score": 80.0}
        result = gate.evaluate(bundle, policy=policy)
        assert result.severity == "critical"
        assert result.passed is False

    def test_custom_warn_score_lower(self, gate):
        """Lowering warn_score means score=76 is no longer warned."""
        bundle = make_bundle(total_score=76.0, pass_fail=True)
        policy = {**DEFAULT_GATE_POLICY, "warn_score": 74.0}
        result = gate.evaluate(bundle, policy=policy)
        assert result.severity == "ok"

    def test_allow_deny_count(self, gate):
        """max_deny_count=2 means deny_count=1 does not warn."""
        bundle = make_bundle(total_score=90.0, pass_fail=True, deny_count=1)
        policy = {**DEFAULT_GATE_POLICY, "max_deny_count": 2}
        result = gate.evaluate(bundle, policy=policy)
        assert result.severity == "ok"

    def test_require_pass_fail_false_override(self, gate):
        """Disabling require_pass_fail means pass_fail=False is not critical."""
        bundle = make_bundle(total_score=90.0, pass_fail=False)
        policy = {**DEFAULT_GATE_POLICY, "require_pass_fail": False}
        result = gate.evaluate(bundle, policy=policy)
        assert result.severity == "ok"
        assert result.passed is True


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_none_bundle_returns_critical(self, gate):
        """None review_bundle → all metrics default to 0 → critical (score=0 < 70)."""
        result = gate.evaluate(None)
        assert result.severity == "critical"
        assert result.passed is False

    def test_empty_bundle_returns_critical(self, gate):
        """Empty dict → no metrics → score=0 → critical."""
        result = gate.evaluate({})
        assert result.passed is False

    def test_gate_result_bool(self, gate):
        """GateResult.__bool__ reflects passed."""
        ok_result = GateResult(passed=True, severity="ok")
        bad_result = GateResult(passed=False, severity="critical")
        assert bool(ok_result) is True
        assert bool(bad_result) is False

    def test_bundle_id_and_domain_in_result(self, gate):
        bundle = make_bundle(bundle_id="brv-abc123", domain="ci_change_control")
        result = gate.evaluate(bundle)
        assert result.bundle_id == "brv-abc123"
        assert result.domain == "ci_change_control"

    def test_singleton(self):
        """get_azul_result_gate() returns the same instance."""
        g1 = get_azul_result_gate()
        g2 = get_azul_result_gate()
        assert g1 is g2

    def test_default_policy_matches_sam(self):
        """DEFAULT_GATE_POLICY matches SAM's fw_result_gate defaults exactly."""
        assert DEFAULT_GATE_POLICY["min_score"] == 70.0
        assert DEFAULT_GATE_POLICY["warn_score"] == 80.0
        assert DEFAULT_GATE_POLICY["max_deny_count"] == 0
        assert DEFAULT_GATE_POLICY["max_oracle_mismatch"] == 0
        assert DEFAULT_GATE_POLICY["max_escalation_count"] == 2
        assert DEFAULT_GATE_POLICY["require_pass_fail"] is True
