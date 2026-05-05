"""
verification_engine.py — Core verify(ticket) function  (P0-6, P0-7)
====================================================================
Orchestrates the full Azul behavioral verification pipeline:

    ANALYZING   → ForgeScaffold blast-radius (codebase domains only)
    PROVISIONING → ForgeHarbor environment request
    EVALUATING  → ForgeWorks execute_planner_request
    GATING      → AzulResultGate evaluate (→ COMPLETED | REJECTED | WARNED)

Error handling rules (Core Spec §5.4):
    - Any integration failure → FAILED (never REJECTED)
    - REJECTED means the *behavioral evaluation* said "no"
    - ForgeHarbor environment is ALWAYS released in finally block
    - XP is awarded for COMPLETED and WARNED (not REJECTED / FAILED)
    - Training pair is emitted for DISTILLATION_PAIR tickets that pass

Usage:
    from azul.verification_engine import verify

    ticket = create_ticket(...)
    store.save(ticket)
    result = verify(ticket, store=store)
    # ticket.status is now a terminal status; ticket.verdict is set
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .ticket import AzulTicket, TicketStatus
from .ticket_store import AzulTicketStore
from .lifecycle import (
    begin_analysis,
    begin_provisioning,
    begin_evaluation,
    begin_gating,
    complete,
    reject,
    warn,
    fail,
)
from .gate import get_azul_result_gate
from .spec_builder import build_verification_spec
from .xp_ledger import XPLedger, calculate_xp
from .training_pairs import emit_training_pair
from .domain_config import requires_blast_radius
from .config import (
    AZUL_FORGE_HARBOR_ENABLED,
    AZUL_FORGE_SCAFFOLD_ENABLED,
    AZUL_GOVERNANCE_GUARDS_ENABLED,
    AZUL_NO_DESTRUCTIVE_REMEDIATION_GUARD_ENABLED,
)
from .governance_guards import (
    evaluate_diff_against_subprocess_guards,
    evaluate_no_destructive_remediation,
)

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _save(ticket: AzulTicket, store: Optional[AzulTicketStore]) -> None:
    """Persist the ticket if a store is provided."""
    if store:
        store.save(ticket)


def _transition_and_save(result, ticket: AzulTicket, store: Optional[AzulTicketStore]) -> None:
    """If a transition returned an error dict, apply fail() and save; otherwise just save."""
    if isinstance(result, dict) and result.get("status") == "error":
        fail(ticket, reason=str(result.get("error", {}).get("message", "Transition failed")))
        _save(ticket, store)


def _reject_for_guard_violation(
    ticket: AzulTicket,
    store: Optional[AzulTicketStore],
    violations: list[str],
) -> Dict[str, Any]:
    """Advance to GATING if needed, then issue a REJECTED verdict with guard details."""
    reason = "  |  ".join(violations)

    if ticket.status in (TicketStatus.SUBMITTED, TicketStatus.ANALYZING):
        res = begin_provisioning(ticket)
        if isinstance(res, dict):
            fail(ticket, reason="Cannot begin provisioning for guard rejection")
            _save(ticket, store)
            return _make_result("error", ticket, alerts=["STATUS_TRANSITION_FAILED"])
        _save(ticket, store)

    if ticket.status == TicketStatus.PROVISIONING:
        res = begin_evaluation(ticket)
        if isinstance(res, dict):
            fail(ticket, reason="Cannot begin evaluation for guard rejection")
            _save(ticket, store)
            return _make_result("error", ticket, alerts=["STATUS_TRANSITION_FAILED"])
        _save(ticket, store)

    if ticket.status == TicketStatus.EVALUATING:
        res = begin_gating(ticket)
        if isinstance(res, dict):
            fail(ticket, reason="Cannot begin gating for guard rejection")
            _save(ticket, store)
            return _make_result("error", ticket, alerts=["STATUS_TRANSITION_FAILED"])
        _save(ticket, store)

    if ticket.status != TicketStatus.GATING:
        fail(ticket, reason=f"Invalid status for guard rejection: {ticket.status.value}")
        _save(ticket, store)
        return _make_result("error", ticket, alerts=["STATUS_TRANSITION_FAILED"])

    ticket.gate_result = {
        "passed": False,
        "severity": "critical",
        "alerts": violations,
    }
    reject(ticket, reason=reason)
    _save(ticket, store)
    logger.info(
        "[verify] %s → REJECTED — governance guards failed: %s",
        ticket.ticket_id,
        reason,
    )
    return _make_result("ok", ticket, alerts=violations)


def _fail_closed_operational(
    ticket: AzulTicket,
    store: Optional[AzulTicketStore],
    *,
    reason: str,
    error_code: str,
    alerts: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    Mark ticket FAILED with manual review required metadata.
    Used when verifier infrastructure is degraded/unavailable.
    """
    fail(ticket, reason=reason, error_code=error_code)
    ticket.metadata["manual_review_required"] = True
    ticket.metadata["manual_review_reason"] = "operational_fail_closed"
    ticket.metadata["operational_friction"] = reason
    ticket.metadata["manual_review_flagged_at"] = ticket.updated_at
    _save(ticket, store)
    merged_alerts = list(alerts or [])
    if "MANUAL_REVIEW_REQUIRED" not in merged_alerts:
        merged_alerts.append("MANUAL_REVIEW_REQUIRED")
    return _make_result("error", ticket, alerts=merged_alerts)


def _notify_recursive_loop(
    ticket: AzulTicket,
    store: Optional[AzulTicketStore],
    ledger: Optional[XPLedger],
) -> None:
    """Best-effort loop callback. Never raises into verification path."""
    from .ticket import TERMINAL_STATUSES

    if ticket.status not in TERMINAL_STATUSES:
        return
    try:
        from .loop.orchestrator import LoopOrchestrator

        orchestrator = LoopOrchestrator(ticket_store=store, ledger=ledger)
        orchestrator.on_ticket_completed(ticket)
    except Exception as exc:
        logger.warning("[verify] recursive loop callback failed: %s", exc)


# ── Main engine ───────────────────────────────────────────────────────────────

def verify(
    ticket: AzulTicket,
    store: Optional[AzulTicketStore] = None,
    ledger: Optional[XPLedger] = None,
) -> Dict[str, Any]:
    """
    Run behavioral verification for the given ticket.

    Args:
        ticket: The AzulTicket in SUBMITTED status.
        store:  Ticket store for persistence.  Pass None to skip persistence
                (useful in tests).
        ledger: XP ledger.  Pass None to skip XP recording.

    Returns:
        A structured result dict:
        {
            "status":     "ok" | "error",
            "verdict":    "pass" | "reject" | None,
            "severity":   "ok" | "warn" | "critical" | None,
            "ticket_id":  str,
            "alerts":     list[str],
            "xp_awarded": int,
        }

    Never raises.  All exceptions are caught and result in ticket.status=FAILED.
    """
    from . import integrations  # noqa: F401 — ensure integrations are importable
    from .integrations import forge_harbor, forge_scaffold, forge_works

    environment_id: Optional[str] = None

    try:
        # ── Phase: Blast-radius analysis (codebase domains only) ─────────────
        if (
            AZUL_FORGE_SCAFFOLD_ENABLED
            and requires_blast_radius(ticket.domain)
            and ticket.target_files
        ):
            res = begin_analysis(ticket)
            if isinstance(res, dict):
                return _fail_closed_operational(
                    ticket,
                    store,
                    reason="Cannot begin analysis from current status",
                    error_code="STATUS_TRANSITION_FAILED",
                    alerts=["STATUS_TRANSITION_FAILED"],
                )

            _save(ticket, store)
            logger.info(f"[verify] {ticket.ticket_id} → ANALYZING")

            scaffold_result = forge_scaffold.analyze_blast_radius(
                target_files=ticket.target_files,
            )
            if scaffold_result["status"] == "ok":
                ticket.blast_radius = scaffold_result["payload"]["blast_radius"]
            else:
                err = scaffold_result.get("error", {})
                return _fail_closed_operational(
                    ticket,
                    store,
                    reason=f"ForgeScaffold error: {err.get('message')}",
                    error_code="FORGE_SCAFFOLD_ERROR",
                    alerts=[str(err)],
                )

        # ── Phase: Governance guard predicates (catalog-driven hard blocks) ──
        # Run before ForgeHarbor/ForgeWorks so explicit guard violations reject
        # deterministically even if downstream integrations are unavailable.
        if AZUL_GOVERNANCE_GUARDS_ENABLED:
            diff_text = str(ticket.change_payload.get("diff", ""))
            guard_violations = evaluate_diff_against_subprocess_guards(diff_text)
            if guard_violations:
                return _reject_for_guard_violation(ticket, store, guard_violations)
            if AZUL_NO_DESTRUCTIVE_REMEDIATION_GUARD_ENABLED:
                destructive_violations = evaluate_no_destructive_remediation(diff_text)
                if destructive_violations:
                    return _reject_for_guard_violation(ticket, store, destructive_violations)

        # ── Phase: Environment provisioning ───────────────────────────────────
        res = begin_provisioning(ticket)
        if isinstance(res, dict):
            return _fail_closed_operational(
                ticket,
                store,
                reason="Cannot begin provisioning from current status",
                error_code="STATUS_TRANSITION_FAILED",
                alerts=["STATUS_TRANSITION_FAILED"],
            )

        _save(ticket, store)
        logger.info(f"[verify] {ticket.ticket_id} → PROVISIONING")

        if AZUL_FORGE_HARBOR_ENABLED:
            harbor_result = forge_harbor.request_environment(ticket_id=ticket.ticket_id)
            if harbor_result["status"] == "ok":
                environment_id = harbor_result["payload"].get("environment_id")
                ticket.environment_id = environment_id
            else:
                err = harbor_result.get("error", {})
                return _fail_closed_operational(
                    ticket,
                    store,
                    reason=f"ForgeHarbor error: {err.get('message')}",
                    error_code="FORGE_HARBOR_ERROR",
                    alerts=[str(err)],
                )

        # ── Phase: Build spec and evaluate ────────────────────────────────────
        planner_spec = build_verification_spec(ticket)
        ticket.planner_spec = planner_spec

        res = begin_evaluation(ticket)
        if isinstance(res, dict):
            return _fail_closed_operational(
                ticket,
                store,
                reason="Cannot begin evaluation from current status",
                error_code="STATUS_TRANSITION_FAILED",
                alerts=["STATUS_TRANSITION_FAILED"],
            )

        _save(ticket, store)
        logger.info(f"[verify] {ticket.ticket_id} → EVALUATING")

        fw_result = forge_works.execute_verification(planner_spec)
        if fw_result["status"] != "ok":
            err = fw_result.get("error", {})
            return _fail_closed_operational(
                ticket,
                store,
                reason=f"ForgeWorks error: {err.get('message')}",
                error_code="FORGEWORKS_UNAVAILABLE",
                alerts=[str(err)],
            )

        if bool(fw_result.get("payload", {}).get("degraded")):
            degraded_reason = str(fw_result.get("payload", {}).get("degraded_reason", "degraded mode"))
            return _fail_closed_operational(
                ticket,
                store,
                reason=f"ForgeWorks degraded execution: {degraded_reason}",
                error_code="FORGEWORKS_DEGRADED",
                alerts=[degraded_reason],
            )

        review_bundle = fw_result["payload"].get("review_bundle")
        ticket.review_bundle = review_bundle

        # ── Phase: Gate evaluation ────────────────────────────────────────────
        res = begin_gating(ticket)
        if isinstance(res, dict):
            return _fail_closed_operational(
                ticket,
                store,
                reason="Cannot begin gating from current status",
                error_code="STATUS_TRANSITION_FAILED",
                alerts=["STATUS_TRANSITION_FAILED"],
            )

        _save(ticket, store)
        logger.info(f"[verify] {ticket.ticket_id} → GATING")

        gate = get_azul_result_gate()
        gate_result = gate.evaluate(review_bundle, policy=ticket.gate_policy)
        if gate_result.operational_error:
            reason = "Gate evaluation infrastructure error (fail-closed)."
            return _fail_closed_operational(
                ticket,
                store,
                reason=reason,
                error_code="GATE_EVALUATION_ERROR",
                alerts=gate_result.alerts,
            )

        ticket.gate_result = {
            "passed":   gate_result.passed,
            "severity": gate_result.severity,
            "alerts":   gate_result.alerts,
        }

        # ── Phase: Final verdict ──────────────────────────────────────────────
        if gate_result.severity == "critical":
            reason = "  |  ".join(gate_result.alerts) if gate_result.alerts else "Hard block"
            reject(ticket, reason=reason)
            _save(ticket, store)
            logger.info(f"[verify] {ticket.ticket_id} → REJECTED — {reason}")
            return _make_result("ok", ticket, alerts=gate_result.alerts)

        if gate_result.severity == "warn":
            reason = "  |  ".join(gate_result.alerts) if gate_result.alerts else "Soft alerts"
            warn(ticket, reason=reason, xp=0)          # sets status=WARNED, verdict="pass"
        else:
            complete(ticket, xp=0)                     # sets status=COMPLETED, verdict="pass"

        # Now ticket is in a terminal XP-eligible status — calculate and record XP
        xp = calculate_xp(ticket)
        ticket.xp_awarded = xp

        # ── Reward and training pair ──────────────────────────────────────────
        if ledger:
            ledger.award_xp(ticket)

        emit_training_pair(ticket)  # no-op unless distillation_pair + pass

        _save(ticket, store)
        logger.info(
            f"[verify] {ticket.ticket_id} → {ticket.status.value} "
            f"(xp={xp}, severity={gate_result.severity})"
        )
        return _make_result("ok", ticket, alerts=gate_result.alerts)

    except Exception as exc:
        logger.exception(f"[verify] Unhandled exception for {ticket.ticket_id}: {exc}")
        return _fail_closed_operational(
            ticket,
            store,
            reason=f"Unhandled verification error: {exc}",
            error_code="UNHANDLED_VERIFICATION_ERROR",
            alerts=[str(exc)],
        )

    finally:
        # Always release the environment — even on exception
        if environment_id:
            from .integrations import forge_harbor as _fh
            _fh.release_environment(environment_id)
        _notify_recursive_loop(ticket, store=store, ledger=ledger)


# ── Result builder ────────────────────────────────────────────────────────────

def _make_result(
    status: str,
    ticket: AzulTicket,
    alerts: Optional[list] = None,
) -> Dict[str, Any]:
    return {
        "status":     status,
        "verdict":    ticket.verdict,
        "severity":   ticket.gate_result.get("severity") if ticket.gate_result else None,
        "ticket_id":  ticket.ticket_id,
        "ticket_status": ticket.status.value,
        "alerts":     alerts or [],
        "xp_awarded": ticket.xp_awarded,
    }
