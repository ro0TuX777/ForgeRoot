"""
adapters/distillation.py — Distillation training pair verification adapter
==========================================================================
Submits a candidate input/output pair for behavioral verification before
it enters the training dataset.

A distillation pair must pass ForgeWorks evaluation before it is stored
as a verified training pair.  Rejected pairs are not emitted.

Payload schema:
{
    "input":          str,          # prompt / question
    "output":         str,          # expected completion / answer
    "domain":         str,          # target domain for scoring
    "quality_score":  float | None, # pre-filter quality signal (optional)
    "source_model":   str | None,   # originating model name
    "metadata":       dict | None,
}

Returns verdict and, if passed, the emitted pair_id.
Never raises.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..ticket import create_ticket, TicketType, TicketPriority
from ..ticket_store import AzulTicketStore
from ..xp_ledger import XPLedger
from ..training_pairs import TrainingPairStore
from ..verification_engine import verify

logger = logging.getLogger(__name__)

# ── Validation ─────────────────────────────────────────────────────────────────

REQUIRED = {"input", "output", "domain"}

# Minimum quality score to even attempt verification (pre-filter gate)
DEFAULT_MIN_QUALITY: float = 0.0


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": data, "error": None}


def _err(msg: str) -> Dict[str, Any]:
    return {"status": "error", "data": None, "error": msg}


# ── Public API ─────────────────────────────────────────────────────────────────

def submit_pair(
    payload:     Dict[str, Any],
    store:       Optional[AzulTicketStore]   = None,
    ledger:      Optional[XPLedger]           = None,
    pair_store:  Optional[TrainingPairStore]  = None,
    min_quality: float                        = DEFAULT_MIN_QUALITY,
) -> Dict[str, Any]:
    """
    Submit an input/output candidate pair for Azul verification.

    Pre-filter: if quality_score < min_quality, reject immediately without
    running the verification pipeline (save compute).

    Args:
        payload:     Dict with input, output, domain, and optional metadata.
        store:       Ticket store for persistence.
        ledger:      XP ledger.
        pair_store:  TrainingPairStore for querying the emitted pair.
        min_quality: Pre-filter threshold on payload["quality_score"].

    Returns _ok({"verdict", "pair_id", "ticket_id", "xp_awarded"}).
    Never raises.
    """
    missing = REQUIRED - set(payload.keys())
    if missing:
        return _err(f"Missing required fields: {sorted(missing)}")

    # Pre-filter gate — cheap rejection before spinning up the pipeline
    quality = float(payload.get("quality_score") or 0.0)
    if quality < min_quality:
        logger.info(
            f"[distillation] Pre-filter reject: quality={quality:.2f} < min={min_quality:.2f}"
        )
        return _ok({
            "verdict":   "reject",
            "reason":    f"quality_score {quality:.2f} below pre-filter threshold {min_quality:.2f}",
            "pair_id":   None,
            "ticket_id": None,
            "xp_awarded": 0,
        })

    source_model = payload.get("source_model", "unknown")
    domain       = payload["domain"]

    summary = (
        f"Distillation pair from {source_model}: "
        f"\"{str(payload['input'])[:60]}{'...' if len(str(payload['input'])) > 60 else ''}\""
    )

    try:
        ticket = create_ticket(
            ticket_type    = TicketType.DISTILLATION_PAIR,
            domain         = domain,
            change_summary = summary,
            change_payload = {
                "input":         payload["input"],
                "output":        payload["output"],
                "quality_score": quality,
                "source_model":  source_model,
            },
            priority = TicketPriority.NORMAL,
            mode     = "shadow",
            metadata = payload.get("metadata") or {},
            source   = {
                "adapter":      "distillation",
                "source_model": source_model,
                "quality_score": quality,
            },
        )
    except (ValueError, KeyError) as exc:
        return _err(f"Ticket creation error: {exc}")

    logger.info(
        f"[distillation] Submitting pair ticket={ticket.ticket_id} "
        f"domain={domain} quality={quality:.2f}"
    )

    result = verify(ticket, store=store, ledger=ledger)

    # Resolve pair_id (emitted by training_pairs.emit_training_pair inside verify)
    pair_id: Optional[str] = None
    if result.get("verdict") == "pass":
        pair_id = f"tp-{ticket.ticket_id}"

    return _ok({
        "verdict":    result.get("verdict"),
        "severity":   result.get("severity"),
        "ticket_id":  result.get("ticket_id"),
        "pair_id":    pair_id,
        "alerts":     result.get("alerts", []),
        "xp_awarded": result.get("xp_awarded", 0),
    })
