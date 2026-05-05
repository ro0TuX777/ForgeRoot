"""
lifecycle.py — Azul status machine  (P0-2)
==========================================
Implements ``can_transition()`` and named transition helpers.
Follows the same pattern as ForgeHarbor's lifecycle_engine.py.

All transitions check validity via the guard before mutating the ticket.
Every function returns the (mutated) ticket on success or a structured
error dict on failure — callers check ``["status"] == "error"``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Union

from .ticket import AzulTicket, TicketStatus, TERMINAL_STATUSES


# ── Transition table (Core Spec §4.3) ────────────────────────────────────────

_VALID_TRANSITIONS: Dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.SUBMITTED: [
        TicketStatus.ANALYZING,     # codebase domains
        TicketStatus.PROVISIONING,  # non-codebase domains skip analysis
        TicketStatus.FAILED,
    ],
    TicketStatus.ANALYZING: [
        TicketStatus.PROVISIONING,
        TicketStatus.FAILED,
    ],
    TicketStatus.PROVISIONING: [
        TicketStatus.EVALUATING,
        TicketStatus.FAILED,
    ],
    TicketStatus.EVALUATING: [
        TicketStatus.GATING,
        TicketStatus.FAILED,
    ],
    TicketStatus.GATING: [
        TicketStatus.COMPLETED,
        TicketStatus.REJECTED,
        TicketStatus.WARNED,
        TicketStatus.FAILED,
    ],
    # Terminal statuses: no further transitions
    TicketStatus.COMPLETED:    [],
    TicketStatus.REJECTED:     [],
    TicketStatus.WARNED:       [],
    TicketStatus.FAILED:       [],
}


# ── Guard ─────────────────────────────────────────────────────────────────────

def can_transition(from_status: TicketStatus, to_status: TicketStatus) -> bool:
    """
    Return True iff the (from_status → to_status) edge is in the legal topology.

    Any status can transition to FAILED (unrecoverable error at any stage).
    Terminal statuses cannot transition to anything else.
    """
    if from_status in TERMINAL_STATUSES:
        return False
    return to_status in _VALID_TRANSITIONS.get(from_status, [])


# ── Internal helpers ──────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _transition_error(from_s: TicketStatus, to_s: TicketStatus) -> Dict[str, Any]:
    return {
        "status": "error",
        "error": {
            "code": "INVALID_TRANSITION",
            "message": (
                f"Cannot transition ticket from {from_s.value} to {to_s.value}"
            ),
            "details": {
                "from_status": from_s.value,
                "to_status":   to_s.value,
            },
        },
    }


def _apply(ticket: AzulTicket, to_status: TicketStatus) -> AzulTicket:
    """Mutate status + updated_at in place and return the ticket."""
    ticket.status = to_status
    ticket.updated_at = _now_iso()
    return ticket


# ── Named transition functions ────────────────────────────────────────────────

def begin_analysis(ticket: AzulTicket) -> Union[AzulTicket, Dict[str, Any]]:
    """
    SUBMITTED → ANALYZING
    Called when a codebase-domain ticket is dequeued for blast-radius analysis.
    """
    if not can_transition(ticket.status, TicketStatus.ANALYZING):
        return _transition_error(ticket.status, TicketStatus.ANALYZING)
    return _apply(ticket, TicketStatus.ANALYZING)


def begin_provisioning(ticket: AzulTicket) -> Union[AzulTicket, Dict[str, Any]]:
    """
    SUBMITTED → PROVISIONING  (non-codebase domains)
    ANALYZING → PROVISIONING  (codebase domains, after ForgeScaffold)
    """
    if not can_transition(ticket.status, TicketStatus.PROVISIONING):
        return _transition_error(ticket.status, TicketStatus.PROVISIONING)
    return _apply(ticket, TicketStatus.PROVISIONING)


def begin_evaluation(ticket: AzulTicket) -> Union[AzulTicket, Dict[str, Any]]:
    """
    PROVISIONING → EVALUATING
    ForgeHarbor has assigned an environment.
    """
    if not can_transition(ticket.status, TicketStatus.EVALUATING):
        return _transition_error(ticket.status, TicketStatus.EVALUATING)
    return _apply(ticket, TicketStatus.EVALUATING)


def begin_gating(ticket: AzulTicket) -> Union[AzulTicket, Dict[str, Any]]:
    """
    EVALUATING → GATING
    ForgeWorks pipeline complete, ReviewBundle returned.
    """
    if not can_transition(ticket.status, TicketStatus.GATING):
        return _transition_error(ticket.status, TicketStatus.GATING)
    return _apply(ticket, TicketStatus.GATING)


def complete(ticket: AzulTicket, xp: int = 0) -> Union[AzulTicket, Dict[str, Any]]:
    """
    GATING → COMPLETED
    Gate verdict = pass (no warnings).  XP awarded.
    """
    if not can_transition(ticket.status, TicketStatus.COMPLETED):
        return _transition_error(ticket.status, TicketStatus.COMPLETED)
    ticket.xp_awarded = xp
    ticket.verdict = "pass"
    ticket.completed_at = _now_iso()
    return _apply(ticket, TicketStatus.COMPLETED)


def reject(
    ticket: AzulTicket,
    reason: str = "Behavioral verification failed",
) -> Union[AzulTicket, Dict[str, Any]]:
    """
    GATING → REJECTED
    Gate verdict = reject (hard block: score below min or pass_fail=False).
    """
    if not can_transition(ticket.status, TicketStatus.REJECTED):
        return _transition_error(ticket.status, TicketStatus.REJECTED)
    ticket.verdict = "reject"
    ticket.verdict_reason = reason
    ticket.xp_awarded = 0
    ticket.completed_at = _now_iso()
    return _apply(ticket, TicketStatus.REJECTED)


def warn(
    ticket: AzulTicket,
    reason: str = "Verification passed with warnings",
    xp: int = 0,
) -> Union[AzulTicket, Dict[str, Any]]:
    """
    GATING → WARNED
    Gate verdict = pass with soft alerts (deny_count, oracle_mismatch, etc.).
    XP is still awarded.
    """
    if not can_transition(ticket.status, TicketStatus.WARNED):
        return _transition_error(ticket.status, TicketStatus.WARNED)
    ticket.verdict = "pass"
    ticket.verdict_reason = reason
    ticket.xp_awarded = xp
    ticket.completed_at = _now_iso()
    return _apply(ticket, TicketStatus.WARNED)


def fail(
    ticket: AzulTicket,
    reason: str = "Operational failure",
    error_code: str = "PIPELINE_ERROR",
) -> Union[AzulTicket, Dict[str, Any]]:
    """
    Any non-terminal → FAILED
    Unrecoverable operational error (not a behavioral rejection).
    XP is never awarded.
    """
    if not can_transition(ticket.status, TicketStatus.FAILED):
        return _transition_error(ticket.status, TicketStatus.FAILED)
    ticket.verdict = None          # FAILED is not a behavioral verdict
    ticket.verdict_reason = reason
    ticket.xp_awarded = 0
    ticket.completed_at = _now_iso()
    if "error_code" not in ticket.metadata:
        ticket.metadata["error_code"] = error_code
    return _apply(ticket, TicketStatus.FAILED)
