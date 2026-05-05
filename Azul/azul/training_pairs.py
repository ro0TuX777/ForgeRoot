"""
training_pairs.py — Distillation training pair emission and storage  (P1-2)
===========================================================================
Emits verified training pairs only for ``distillation_pair`` tickets that have
reached COMPLETED or WARNED (verdict = "pass").

Pairs are stored as individual JSON files:
    azul_data/training_pairs/<pair_id>.json

Provenance: every pair carries the ReviewBundle ID so the training dataset can
be traced back to the verification run that approved it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ticket import AzulTicket, TicketType, TicketStatus, TERMINAL_STATUSES
from .config import TRAINING_PAIRS_DIR


# ── Emission ──────────────────────────────────────────────────────────────────

def emit_training_pair(ticket: AzulTicket) -> Optional[Dict[str, Any]]:
    """
    Build and persist a training pair from a verified distillation ticket.

    Returns the pair dict on success, or ``None`` if the ticket is not eligible
    (wrong type, wrong verdict, or missing payload fields).
    """
    # Only distillation_pair tickets produce training pairs
    if ticket.ticket_type != TicketType.DISTILLATION_PAIR:
        return None

    # Only passing tickets earn a pair
    if ticket.verdict != "pass":
        return None

    # Require the input/output fields in change_payload
    if "input" not in ticket.change_payload or "output" not in ticket.change_payload:
        return None

    score = 0.0
    bundle_id = None
    if ticket.review_bundle:
        score = float(
            ticket.review_bundle.get("metrics", {}).get("total_score", 0.0)
        )
        bundle_id = ticket.review_bundle.get("bundle_id")

    pair_id = f"tp-{ticket.ticket_id}"
    pair: Dict[str, Any] = {
        "pair_id":                pair_id,
        "input":                  ticket.change_payload["input"],
        "output":                 ticket.change_payload["output"],
        "verification_score":     score,
        "verification_bundle_id": bundle_id,
        "xp_awarded":             ticket.xp_awarded,
        "domain":                 ticket.domain,
        "verified_at":            ticket.completed_at or datetime.now(timezone.utc).isoformat(),
        "ticket_id":              ticket.ticket_id,
    }

    # Persist
    out_dir = Path(TRAINING_PAIRS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{pair_id}.json").write_text(
        json.dumps(pair, indent=2), encoding="utf-8"
    )

    return pair


# ── Query ─────────────────────────────────────────────────────────────────────

class TrainingPairStore:
    """
    Query interface for persisted training pairs.

    Args:
        directory: Directory containing .json pair files.
    """

    def __init__(self, directory: Optional[Path] = None) -> None:
        self._dir = Path(directory or TRAINING_PAIRS_DIR)

    def get_pairs(
        self,
        domain:    Optional[str]   = None,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve verified training pairs.

        Args:
            domain:    Filter to a specific domain string.
            min_score: Exclude pairs whose verification_score is below this value.

        Results are sorted by verification_score descending (highest quality first).
        """
        if not self._dir.exists():
            return []

        pairs: List[Dict[str, Any]] = []
        for path in self._dir.glob("*.json"):
            try:
                pair = json.loads(path.read_text(encoding="utf-8"))
                if domain and pair.get("domain") != domain:
                    continue
                if min_score is not None:
                    if float(pair.get("verification_score", 0.0)) < min_score:
                        continue
                pairs.append(pair)
            except Exception:
                continue

        pairs.sort(key=lambda p: float(p.get("verification_score", 0.0)), reverse=True)
        return pairs

    def count(self) -> int:
        """Return total number of stored pairs."""
        if not self._dir.exists():
            return 0
        return sum(1 for _ in self._dir.glob("*.json"))
