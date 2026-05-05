"""
domain_config.py — Per-domain oracle/scoring/mode configuration  (P1-3)
========================================================================
Azul's equivalent of SAM's FORGEWORKS_ORACLE_PATHS / FORGEWORKS_SCORING_PATHS
tables.  Follows the same pattern as `_build_planner_spec()` in
``forge_planner_agent.py``.

Domain configuration controls:
    - oracle_path:    Path to the oracle YAML for this domain's scoring
    - scoring_path:   Path to the scoring rubric for this domain
    - default_mode:   The default ForgeWorks run mode for this domain
    - requires_blast_radius: Whether ForgeScaffold analysis is needed

The paths here are relative to the Azul data directory.  They point to
ForgeWorks domain configuration files that must already exist in the
ForgeWorks installation.  Overridable per-ticket via planner_spec fields
if the caller provides them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

# ── Resolve ForgeWorks root (for oracle and scoring paths) ────────────────────
# ForgeWorks ships its own oracle/rubric files under forgeworks/oracles/.
# The path used here mirrors the SAM pattern from _build_planner_spec().
_FORGEWORKS_ROOT = Path(
    os.environ.get("FORGEWORKS_ROOT")
    or os.environ.get("FORGE_SCAFFOLD_ROOT")
    or str(Path(__file__).resolve().parents[2] / "ForgeScaffold")
)

# ── Domain configuration table ───────────────────────────────────────────────

DOMAIN_CONFIG: Dict[str, Dict[str, Any]] = {
    "ci_change_control": {
        "oracle_path":          str(_FORGEWORKS_ROOT / "forgeworks" / "oracles" / "ci_change_control" / "oracle.yaml"),
        "scoring_path":         str(_FORGEWORKS_ROOT / "forgeworks" / "oracles" / "ci_change_control" / "scoring.yaml"),
        "default_mode":         "shadow",
        "requires_blast_radius": True,
    },
    "it_ops_runbook": {
        "oracle_path":          str(_FORGEWORKS_ROOT / "forgeworks" / "oracles" / "it_ops_runbook" / "oracle.yaml"),
        "scoring_path":         str(_FORGEWORKS_ROOT / "forgeworks" / "oracles" / "it_ops_runbook" / "scoring.yaml"),
        "default_mode":         "shadow",
        "requires_blast_radius": False,
    },
}

# Domains that require codebase blast-radius analysis via ForgeScaffold
CODEBASE_DOMAINS: frozenset[str] = frozenset(
    d for d, cfg in DOMAIN_CONFIG.items() if cfg.get("requires_blast_radius")
)


# ── Accessors ─────────────────────────────────────────────────────────────────

def get_domain_config(domain: str) -> Dict[str, Any]:
    """
    Return configuration for the given domain.
    Falls back to ci_change_control defaults for unknown domains.
    """
    return DOMAIN_CONFIG.get(domain, DOMAIN_CONFIG["ci_change_control"])


def resolve_oracle_path(domain: str) -> str:
    """Return the oracle path for the given domain."""
    return get_domain_config(domain)["oracle_path"]


def resolve_scoring_path(domain: str) -> str:
    """Return the scoring path for the given domain."""
    return get_domain_config(domain)["scoring_path"]


def resolve_default_mode(domain: str) -> str:
    """Return the default mode for the given domain."""
    return get_domain_config(domain).get("default_mode", "shadow")


def requires_blast_radius(domain: str) -> bool:
    """Return True if this domain requires ForgeScaffold blast-radius analysis."""
    return bool(get_domain_config(domain).get("requires_blast_radius", False))
