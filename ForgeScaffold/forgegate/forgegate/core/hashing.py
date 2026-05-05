import hashlib
from typing import Any, Dict, Optional

from .canonicalize import canonical_json, strip_volatile


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_signal_values(signals: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not signals:
        return {}
    values = signals.get("values")
    if isinstance(values, dict):
        return values
    return signals


def compute_input_hash(
    proposed_action: Dict[str, Any],
    signals: Optional[Dict[str, Any]],
    budget_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    action_clean = strip_volatile(proposed_action)
    payload: Dict[str, Any] = {
        "proposed_action": action_clean,
        "signals": _extract_signal_values(signals),
    }
    if budget_snapshot is not None:
        payload["budget_snapshot"] = strip_volatile(budget_snapshot)
    canonical = canonical_json(payload)
    return _sha256_hex(canonical)


def compute_decision_id(intent_version: str, input_hash: str) -> str:
    return _sha256_hex(f"{intent_version}:{input_hash}")
