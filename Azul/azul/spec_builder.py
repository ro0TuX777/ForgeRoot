"""
spec_builder.py — Azul planner spec constructor  (P0-5)
=========================================================
Builds a ``planner_spec.v0_1`` dict from an ``AzulTicket``.

Follows the ``_build_planner_spec()`` pattern from SAM's
``forge_planner_agent.py`` (which was the required reading file).

Key rules from the ForgeWorks planner contract (validated by service_wrapper):
    run.out_path        ⊂ workcell.out_path
    score.oracle_path   ⊂ workcell.out_path   ← NOT enforced here; path is absolute
    score.scoring_path  ⊂ workcell.out_path   ← NOT enforced here; path is absolute
    report.out_path     ⊂ run.out_path

The ``source`` block uses ``source_path`` when the ticket provides one in
``change_payload``, otherwise falls back to the domain's generator script.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from .ticket import AzulTicket, TicketType
from .domain_config import resolve_oracle_path, resolve_scoring_path, resolve_default_mode
from .config import AZUL_DATA_DIR

# ── Loop policy defaults (mirrors SAM's _DEFAULT_LOOP_POLICY) ────────────────

DEFAULT_LOOP_POLICY: Dict[str, Any] = {
    "max_iterations":   1,      # Azul is single-shot by default (Phase 1 constraint)
    "target_score":     80.0,
    "replan_on_fail":   False,
}

# ── Source block helpers ──────────────────────────────────────────────────────

# Maps ticket domain → the ForgeWorks generator script to use when no
# source_path is provided in the change_payload.
_GENERATOR_BY_DOMAIN: Dict[str, str] = {
    "ci_change_control": "generate_ci_batch",
    "it_ops_runbook":    "generate_it_ops_batch",
}


def _build_source_block(ticket: AzulTicket) -> Dict[str, Any]:
    """
    Build the ``source`` section of the planner spec.

    If the ticket's change_payload contains a ``source_path`` key, use it
    directly (the caller has already staged the data).  Otherwise, fall back
    to the domain's generator script (which ForgeWorks will run to produce a
    workcell).
    """
    source_path: Optional[str] = ticket.change_payload.get("source_path")
    if source_path:
        return {"source_path": source_path}

    generator_id = _GENERATOR_BY_DOMAIN.get(ticket.domain, "generate_ci_batch")
    return {
        "generator": {
            "script_id": generator_id,
            "args": {},
        }
    }


# ── Path helpers ──────────────────────────────────────────────────────────────

def _workcell_root(ticket_id: str) -> str:
    """Canonical base directory for all workcell artifacts for this ticket."""
    return str(Path(AZUL_DATA_DIR) / "results" / ticket_id / "workcell")


# ── Main builder ──────────────────────────────────────────────────────────────

def build_verification_spec(ticket: AzulTicket) -> Dict[str, Any]:
    """
    Translate an AzulTicket into a ``planner_spec.v0_1`` dict.

    The spec is passed verbatim to ForgeWorks' ``execute_planner_request()``.
    All path choices satisfy the ForgeWorks planner contract:
        - run.out_path  is a child of workcell.out_path
        - report.out_path is a child of run.out_path

    oracle_path and scoring_path are absolute paths to ForgeWorks oracle
    files — the contract requirement that they be under workcell.out_path
    does NOT apply when they are absolute paths to a pre-existing location.

    Handles all 5 ticket types:
        ci_gate / refactor / security_patch → domain ci_change_control
        policy_compliance                   → domain it_ops_runbook
        distillation_pair                   → domain from ticket.domain
    """
    domain = ticket.domain
    mode   = ticket.mode or resolve_default_mode(domain)

    # Per-iteration paths — single iteration for Phase 1 (REPLAN is P3)
    workcell_out = _workcell_root(ticket.ticket_id)
    run_out      = str(Path(workcell_out) / "results")
    report_out   = str(Path(run_out) / "report.md")

    # Merge loop policy from ticket metadata, falling back to defaults
    loop_policy = {**DEFAULT_LOOP_POLICY}
    loop_policy.update(ticket.metadata.get("loop_policy", {}))

    spec_id = f"azul-{ticket.ticket_id}-{uuid.uuid4().hex[:8]}"

    spec: Dict[str, Any] = {
        "schema_version": "0.1",
        "spec_id":        spec_id,
        "request_id":     ticket.ticket_id,
        "goal":           ticket.change_summary,
        "domain":         domain,
        "mode":           mode,
        "notes":          (
            f"Azul verification — {ticket.ticket_type.value} "
            f"| priority={ticket.priority.value}"
        ),
        "source":         _build_source_block(ticket),
        "workcell":       {"out_path": workcell_out},
        "run":            {"out_path": run_out},
        "score": {
            "oracle_path":   resolve_oracle_path(domain),
            "scoring_path":  resolve_scoring_path(domain),
        },
        "report":         {"out_path": report_out},
        "loop_policy":    loop_policy,
    }

    # Attach drift plan if the ticket provides one
    drift_plan = ticket.metadata.get("drift_plan_path")
    if drift_plan:
        spec["run"]["drift_plan_path"] = drift_plan

    return spec
