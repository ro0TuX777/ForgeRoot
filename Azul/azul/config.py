"""
config.py — Azul configuration
================================
Reads environment variables with typed defaults.
All Azul modules import from here; nothing reads os.environ directly.
"""

from __future__ import annotations

import os
from pathlib import Path


def _as_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


# ── Storage ───────────────────────────────────────────────────────────────────

_DEFAULT_FORGE_ROOT = Path(os.environ.get("FORGE_ROOT", Path(__file__).resolve().parents[2]))
AZUL_DATA_DIR: str = os.environ.get("AZUL_DATA_DIR", str(_DEFAULT_FORGE_ROOT / "azul_data"))

# Derived paths (resolved at import time so callers always get absolute paths
# when the process cwd is consistent).
_DATA = Path(AZUL_DATA_DIR)
TICKETS_ACTIVE_DIR:    Path = _DATA / "tickets" / "active"
TICKETS_COMPLETED_DIR: Path = _DATA / "tickets" / "completed"
VERDICTS_DIR:          Path = _DATA / "verdicts"
TRAINING_PAIRS_DIR:    Path = _DATA / "training_pairs"
XP_LEDGER_PATH:        Path = _DATA / "xp_ledger.jsonl"
CONFIG_DIR:            Path = _DATA / "config"
GATE_POLICIES_DIR:     Path = CONFIG_DIR / "gate_policies"
DOMAIN_CONFIG_PATH:    Path = CONFIG_DIR / "domain_config.yaml"

# ── Runtime ───────────────────────────────────────────────────────────────────

AZUL_DEFAULT_MODE:   str = os.environ.get("AZUL_DEFAULT_MODE",   "shadow")
AZUL_DEFAULT_DOMAIN: str = os.environ.get("AZUL_DEFAULT_DOMAIN", "ci_change_control")
AZUL_QUEUE_WORKERS:  int = int(os.environ.get("AZUL_QUEUE_WORKERS", "3"))

# Timeouts (milliseconds)
AZUL_FORGEWORKS_TIMEOUT_MS: int = int(
    os.environ.get("AZUL_FORGEWORKS_TIMEOUT_MS", "300000")
)

# Feature flags
AZUL_FORGE_HARBOR_ENABLED:      bool = _as_bool("AZUL_FORGE_HARBOR_ENABLED", "true")
AZUL_FORGE_SCAFFOLD_ENABLED:    bool = _as_bool("AZUL_FORGE_SCAFFOLD_ENABLED", "true")
AZUL_TRAINING_PAIR_EMISSION:    bool = _as_bool("AZUL_TRAINING_PAIR_EMISSION", "true")
AZUL_GOVERNANCE_GUARDS_ENABLED: bool = _as_bool("AZUL_GOVERNANCE_GUARDS_ENABLED", "true")
AZUL_FORGEWORKS_DEGRADED_FALLBACK: bool = _as_bool(
    "AZUL_FORGEWORKS_DEGRADED_FALLBACK",
    "false",
)
AZUL_NO_DESTRUCTIVE_REMEDIATION_GUARD_ENABLED: bool = _as_bool(
    "AZUL_NO_DESTRUCTIVE_REMEDIATION_GUARD_ENABLED",
    "true",
)
AZUL_CI_STATUS_POST_ENABLED: bool = _as_bool("AZUL_CI_STATUS_POST_ENABLED", "true")
AZUL_CI_STATUS_FAIL_CLOSED: bool = _as_bool("AZUL_CI_STATUS_FAIL_CLOSED", "true")

# Logging
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")


# ── Domains that trigger ForgeScaffold blast-radius analysis ──────────────────

CODEBASE_DOMAINS: frozenset[str] = frozenset({
    "ci_change_control",
})


def ensure_data_dirs() -> None:
    """Create all persistent data directories if they do not already exist."""
    for d in (
        TICKETS_ACTIVE_DIR,
        TICKETS_COMPLETED_DIR,
        VERDICTS_DIR,
        TRAINING_PAIRS_DIR,
        GATE_POLICIES_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
