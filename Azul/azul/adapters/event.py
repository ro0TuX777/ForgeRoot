"""
adapters/event.py — Event/message-bus adapter
==============================================
Handles change-event payloads arriving from an internal message bus,
SAM's evolution loop, or any event-driven trigger.

Event payload schema:
{
    "event_type":    str,           # e.g. "patch_proposed", "refactor_complete"
    "source_system": str,           # e.g. "sam_evolution", "ci_pipeline"
    "ticket_type":   str,           # one of TicketType values
    "domain":        str,
    "change_summary": str,
    "change_payload": dict,
    "target_files":  list[str],
    "priority":      str | None,
    "mode":          str | None,
    "metadata":      dict | None,
}

Returns a structured verdict dict (same shape as api.py _ok / _err).
Never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..ticket import create_ticket, TicketType, TicketPriority
from ..ticket_store import AzulTicketStore
from ..xp_ledger import XPLedger
from ..verification_engine import verify

logger = logging.getLogger(__name__)

# ── Validation ─────────────────────────────────────────────────────────────────

REQUIRED = {"event_type", "source_system", "ticket_type", "domain", "change_summary"}

# Map well-known event types → ticket type overrides
_EVENT_TYPE_MAP: Dict[str, str] = {
    "patch_proposed":    TicketType.CI_GATE.value,
    "refactor_complete": TicketType.REFACTOR.value,
    "security_advisory": TicketType.SECURITY_PATCH.value,
    "policy_update":     TicketType.POLICY_COMPLIANCE.value,
    "distillation_emit": TicketType.DISTILLATION_PAIR.value,
}


def _resolve_ticket_type(event: Dict[str, Any]) -> str:
    """
    Resolve final ticket_type:
      1. Explicit event payload field takes priority.
      2. Fall back to event_type → ticket_type mapping.
    """
    explicit = event.get("ticket_type")
    if explicit and explicit in {t.value for t in TicketType}:
        return explicit
    event_type = event.get("event_type", "")
    return _EVENT_TYPE_MAP.get(event_type, TicketType.CI_GATE.value)


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": data, "error": None}


def _err(msg: str) -> Dict[str, Any]:
    return {"status": "error", "data": None, "error": msg}


# ── Public API ─────────────────────────────────────────────────────────────────

def handle_event(
    event:  Dict[str, Any],
    store:  Optional[AzulTicketStore] = None,
    ledger: Optional[XPLedger]        = None,
) -> Dict[str, Any]:
    """
    Handle an inbound event payload and run Azul verification.

    Args:
        event:  Event payload dict.
        store:  Ticket store for persistence.
        ledger: XP ledger.

    Returns _ok(verdict_data) or _err(message).  Never raises.
    """
    missing = REQUIRED - set(event.keys())
    if missing:
        return _err(f"Missing required event fields: {sorted(missing)}")

    ticket_type = _resolve_ticket_type(event)

    try:
        ticket = create_ticket(
            ticket_type    = ticket_type,
            domain         = event["domain"],
            change_summary = event["change_summary"],
            change_payload = event.get("change_payload", {}),
            target_files   = event.get("target_files", []),
            priority       = event.get("priority") or TicketPriority.NORMAL.value,
            mode           = event.get("mode", "shadow"),
            metadata       = {
                "event_type":    event.get("event_type"),
                "source_system": event.get("source_system"),
                **(event.get("metadata") or {}),
            },
            source = {
                "adapter":       "event",
                "event_type":    event.get("event_type"),
                "source_system": event.get("source_system"),
            },
        )
    except (ValueError, KeyError) as exc:
        return _err(f"Ticket creation error: {exc}")

    logger.info(
        f"[event_adapter] ticket={ticket.ticket_id} "
        f"event_type={event.get('event_type')} "
        f"source={event.get('source_system')}"
    )

    result = verify(ticket, store=store, ledger=ledger)

    return _ok({
        "ticket_id":     result.get("ticket_id"),
        "verdict":       result.get("verdict"),
        "severity":      result.get("severity"),
        "ticket_status": result.get("ticket_status"),
        "alerts":        result.get("alerts", []),
        "xp_awarded":    result.get("xp_awarded", 0),
    })
