"""
adapters/api.py — Lightweight HTTP-style API adapter
=====================================================
Provides a pure-Python, framework-agnostic API handler.
Receives requests as plain dicts (WSGI or any HTTP glue can convert).

This is NOT a web server.  Phase 5's daemon.py exposes this via a
simple socket listener.  The design keeps zero framework dependencies
for Phase 4 (as per the Implementation Plan).

Request dict schema:
{
    "action":  "submit" | "get_ticket" | "list" | "health",
    "payload": dict | None,
}

Response dict schema:
{
    "status":  "ok" | "error",
    "data":    dict | list | None,
    "error":   str | None,
}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..ticket import create_ticket, TicketType, TicketPriority
from ..ticket_store import AzulTicketStore
from ..xp_ledger import XPLedger
from ..verification_engine import verify

logger = logging.getLogger(__name__)


# ── Response helpers ───────────────────────────────────────────────────────────

def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": data, "error": None}


def _err(msg: str, code: str = "BAD_REQUEST") -> Dict[str, Any]:
    return {"status": "error", "data": None, "error": msg, "code": code}


# ── Handler ────────────────────────────────────────────────────────────────────

class AzulAPIHandler:
    """
    Stateless request handler.  Injected with a store and ledger on creation.

    Usage (in daemon or test):
        handler = AzulAPIHandler(store=store, ledger=ledger)
        response = handler.handle({"action": "submit", "payload": {...}})
    """

    SUPPORTED_ACTIONS = frozenset({"submit", "get_ticket", "list", "health"})

    def __init__(
        self,
        store:  Optional[AzulTicketStore] = None,
        ledger: Optional[XPLedger]        = None,
    ) -> None:
        self._store  = store
        self._ledger = ledger

    # ── Dispatch ───────────────────────────────────────────────────────────────

    def handle(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch a request dict to the appropriate action handler.
        Never raises.
        """
        if not isinstance(request, dict):
            return _err("Request must be a dict", "INVALID_REQUEST")

        action  = request.get("action", "")
        payload = request.get("payload") or {}

        if action not in self.SUPPORTED_ACTIONS:
            return _err(
                f"Unknown action '{action}'. Supported: {sorted(self.SUPPORTED_ACTIONS)}",
                "UNKNOWN_ACTION",
            )

        try:
            return getattr(self, f"_handle_{action}")(payload)
        except Exception as exc:
            logger.exception(f"[AzulAPIHandler] Unhandled error in action={action}: {exc}")
            return _err(str(exc), "INTERNAL_ERROR")

    # ── Action handlers ────────────────────────────────────────────────────────

    def _handle_submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit a change for verification and return the verdict synchronously.

        Required payload fields: ticket_type, domain, change_summary.
        """
        required = {"ticket_type", "domain", "change_summary"}
        missing = required - set(payload.keys())
        if missing:
            return _err(f"Missing required fields: {sorted(missing)}")

        try:
            ticket = create_ticket(
                ticket_type    = payload["ticket_type"],
                domain         = payload["domain"],
                change_summary = payload["change_summary"],
                change_payload = payload.get("change_payload", {}),
                target_files   = payload.get("target_files", []),
                priority       = payload.get("priority", TicketPriority.NORMAL.value),
                mode           = payload.get("mode", "shadow"),
                gate_policy    = payload.get("gate_policy"),
                metadata       = payload.get("metadata", {}),
                source         = {"adapter": "api", **payload.get("source", {})},
            )
        except (ValueError, KeyError) as exc:
            return _err(f"Ticket creation error: {exc}")

        result = verify(ticket, store=self._store, ledger=self._ledger)

        return _ok({
            "ticket_id":     result.get("ticket_id"),
            "verdict":       result.get("verdict"),
            "severity":      result.get("severity"),
            "ticket_status": result.get("ticket_status"),
            "alerts":        result.get("alerts", []),
            "xp_awarded":    result.get("xp_awarded", 0),
        })

    def _handle_get_ticket(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return a stored ticket by ID."""
        ticket_id = payload.get("ticket_id")
        if not ticket_id:
            return _err("payload.ticket_id is required")

        if not self._store:
            return _err("No ticket store configured", "NO_STORE")

        ticket = self._store.get(ticket_id)
        if ticket is None:
            return _err(f"Ticket '{ticket_id}' not found", "NOT_FOUND")

        return _ok(ticket.to_dict())

    def _handle_list(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """List tickets with optional status / type filter."""
        if not self._store:
            return _err("No ticket store configured", "NO_STORE")

        status      = payload.get("status")
        ticket_type = payload.get("ticket_type")
        tickets     = self._store.list(status=status, ticket_type=ticket_type)

        return _ok({
            "tickets": [t.to_dict() for t in tickets],
            "count":   len(tickets),
        })

    def _handle_health(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Health check endpoint — always returns ok in Phase 4 (Phase 5 adds queue depth)."""
        return _ok({"healthy": True, "phase": 4})
