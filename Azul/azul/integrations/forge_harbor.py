"""
integrations/forge_harbor.py — ForgeHarbor environment management
==================================================================
Wraps ForgeHarbor daemon calls for PROVISIONING and environment release.

ForgeHarbor is a long-running daemon (ForgeHarborDaemon) with typed
caller-facing functions:  ``request_environment()`` / ``release_environment()``.

In production: an importlib call loads ForgeHarbor's daemon.py and uses the
singleton daemon instance.  In tests: swapped for the mock via the
``FORGE_HARBOR_DAEMON`` env var or direct injection.

All public functions return _ok/_error envelopes (callers check ["status"]).
Never raises — errors are caught and returned as structured dicts.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Path resolution ─────────────────────────────────────────────────────────

_FORGE_HARBOR_DAEMON_PATH = os.environ.get(
    "FORGE_HARBOR_DAEMON_PATH",
    str(Path(__file__).resolve().parents[3] / "ForgeHarbor" / "daemon.py"),
)

# Module-level daemon singleton (loaded once, reused across calls)
_daemon = None


def _get_daemon():
    """Load and return the ForgeHarbor daemon singleton (importlib Pattern 1)."""
    global _daemon
    if _daemon is not None:
        return _daemon

    daemon_path = Path(_FORGE_HARBOR_DAEMON_PATH)
    if not daemon_path.exists():
        raise FileNotFoundError(
            f"ForgeHarbor daemon not found at {daemon_path}. "
            "Set FORGE_HARBOR_DAEMON_PATH env var."
        )

    spec = importlib.util.spec_from_file_location("forge_harbor_daemon", daemon_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _daemon = mod.ForgeHarborDaemon(use_mock_provider=True)
    _daemon.start()
    return _daemon


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "payload": payload}


def _error(code: str, message: str, details: Optional[Dict] = None) -> Dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message, "details": details or {}}}


# ── Public API ───────────────────────────────────────────────────────────────

def request_environment(ticket_id: str) -> Dict[str, Any]:
    """
    Request a warm environment for the given ticket.

    Returns _ok({"environment_id": str}) on success.
    Returns _error on failure (ENVIRONMENT_UNAVAILABLE, etc.).
    Never raises.
    """
    try:
        daemon = _get_daemon()
        result = daemon.request_environment(session_id=ticket_id)
        return result
    except FileNotFoundError as exc:
        return _error("FORGE_HARBOR_UNAVAILABLE", str(exc))
    except Exception as exc:
        logger.error(f"[ForgeHarbor] request_environment error: {exc}")
        return _error("FORGE_HARBOR_ERROR", str(exc))


def release_environment(environment_id: str) -> Dict[str, Any]:
    """
    Release an environment back to the pool.
    Always called — even on failure paths (finally block in verify()).
    Never raises.
    """
    if not environment_id:
        return _ok({"released": False, "reason": "no environment_id"})
    try:
        daemon = _get_daemon()
        result = daemon.release_environment(environment_id)
        return result
    except Exception as exc:
        logger.warning(f"[ForgeHarbor] release_environment error (non-fatal): {exc}")
        return _error("FORGE_HARBOR_RELEASE_ERROR", str(exc))


def reset_daemon() -> None:
    """Reset the module-level singleton (for testing)."""
    global _daemon
    _daemon = None
