"""
xp_ledger.py — XP calculation and append-only JSONL ledger  (P1-1)
====================================================================
XP is awarded when a ticket reaches COMPLETED or WARNED status.
No XP is awarded for REJECTED or FAILED tickets.

The ledger is a JSONL file (one JSON object per line) — never mutated,
only appended to.  This design makes it trivially auditable.

Formula (Core Spec §6.1):
    base_xp        = XP_BY_TYPE[ticket_type]
    score_bonus    = int(total_score / 10)
    risk_multiplier = RISK_MULTIPLIERS[priority]
    xp_awarded     = int(base_xp * risk_multiplier + score_bonus)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ticket import AzulTicket, TicketStatus, TicketType, TicketPriority
from .config import XP_LEDGER_PATH


# ── XP tables ─────────────────────────────────────────────────────────────────

XP_BY_TYPE: Dict[TicketType, int] = {
    TicketType.CI_GATE:           10,
    TicketType.REFACTOR:          15,
    TicketType.SECURITY_PATCH:    20,
    TicketType.POLICY_COMPLIANCE: 10,
    TicketType.DISTILLATION_PAIR:  5,
}

RISK_MULTIPLIERS: Dict[TicketPriority, float] = {
    TicketPriority.LOW:      1.0,
    TicketPriority.NORMAL:   1.0,
    TicketPriority.HIGH:     1.5,
    TicketPriority.CRITICAL: 2.0,
}

# Statuses that qualify for XP
XP_ELIGIBLE_STATUSES = frozenset({TicketStatus.COMPLETED, TicketStatus.WARNED})


# ── Calculation ───────────────────────────────────────────────────────────────

def calculate_xp(ticket: AzulTicket) -> int:
    """
    Calculate XP for a completed or warned ticket.
    Returns 0 for rejected / failed tickets.
    """
    if ticket.status not in XP_ELIGIBLE_STATUSES:
        return 0
    if ticket.verdict != "pass":
        return 0

    base_xp = XP_BY_TYPE.get(ticket.ticket_type, 10)
    risk    = RISK_MULTIPLIERS.get(ticket.priority, 1.0)

    # Extract score from review_bundle if available
    score = 0.0
    if ticket.review_bundle:
        score = float(
            ticket.review_bundle.get("metrics", {}).get("total_score", 0.0)
        )

    score_bonus = int(score / 10)
    return int(base_xp * risk + score_bonus)


# ── Ledger ────────────────────────────────────────────────────────────────────

class XPLedger:
    """
    Append-only JSONL ledger for XP awards.

    Args:
        path: Path to the JSONL file.  Created on first write if it does not exist.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path or XP_LEDGER_PATH)

    # ── Write ──────────────────────────────────────────────────────────────────

    def award_xp(self, ticket: AzulTicket) -> int:
        """
        Calculate XP for *ticket*, persist the award record, and return the
        amount awarded.  Returns 0 (and writes nothing) for ineligible tickets.
        """
        xp = calculate_xp(ticket)
        if xp == 0:
            return 0

        record: Dict[str, Any] = {
            "ticket_id":   ticket.ticket_id,
            "xp":          xp,
            "ticket_type": ticket.ticket_type.value,
            "domain":      ticket.domain,
            "score":       (
                ticket.review_bundle.get("metrics", {}).get("total_score", 0.0)
                if ticket.review_bundle else 0.0
            ),
            "priority":    ticket.priority.value,
            "status":      ticket.status.value,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return xp

    # ── Read ───────────────────────────────────────────────────────────────────

    def records(self) -> List[Dict[str, Any]]:
        """Return all records as a list (in order, oldest first)."""
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        result = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return result

    def get_summary(
        self,
        domain:      Optional[str] = None,
        ticket_type: Optional[str] = None,
        since:       Optional[str] = None,   # ISO-8601 timestamp string
    ) -> Dict[str, Any]:
        """
        Return aggregated XP totals.

        Args:
            domain:      Filter to a specific domain string.
            ticket_type: Filter to a specific ticket type string.
            since:       Only include records at or after this ISO timestamp.

        Returns a dict with:
            - total_xp:   int
            - by_domain:  {domain: xp_total}
            - by_type:    {ticket_type: xp_total}
            - record_count: int
        """
        recs = self.records()

        # Apply filters
        if since:
            recs = [r for r in recs if r.get("timestamp", "") >= since]
        if domain:
            recs = [r for r in recs if r.get("domain") == domain]
        if ticket_type:
            recs = [r for r in recs if r.get("ticket_type") == ticket_type]

        by_domain: Dict[str, int] = defaultdict(int)
        by_type:   Dict[str, int] = defaultdict(int)
        total = 0

        for r in recs:
            xp = r.get("xp", 0)
            total += xp
            by_domain[r.get("domain", "unknown")] += xp
            by_type[r.get("ticket_type", "unknown")] += xp

        return {
            "total_xp":     total,
            "by_domain":    dict(by_domain),
            "by_type":      dict(by_type),
            "record_count": len(recs),
        }
