"""
integrations/forge_atlas.py — ForgeAtlas action discovery (P2-3)
================================================================
Calls ForgeAtlas' ``run.py`` via importlib Pattern 1 to discover available
actions for the verification task.

ForgeAtlas is OPTIONAL in Phase 1 (called if enabled, skipped gracefully if
ForgeAtlas is unavailable or AZUL_FORGE_ATLAS_ENABLED=false).

Returns _ok({"actions": list}) or _error.
Never raises.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Feature flag ─────────────────────────────────────────────────────────────

AZUL_FORGE_ATLAS_ENABLED: bool = (
    os.environ.get("AZUL_FORGE_ATLAS_ENABLED", "false").lower() == "true"
)

# ── Path resolution ─────────────────────────────────────────────────────────

_FORGE_ATLAS_RUN_PATH = os.environ.get(
    "FORGE_ATLAS_RUN_PATH",
    str(
        Path(__file__).resolve().parents[3]
        / "ForgeAtlas" / "action_discovery_service" / "run.py"
    ),
)

_atlas_mod = None


def _get_atlas():
    """Load ForgeAtlas run module once (importlib Pattern 1)."""
    global _atlas_mod
    if _atlas_mod is not None:
        return _atlas_mod

    path = Path(_FORGE_ATLAS_RUN_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"ForgeAtlas run.py not found at {path}. "
            "Set FORGE_ATLAS_RUN_PATH env var."
        )

    spec = importlib.util.spec_from_file_location("forge_atlas_run", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _atlas_mod = mod
    return mod


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "payload": payload}


def _error(code: str, message: str, details: Optional[Dict] = None) -> Dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message, "details": details or {}}}


# ── Public API ───────────────────────────────────────────────────────────────

def discover_actions(
    task_context: str,
    capability_set: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Discover available actions for the verification task context.

    Returns _ok({"actions": list}) or _error.
    If AZUL_FORGE_ATLAS_ENABLED is False, returns _ok({"actions": [], "skipped": True}).
    Never raises.
    """
    if not AZUL_FORGE_ATLAS_ENABLED:
        return _ok({"actions": [], "skipped": True, "reason": "AZUL_FORGE_ATLAS_ENABLED=false"})

    try:
        atlas = _get_atlas()

        # Default capability set for Azul verification tasks
        cap_set = capability_set or {
            "id":                    "azul-verification",
            "allowed_action_families": [],
            "allowed_resource_types":  [],
            "restricted_resource_types": [],
            "restricted_resource_tags":  [],
            "lease_permissions":         [],
            "exclusions":                [],
        }

        result = atlas.run(
            query={"task_context": task_context, "max_results": 10},
            capability_set=cap_set,
        )

        if result.get("status") == "ok":
            actions = result["payload"].get("available_actions", [])
            return _ok({"actions": actions, "skipped": False})
        else:
            # Non-fatal — ForgeAtlas unavailability doesn't block verification
            logger.warning(f"[ForgeAtlas] discover_actions returned error: {result}")
            return _ok({"actions": [], "skipped": True, "reason": "forge_atlas_error"})

    except FileNotFoundError:
        logger.warning("[ForgeAtlas] run.py not found — skipping action discovery")
        return _ok({"actions": [], "skipped": True, "reason": "forge_atlas_not_found"})
    except Exception as exc:
        logger.warning(f"[ForgeAtlas] discover_actions error (non-fatal): {exc}")
        return _ok({"actions": [], "skipped": True, "reason": str(exc)})


def reset_module() -> None:
    """Reset the module-level singleton (for testing)."""
    global _atlas_mod
    _atlas_mod = None
