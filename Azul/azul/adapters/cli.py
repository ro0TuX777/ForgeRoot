"""
adapters/cli.py — Command-line interface adapter
=================================================
Runs Azul verification directly from the command line.

Usage:
    python -m azul.adapters.cli \\
        --type ci_gate \\
        --domain ci_change_control \\
        --summary "Fix null check in auth.py" \\
        --files src/auth.py src/session.py \\
        --payload '{"commit_sha": "abc123"}' \\
        [--priority high] [--mode shadow]

Exit codes:
    0  → verdict = pass (COMPLETED or WARNED)
    1  → verdict = reject (REJECTED)
    2  → operational failure (FAILED or validation error)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from ..ticket import create_ticket, TicketType, TicketPriority
from ..ticket_store import AzulTicketStore
from ..xp_ledger import XPLedger
from ..verification_engine import verify
from ..config import ensure_data_dirs
from ..loop.gold_labels import GoldLabelStore
from ..loop.orchestrator import LoopOrchestrator

logger = logging.getLogger(__name__)


# ── Argument parser ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="azul",
        description="Azul — Agentic Change Verification System",
        epilog=(
            "Recursive loop commands: azul loop status | report | agreement-rate | drift"
        ),
    )
    p.add_argument(
        "--type", dest="ticket_type",
        choices=[t.value for t in TicketType],
        default=TicketType.CI_GATE.value,
        help="Ticket type (default: ci_gate)",
    )
    p.add_argument(
        "--domain", default="ci_change_control",
        help="Routing domain (default: ci_change_control)",
    )
    p.add_argument(
        "--summary", required=True,
        help="One-line description of the change",
    )
    p.add_argument(
        "--files", nargs="*", default=[],
        metavar="FILE",
        help="Files changed by this commit",
    )
    p.add_argument(
        "--payload", default="{}",
        help="JSON string of additional change payload",
    )
    p.add_argument(
        "--priority",
        choices=[p.value for p in TicketPriority],
        default=TicketPriority.NORMAL.value,
    )
    p.add_argument(
        "--mode", choices=["shadow", "supervised", "ramped"],
        default="shadow",
    )
    p.add_argument(
        "--no-persist", action="store_true",
        help="Skip persisting ticket to disk (dry-run)",
    )
    p.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Emit result as JSON (useful for script consumers)",
    )
    return p


def build_loop_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="azul loop",
        description="Azul recursive loop commands",
    )
    sub = p.add_subparsers(dest="loop_command", required=True)
    sub.add_parser("status", help="Loop status and current agreement snapshot")
    sub.add_parser("report", help="Latest improvement report")
    sub.add_parser("agreement-rate", help="Agreement rates by artifact type")
    sub.add_parser("drift", help="Latest drift report")
    return p


def _run_loop(args: Optional[List[str]] = None) -> int:
    parser = build_loop_parser()
    ns = parser.parse_args(args)
    orchestrator = LoopOrchestrator()

    if ns.loop_command == "status":
        print(json.dumps(orchestrator.status_snapshot(), indent=2))
        return 0

    if ns.loop_command == "report":
        payload = orchestrator.latest_report()
        if not payload:
            print(json.dumps({"status": "empty", "message": "no loop report found"}, indent=2))
        else:
            print(json.dumps(payload, indent=2))
        return 0

    if ns.loop_command == "agreement-rate":
        labels = GoldLabelStore()
        response = {
            "action_contract_stub": {
                "rate": labels.compute_agreement_rate("action_contract_stub", window=20),
                "trend": labels.compute_agreement_trend("action_contract_stub", window=20),
            },
            "verdict_override": {
                "rate": labels.compute_agreement_rate("verdict_override", window=20),
                "trend": labels.compute_agreement_trend("verdict_override", window=20),
            },
            "gate_policy_recommendation": {
                "rate": labels.compute_agreement_rate("gate_policy_recommendation", window=20),
                "trend": labels.compute_agreement_trend("gate_policy_recommendation", window=20),
            },
        }
        print(json.dumps(response, indent=2))
        return 0

    if ns.loop_command == "drift":
        payload = orchestrator.latest_drift_report()
        if not payload:
            print(json.dumps({"status": "empty", "message": "no drift report found"}, indent=2))
        else:
            print(json.dumps(payload, indent=2))
        return 0

    return 2


# ── Main entry point ────────────────────────────────────────────────────────────

def run(args: Optional[List[str]] = None) -> int:
    """
    Parse CLI args, run verification, print result, return exit code.

    Exit codes: 0=pass, 1=reject, 2=error/failure.
    """
    argv = list(args) if args is not None else sys.argv[1:]
    if argv and argv[0] == "loop":
        return _run_loop(argv[1:])

    parser = build_parser()
    ns = parser.parse_args(argv)

    # Parse payload JSON
    try:
        payload: Dict[str, Any] = json.loads(ns.payload)
    except json.JSONDecodeError as exc:
        print(f"ERROR: --payload is not valid JSON: {exc}", file=sys.stderr)
        return 2

    # Set up persistence
    store: Optional[AzulTicketStore] = None
    ledger: Optional[XPLedger] = None
    if not ns.no_persist:
        ensure_data_dirs()
        store  = AzulTicketStore()
        ledger = XPLedger()

    ticket = create_ticket(
        ticket_type    = ns.ticket_type,
        domain         = ns.domain,
        mode           = ns.mode,
        change_summary = ns.summary,
        change_payload = payload,
        target_files   = ns.files,
        priority       = ns.priority,
        source         = {"adapter": "cli"},
    )

    result = verify(ticket, store=store, ledger=ledger)

    if ns.json_output:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result, ticket)

    verdict  = result.get("verdict")
    status   = result.get("status")

    if status == "error":
        return 2
    if verdict == "pass":
        return 0
    if verdict == "reject":
        return 1
    return 2


def _print_human(result: Dict[str, Any], ticket) -> None:
    verdict  = result.get("verdict") or "error"
    severity = result.get("severity", "")
    tid      = result.get("ticket_id", "")
    xp       = result.get("xp_awarded", 0)
    alerts   = result.get("alerts", [])

    icon = {"pass": "✅", "reject": "❌", "error": "⚠️"}.get(verdict, "⚠️")
    print(f"\n{icon}  Azul Verdict: {verdict.upper()}  [{severity}]")
    print(f"   Ticket: {tid}")
    print(f"   XP:     {xp}")
    if alerts:
        print("   Alerts:")
        for a in alerts:
            print(f"     • {a}")
    print()


if __name__ == "__main__":
    sys.exit(run())
