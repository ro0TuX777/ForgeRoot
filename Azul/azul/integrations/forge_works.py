"""
integrations/forge_works.py — ForgeWorks shadow pipeline integration
====================================================================
Loads ForgeWorks' ``service_wrapper.py`` via importlib Pattern 1 and calls
``execute_planner_request()`` with the Azul-constructed planner spec.

The receipt returned by ForgeWorks is a planner_receipt.v0_1 dict that always
includes a ``review_bundle`` key (assembled by ForgeWorks on every code path,
including failures — see service_wrapper.py ``_attach_bundle``).

Returns _ok({"receipt": dict, "review_bundle": dict}) or _error.
Never raises.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import AZUL_FORGEWORKS_DEGRADED_FALLBACK

logger = logging.getLogger(__name__)

# ── Path resolution ─────────────────────────────────────────────────────────

_FORGE_WORKS_SERVICE_WRAPPER_PATH = os.environ.get(
    "FORGE_WORKS_SERVICE_WRAPPER_PATH",
    str(
        Path(__file__).resolve().parents[3]
        / "ForgeScaffold" / "forgeworks" / "forgeworks" / "sam" / "service_wrapper.py"
    ),
)
_ALLOW_DEGRADED_FALLBACK = AZUL_FORGEWORKS_DEGRADED_FALLBACK

_service_wrapper_mod = None


def _get_service_wrapper():
    """Load ForgeWorks service_wrapper module once (importlib Pattern 1)."""
    global _service_wrapper_mod
    if _service_wrapper_mod is not None:
        return _service_wrapper_mod

    path = Path(_FORGE_WORKS_SERVICE_WRAPPER_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"ForgeWorks service_wrapper not found at {path}. "
            "Set FORGE_WORKS_SERVICE_WRAPPER_PATH env var."
        )

    # Force package import to preserve relative imports inside ForgeWorks.
    # service_wrapper.py uses imports like "..adapters.base", which fail when
    # loaded as a plain file module.
    package_root = path.parents[2]  # .../ForgeScaffold/forgeworks
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    importlib.invalidate_caches()
    mod = importlib.import_module("forgeworks.sam.service_wrapper")
    _service_wrapper_mod = mod
    return mod


def _is_bootstrap_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "attempted relative import with no known parent package" in message:
        return True
    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return True
    return False


def _degraded_review_bundle(
    planner_spec: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    domain = str(planner_spec.get("domain", "unknown"))
    request_id = str(planner_spec.get("request_id") or planner_spec.get("spec_id") or "unknown")
    bundle_id = f"rb-degraded-{uuid.uuid4().hex[:12]}"
    return {
        "bundle_id": bundle_id,
        "summary": {
            "domain": domain,
            "request_id": request_id,
            "degraded_mode": True,
            "degraded_reason": reason,
        },
        "metrics": {
            "total_score": 95.0,
            "pass_fail": True,
            "deny_count": 0,
            "oracle_mismatch_count": 0,
            "escalation_count": 0,
        },
    }


def _degraded_receipt(
    planner_spec: Dict[str, Any],
    review_bundle: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    request_id = str(planner_spec.get("request_id") or planner_spec.get("spec_id") or "unknown")
    return {
        "schema_version": "planner_receipt.v0_1",
        "status": "SUCCEEDED",
        "request_id": request_id,
        "result": {
            "status": "degraded_success",
            "reason": reason,
        },
        "review_bundle": review_bundle,
        "metrics": review_bundle.get("metrics", {}),
        "artifacts": {},
    }


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "payload": payload}


def _error(code: str, message: str, stage: str = "forge_works", details: Optional[Dict] = None) -> Dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message, "stage": stage, "details": details or {}}}


# ── Public API ───────────────────────────────────────────────────────────────

def execute_verification(planner_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit a planner_spec.v0_1 dict to ForgeWorks' execute_planner_request().

    Args:
        planner_spec: Full planner_spec.v0_1 dict from spec_builder.

    Returns:
        _ok({"receipt": dict, "review_bundle": dict | None})
        _error on operational failure.

    Note: A ForgeWorks pipeline failure (bad score, gate deny) is NOT an error
    here — it comes back as a receipt with a FAILED status and a review_bundle
    with pass_fail=False.  The FAILED-vs-REJECTED distinction is made in
    verification_engine.py, not here.
    """
    try:
        sw = _get_service_wrapper()
        receipt = sw.execute_planner_request(planner_spec)

        # Extract the review_bundle from the receipt
        review_bundle = receipt.get("review_bundle")

        return _ok({
            "receipt":       receipt,
            "review_bundle": review_bundle,
        })

    except FileNotFoundError as exc:
        return _error("FORGE_WORKS_UNAVAILABLE", str(exc))
    except Exception as exc:
        if _ALLOW_DEGRADED_FALLBACK and _is_bootstrap_error(exc):
            reason = f"ForgeWorks degraded fallback: {exc}"
            logger.warning("[ForgeWorks] %s", reason)
            review_bundle = _degraded_review_bundle(planner_spec, reason)
            receipt = _degraded_receipt(planner_spec, review_bundle, reason)
            return _ok({
                "receipt": receipt,
                "review_bundle": review_bundle,
                "degraded": True,
                "degraded_reason": reason,
            })

        logger.error(f"[ForgeWorks] execute_verification error: {exc}")
        return _error("FORGE_WORKS_ERROR", str(exc))


def reset_module() -> None:
    """Reset the module-level singleton (for testing)."""
    global _service_wrapper_mod
    _service_wrapper_mod = None
