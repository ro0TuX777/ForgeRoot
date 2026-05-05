"""
ForgeWorks ReviewBundle
=======================
Aggregates all pipeline evidence (receipt, metrics, artifacts) into a single
passable object that SAM can inspect to approve, reject, or replan.

Assembly happens inside execute_planner_request(), after build_planner_receipt()
returns, before the receipt dict is handed back to SAM.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Gate-number → human label mapping
# Must stay in sync with execute_planner_request gate numbering.
# ---------------------------------------------------------------------------
_GATE_NAMES: Dict[int, str] = {
    0: "spec_validation",
    1: "spec_validation",   # gate 1 = spec validated
    2: "source_compile",    # gate 2 = source compiled
    3: "ingest",            # gate 3 = ingest passed
    4: "normalize",         # gate 4 = normalize passed
    5: "validate",          # gate 5 = workcell validated
    6: "run",               # gate 6 = run completed
    7: "score",             # gate 7 = score computed
    8: "report",            # gate 8 = report generated
    9: None,                # gate 9 = full success, no failure gate
}

# Risk levels in ascending order — used for highest_risk_level derivation.
_RISK_ORDER = ("low", "med", "high", "critical")

# Action-id → (risk_tier, side_effect) (mirrors sam_like_runner._action_risk)
_ACTION_RISKS: Dict[str, str] = {
    "phase.scout":                "low",
    "phase.legislator":           "low",
    "phase.builder":              "med",
    "execute_sandbox_test":       "critical",
    "deploy_verified_artifact":   "high",
}

_MODE_MAX_RISK: Dict[str, str] = {
    "shadow":     "med",      # Builder is the highest in shadow (Deployer is no-op)
    "supervised": "high",     # Deployer gate is active
    "ramped":     "high",
}


def _failure_gate_name(gates_passed: int) -> Optional[str]:
    """Return the name of the gate that failed, given how many gates passed."""
    if gates_passed >= 9:
        return None
    # The gate that failed is the one *after* the last passed gate.
    failed_at = gates_passed + 1
    # Clamp: if we somehow get a number outside the map, fall back to nearest.
    return _GATE_NAMES.get(failed_at, _GATE_NAMES.get(min(failed_at, 8)))


def _highest_risk_level(spec: Dict[str, Any]) -> str:
    """
    Derive highest_risk_level from the run mode.
    In shadow mode the Deployer is skipped (no-op), so Builder (med) is the
    highest active risk.  In supervised/ramped the Deployer gate is live (high).
    """
    mode = spec.get("mode", "shadow")
    return _MODE_MAX_RISK.get(mode, "med")


def _make_bundle_id(spec_id: str, ts: str) -> str:
    """Deterministic but unique ID for the bundle."""
    raw = f"{spec_id}:{ts}"
    return "brv-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ForgeWorksReviewBundle:
    """
    Aggregated evidence bundle for a single ForgeWorks pipeline run.
    Assembled after build_planner_receipt, returned as review_bundle inside
    the planner receipt dict.
    """

    # Identity
    bundle_id:    str
    spec_id:      str
    request_id:   str
    created_at:   str
    bundle_status: str  # always "pending_review" on creation

    # Pipeline outcome
    summary:       Dict[str, Any]
    gates_passed:  int
    failure_gate:  Optional[str]
    failure_reason: Optional[str]

    # Metrics (lifted from receipt.metrics)
    metrics: Dict[str, Any]

    # Artifact file paths (keys: run_summary, decision_ledger, score_json, report_md)
    artifacts: Dict[str, Optional[str]]

    # Risk
    risk_assessment: Dict[str, Any]

    # Review fields — populated later by SAM or a human reviewer
    reviewer_id:          Optional[str] = field(default=None)
    review_decision:      Optional[str] = field(default=None)   # approved | rejected | revision_requested
    review_notes:         Optional[str] = field(default=None)
    review_completed_at:  Optional[str] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _build_one_line(
    mode: str,
    domain: str,
    ticket_count: int,
    total_score: float,
    pass_fail: bool,
    failure_gate: Optional[str],
) -> str:
    if failure_gate:
        return f"{mode} run on {domain}: failed at {failure_gate} gate"
    verdict = "PASS" if pass_fail else "FAIL"
    return (
        f"{mode} run on {domain}: {ticket_count} ticket"
        f"{'s' if ticket_count != 1 else ''}, "
        f"score {total_score:.1f}, {verdict}"
    )


def _build_summary(
    spec: Dict[str, Any],
    receipt_status: str,
    failure_gate: Optional[str],
    run_summary: Optional[Dict[str, Any]],
    score_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    domain = spec.get("domain", "unknown")
    mode = spec.get("mode", "shadow")
    goal = spec.get("goal", "")
    run = run_summary or {}
    score = score_result or {}

    ticket_count = int(run.get("ticket_count", 0))
    decision_count = int(run.get("decision_count", 0))
    approval_count = run.get("approval_count")  # may be None for shadow
    total_score = float(score.get("total_score", 0.0))
    pass_fail = bool(score.get("pass_fail", False))

    return {
        "domain":           domain,
        "mode":             mode,
        "goal":             goal,
        "ticket_count":     ticket_count,
        "decision_count":   decision_count,
        "approval_count":   approval_count,
        "total_score":      total_score,
        "pass_fail":        pass_fail,
        "pipeline_status":  receipt_status,
        "failure_gate":     failure_gate or "none",
        "one_line":         _build_one_line(
            mode, domain, ticket_count, total_score, pass_fail, failure_gate
        ),
    }


def _build_risk_assessment(
    spec: Dict[str, Any],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    loop_policy = spec.get("loop_policy") or {}
    target_score = float(loop_policy.get("target_score", 0.0))
    total_score = float(metrics.get("total_score", 0.0))

    return {
        "highest_risk_level":    _highest_risk_level(spec),
        "deny_count":            int(metrics.get("deny_count", 0)),
        "oracle_mismatch_count": int(metrics.get("oracle_mismatch_count", 0)),
        "escalation_count":      int(metrics.get("escalation_count", 0)),
        "has_drift_events":      bool(int(metrics.get("drift_events_applied", 0))),
        "pass_fail":             bool(metrics.get("pass_fail", False)),
        "score_below_threshold": total_score < target_score,
    }


# ---------------------------------------------------------------------------
# Public assembly function
# ---------------------------------------------------------------------------

def assemble_review_bundle(
    spec: Dict[str, Any],
    receipt: Dict[str, Any],
    run_summary: Optional[Dict[str, Any]],
    score_result: Optional[Dict[str, Any]],
) -> ForgeWorksReviewBundle:
    """
    Build a ForgeWorksReviewBundle from a completed (or partially completed)
    pipeline run.

    Handles partial completions gracefully: if the pipeline failed at gate 3
    there is no run_summary or score_result.  The bundle is still assembled
    with null/empty values for stages that did not execute.

    Parameters
    ----------
    spec:         The raw planner spec dict that triggered this run.
    receipt:      The planner_receipt dict produced by build_planner_receipt().
    run_summary:  Parsed run_summary.json payload, or None if run never completed.
    score_result: Parsed score.json payload, or None if scoring never completed.
    """
    ts = datetime.now(timezone.utc).isoformat()

    gates_passed = int(receipt.get("gates_passed", 0))
    failure_gate = _failure_gate_name(gates_passed)
    failure_reason = receipt.get("failure_reason")
    if failure_reason == "NONE":
        failure_reason = None

    receipt_status = receipt.get("status", "REPLAN")
    metrics = dict(receipt.get("metrics") or {})

    # Artifact paths — may be partially populated on failure.
    raw_artifacts = receipt.get("artifacts") or {}
    artifacts: Dict[str, Optional[str]] = {
        "run_summary":    raw_artifacts.get("run_summary"),
        "decision_ledger": raw_artifacts.get("decision_ledger"),
        "score_json":     raw_artifacts.get("score_json"),
        "report_md":      raw_artifacts.get("report_md"),
    }

    bundle_id = _make_bundle_id(spec.get("spec_id", "unknown"), ts)

    summary = _build_summary(
        spec=spec,
        receipt_status=receipt_status,
        failure_gate=failure_gate,
        run_summary=run_summary,
        score_result=score_result,
    )

    risk_assessment = _build_risk_assessment(spec=spec, metrics=metrics)

    return ForgeWorksReviewBundle(
        bundle_id=bundle_id,
        spec_id=spec.get("spec_id", "unknown"),
        request_id=spec.get("request_id", "unknown"),
        created_at=ts,
        bundle_status="pending_review",
        summary=summary,
        gates_passed=gates_passed,
        failure_gate=failure_gate,
        failure_reason=failure_reason,
        metrics=metrics,
        artifacts=artifacts,
        risk_assessment=risk_assessment,
    )
