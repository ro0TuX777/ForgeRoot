"""
gate.py — AzulResultGate  (P0-4)
=================================
Extracted and adapted from SAM's ``fw_result_gate.py``.

Key adaptation: SAM's gate operates on a ``FWJob`` object that has named
attributes (``job.total_score``, ``job.pass_fail``, etc.).  Azul operates on
plain ``review_bundle`` dicts returned by ``execute_planner_request()``.
The evaluation *logic* (thresholds, severities, alert text) is identical to
SAM — only the data-access layer changes.

Severity levels
---------------
ok       → gate passed, no issues
warn     → soft alert (deny_count, oracle_mismatch, escalation, score < warn_score)
critical → hard block (score < min_score OR pass_fail=False)

Default gate policy
-------------------
Matches SAM defaults exactly (Core Spec §5.3):

    min_score:            70.0   CRITICAL if below
    warn_score:           80.0   WARN if below (but >= min_score)
    max_deny_count:       0      WARN if > 0
    max_oracle_mismatch:  0      WARN if > 0
    max_escalation_count: 2      WARN if > 2
    require_pass_fail:    True   CRITICAL if pass_fail=False

Usage
-----
    gate = get_azul_result_gate()
    result = gate.evaluate(ticket.review_bundle, policy=ticket.gate_policy)
    # result.passed: bool  — True unless severity=="critical"
    # result.severity: str — "ok" | "warn" | "critical"
    # result.alerts: list[str] — human-readable descriptions of triggered checks
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Default gate policy ───────────────────────────────────────────────────────

DEFAULT_GATE_POLICY: Dict[str, Any] = {
    "min_score":             70.0,   # CRITICAL if score below this
    "warn_score":            80.0,   # WARN if score below this (but >= min_score)
    "max_deny_count":        0,      # WARN if > 0 deny decisions
    "max_oracle_mismatch":   0,      # WARN if > 0 oracle mismatches
    "max_escalation_count":  2,      # WARN if escalations exceed this
    "require_pass_fail":     True,   # CRITICAL if pass_fail=False
}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class GateResult:
    """Result of evaluating a ReviewBundle against a gate policy."""
    passed:    bool
    severity:  str              # "ok" | "warn" | "critical"
    alerts:    List[str] = field(default_factory=list)
    bundle_id: str = ""
    domain:    str = ""
    operational_error: bool = False

    def __bool__(self) -> bool:
        return self.passed


# ── Gate class ────────────────────────────────────────────────────────────────

class AzulResultGate:
    """
    Evaluates a ForgeWorks ReviewBundle dict against a configurable policy
    and returns a structured GateResult.

    This is functionally equivalent to SAM's FWResultGate except it reads
    from a dict (``review_bundle``) rather than a FWJob object.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def evaluate(
        self,
        review_bundle: Optional[Dict[str, Any]],
        policy: Optional[Dict[str, Any]] = None,
    ) -> GateResult:
        """
        Evaluate a ReviewBundle against the given policy.

        Args:
            review_bundle: The dict returned by ForgeWorks in the receipt's
                           ``review_bundle`` key.  If None, treats all metrics
                           as zero (worst-case defaults).
            policy:        Per-ticket gate policy override.  Any keys present
                           override the corresponding DEFAULT_GATE_POLICY key.
                           Pass None to use defaults for all keys.

        Returns a GateResult — never raises.
        """
        try:
            merged_policy = {**DEFAULT_GATE_POLICY, **(policy or {})}
            return self._evaluate(review_bundle or {}, merged_policy)
        except Exception as exc:
            logger.warning(f"[AzulResultGate] evaluate() error (fail-closed): {exc}")
            return GateResult(
                passed=False,
                severity="critical",
                alerts=[f"Gate evaluation error: {exc}"],
                operational_error=True,
            )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _evaluate(
        self, bundle: Dict[str, Any], policy: Dict[str, Any]
    ) -> GateResult:
        alerts: List[str] = []
        severity = "ok"

        # Extract metrics from the ReviewBundle dict
        # ForgeWorks puts metrics at bundle["metrics"] (ForgeWorksReviewBundle)
        metrics = bundle.get("metrics") or {}

        score       = float(metrics.get("total_score", 0.0))
        pass_fail   = bool(metrics.get("pass_fail", False))
        deny_count  = int(metrics.get("deny_count", 0))
        oracle_miss = int(metrics.get("oracle_mismatch_count", 0))
        escalations = int(metrics.get("escalation_count", 0))

        # Bundle-level identifiers (for traceability)
        bundle_id = bundle.get("bundle_id", "")
        domain    = bundle.get("summary", {}).get("domain", "") or ""

        min_score         = float(policy["min_score"])
        warn_score        = float(policy["warn_score"])
        max_deny          = int(policy["max_deny_count"])
        max_oracle        = int(policy["max_oracle_mismatch"])
        max_escalations   = int(policy["max_escalation_count"])
        require_pass_fail = bool(policy["require_pass_fail"])

        # ── Critical checks (hard blocks) ─────────────────────────────────────
        if score < min_score:
            alerts.append(
                f"Score {score:.1f} is below minimum threshold {min_score:.1f}"
            )
            severity = "critical"

        if require_pass_fail and not pass_fail:
            alerts.append("Pipeline completed with pass_fail=False")
            if severity != "critical":
                severity = "critical"

        # ── Warn checks (soft alerts) ─────────────────────────────────────────
        if deny_count > max_deny:
            alerts.append(
                f"deny_count={deny_count} exceeds max_deny_count={max_deny}"
            )
            if severity == "ok":
                severity = "warn"

        if oracle_miss > max_oracle:
            alerts.append(
                f"oracle_mismatch_count={oracle_miss} exceeds max_oracle_mismatch={max_oracle}"
            )
            if severity == "ok":
                severity = "warn"

        if escalations > max_escalations:
            alerts.append(
                f"escalation_count={escalations} exceeds max_escalation_count={max_escalations}"
            )
            if severity == "ok":
                severity = "warn"

        if warn_score > min_score and score < warn_score and severity == "ok":
            alerts.append(
                f"Score {score:.1f} is below warn threshold {warn_score:.1f}"
            )
            severity = "warn"

        passed = severity != "critical"

        return GateResult(
            passed=passed,
            severity=severity,
            alerts=alerts,
            bundle_id=bundle_id,
            domain=domain,
        )


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[AzulResultGate] = None


def get_azul_result_gate() -> AzulResultGate:
    """Return the module-level singleton AzulResultGate."""
    global _instance
    if _instance is None:
        _instance = AzulResultGate()
    return _instance
