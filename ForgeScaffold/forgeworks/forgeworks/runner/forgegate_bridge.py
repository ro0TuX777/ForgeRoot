import json
from pathlib import Path
from typing import Any, Dict, Optional


class ForgeGateBridgeError(Exception):
    pass


def _load_intent_spec(intent_bundle_path: str) -> Dict[str, Any]:
    base = Path(intent_bundle_path)
    if base.is_dir():
        intent_path = base / "intent" / "intent_spec.json"
    else:
        intent_path = base
    if not intent_path.exists():
        raise ForgeGateBridgeError("ForgeGate bridge unavailable - invalid intent bundle path")
    return json.loads(intent_path.read_text())


def evaluate_action(
    intent_bundle_path: str,
    proposed_action: Dict[str, Any],
    signals: Dict[str, Any],
    budget_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        from forgegate.core.evaluate import evaluate
    except ModuleNotFoundError as exc:
        raise ForgeGateBridgeError("ForgeGate bridge unavailable - missing package") from exc

    intent_spec = _load_intent_spec(intent_bundle_path)
    try:
        return evaluate(intent_spec, proposed_action, signals, budget_snapshot)
    except Exception as exc:
        raise ForgeGateBridgeError(f"ForgeGate bridge error: {exc}") from exc
