"""
ticket_store.py — Persistent JSON ticket storage  (P0-3)
=========================================================
Stores tickets as individual JSON files:

    azul_data/tickets/active/<ticket_id>.json      (SUBMITTED → GATING)
    azul_data/tickets/completed/<ticket_id>.json   (COMPLETED | REJECTED | WARNED | FAILED)

Terminal-status tickets are moved from active/ to completed/ automatically.
List operations scan directories; no in-memory cache (designed for single-process
Phase 1 — locking is added in Phase 5 when the queue worker runs concurrently).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ticket import AzulTicket, TicketStatus, TicketType, TERMINAL_STATUSES
from .config import TICKETS_ACTIVE_DIR, TICKETS_COMPLETED_DIR


# ── Storage roots (overridable for tests via AzulTicketStore.__init__) ────────

class AzulTicketStore:
    """
    Thin file-based ticket store.

    Args:
        active_dir:    Directory for in-progress tickets.
        completed_dir: Directory for terminal-status tickets.

    Both directories are created on first use if they don't exist.
    """

    def __init__(
        self,
        active_dir:    Optional[Path] = None,
        completed_dir: Optional[Path] = None,
    ) -> None:
        self._active    = Path(active_dir    or TICKETS_ACTIVE_DIR)
        self._completed = Path(completed_dir or TICKETS_COMPLETED_DIR)
        self._active.mkdir(parents=True, exist_ok=True)
        self._completed.mkdir(parents=True, exist_ok=True)

    # ── Write ──────────────────────────────────────────────────────────────────

    def _latest_completed_chain_hash(self, *, exclude_ticket_id: str = "") -> str:
        latest_path: Optional[Path] = None
        latest_ts = -1.0
        for path in self._completed.glob("azul-*.json"):
            if exclude_ticket_id and path.name == f"{exclude_ticket_id}.json":
                continue
            try:
                ts = path.stat().st_mtime
            except OSError:
                continue
            if ts > latest_ts:
                latest_ts = ts
                latest_path = path
        if latest_path is None:
            return ""
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
        audit = metadata.get("audit", {}) if isinstance(metadata, dict) else {}
        if isinstance(audit, dict):
            return str(audit.get("chain_hash", ""))
        return ""

    def _attach_audit_signature(self, ticket: AzulTicket) -> None:
        """
        Add tamper-evident audit fields.
        Signature covers verdict + contract_version + model_id (+ chain linkage).
        """
        contract_version = str(
            ticket.metadata.get("contract_version")
            or (ticket.review_bundle or {}).get("summary", {}).get("contract_version")
            or "unknown"
        )
        model_id = str(
            ticket.metadata.get("model_id")
            or (ticket.review_bundle or {}).get("summary", {}).get("model_id")
            or "unknown"
        )
        prev_chain_hash = self._latest_completed_chain_hash(exclude_ticket_id=ticket.ticket_id)
        payload = {
            "ticket_id": ticket.ticket_id,
            "verdict": ticket.verdict,
            "verdict_reason": ticket.verdict_reason,
            "contract_version": contract_version,
            "model_id": model_id,
            "updated_at": ticket.updated_at,
            "prev_chain_hash": prev_chain_hash,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        key = os.environ.get("AZUL_AUDIT_SIGNING_KEY", "dev-insecure-key-change-me")
        signature = hmac.new(
            key.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        chain_hash = hashlib.sha256(
            f"{prev_chain_hash}:{payload_hash}:{signature}".encode("utf-8")
        ).hexdigest()

        ticket.metadata.setdefault("audit", {})
        ticket.metadata["audit"] = {
            "algorithm": "HMAC-SHA256",
            "key_id": os.environ.get("AZUL_AUDIT_SIGNING_KEY_ID", "local-dev"),
            "payload_hash": payload_hash,
            "signature": signature,
            "prev_chain_hash": prev_chain_hash,
            "chain_hash": chain_hash,
            "signed_fields": ["verdict", "contract_version", "model_id"],
            "contract_version": contract_version,
            "model_id": model_id,
        }

    def save(self, ticket: AzulTicket) -> None:
        """
        Persist or update a ticket.

        If the ticket is in a terminal status it is written to completed/ and
        any stale copy in active/ is removed.  Non-terminal tickets are always
        written to active/.
        """
        self._attach_audit_signature(ticket)
        data = json.dumps(ticket.to_dict(), indent=2)
        if ticket.status in TERMINAL_STATUSES:
            dest = self._completed / f"{ticket.ticket_id}.json"
            dest.write_text(data, encoding="utf-8")
            stale = self._active / f"{ticket.ticket_id}.json"
            if stale.exists():
                stale.unlink()
        else:
            dest = self._active / f"{ticket.ticket_id}.json"
            dest.write_text(data, encoding="utf-8")

    # ── Read ───────────────────────────────────────────────────────────────────

    def get(self, ticket_id: str) -> Optional[AzulTicket]:
        """
        Load a ticket by ID.  Checks active/ first, then completed/.
        Returns None if not found.
        """
        for directory in (self._active, self._completed):
            path = directory / f"{ticket_id}.json"
            if path.exists():
                return AzulTicket.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return None

    def exists(self, ticket_id: str) -> bool:
        """Return True if the ticket exists in either directory."""
        return (
            (self._active    / f"{ticket_id}.json").exists()
            or (self._completed / f"{ticket_id}.json").exists()
        )

    # ── List ───────────────────────────────────────────────────────────────────

    def list(
        self,
        status:      Optional[str | TicketStatus] = None,
        ticket_type: Optional[str | TicketType]   = None,
    ) -> List[AzulTicket]:
        """
        Return all tickets, with optional filters.

        Args:
            status:      Filter to a specific TicketStatus value.
            ticket_type: Filter to a specific TicketType value.

        Results are sorted by created_at ascending (oldest first).
        """
        status_val      = TicketStatus(status) if isinstance(status, str) else status
        ticket_type_val = TicketType(ticket_type) if isinstance(ticket_type, str) else ticket_type

        tickets: List[AzulTicket] = []
        for directory in (self._active, self._completed):
            for path in directory.glob("*.json"):
                try:
                    t = AzulTicket.from_dict(json.loads(path.read_text(encoding="utf-8")))
                    if status_val is not None and t.status != status_val:
                        continue
                    if ticket_type_val is not None and t.ticket_type != ticket_type_val:
                        continue
                    tickets.append(t)
                except Exception:
                    continue  # Skip corrupt files

        tickets.sort(key=lambda t: t.created_at)
        return tickets

    def list_active(self) -> List[AzulTicket]:
        """Return all non-terminal tickets."""
        return [t for t in self.list() if t.status not in TERMINAL_STATUSES]

    def list_completed(self) -> List[AzulTicket]:
        """Return all terminal tickets."""
        return [t for t in self.list() if t.status in TERMINAL_STATUSES]

    # ── Delete (test/admin use only) ──────────────────────────────────────────

    def delete(self, ticket_id: str) -> bool:
        """Remove a ticket from disk.  Returns True if found and deleted."""
        found = False
        for directory in (self._active, self._completed):
            path = directory / f"{ticket_id}.json"
            if path.exists():
                path.unlink()
                found = True
        return found
