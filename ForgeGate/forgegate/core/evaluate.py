"""Minimal deterministic ForgeGate evaluator compatibility layer.

This restores the interface ForgeWorks expects:
    evaluate(intent_spec, proposed_action, signals, budget_snapshot=None) -> decision dict
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ForgeGateEvaluationError(Exception):
    """Raised when an intent spec cannot be evaluated deterministically."""


def evaluate(
    intent_spec: Dict[str, Any],
    proposed_action: Dict[str, Any],
    signals: Dict[str, Any],
    budget_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    action_id = str(proposed_action.get("action_id") or "")
    constraints = list(intent_spec.get("constraints") or [])
    triggered_rules: List[str] = []
    decision = "ALLOW"

    context = {
        "action": proposed_action or {},
        "signals": _normalize_signals(signals),
        "budget": budget_snapshot or {},
    }

    for constraint in constraints:
        applies_to = list(constraint.get("applies_to_actions") or [])
        if applies_to and action_id not in applies_to:
            continue
        when = constraint.get("when")
        if not _truthy(_eval_expr(when, context)):
            continue

        rule_id = str(constraint.get("id") or "unnamed_rule")
        effect = str(constraint.get("effect") or "DENY").upper()
        triggered_rules.append(rule_id)

        if effect == "DENY":
            decision = "DENY"
            break
        if effect == "ESCALATE" and decision != "DENY":
            decision = "ESCALATE"
        elif effect == "ALLOW_WITH_MODS" and decision == "ALLOW":
            decision = "ALLOW_WITH_MODS"

    return {
        "decision": decision,
        "reasons": {
            "triggered_rules": triggered_rules,
        },
        "intent_id": intent_spec.get("intent_id"),
        "intent_version": intent_spec.get("intent_version"),
        "action_id": action_id,
    }


def _normalize_signals(signals: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(signals, dict):
        return {}
    values = signals.get("values")
    if isinstance(values, dict):
        return values
    return signals


def _eval_expr(expr: Any, context: Dict[str, Any]) -> Any:
    if isinstance(expr, dict):
        if "var" in expr:
            return _resolve_var(str(expr["var"]), context)
        op = str(expr.get("op") or "").lower()
        if op == "eq":
            return _eval_expr(expr.get("left"), context) == _eval_expr(expr.get("right"), context)
        if op == "contains":
            left = _eval_expr(expr.get("left"), context)
            right = _eval_expr(expr.get("right"), context)
            if left is None:
                return False
            if isinstance(left, (list, tuple, set)):
                return right in left
            return str(right) in str(left)
        if op == "in":
            left = _eval_expr(expr.get("left"), context)
            right = _eval_expr(expr.get("right"), context)
            if right is None:
                return False
            if isinstance(right, (list, tuple, set)):
                return left in right
            if isinstance(right, dict):
                return left in right.keys()
            return str(left) in str(right)
        if op == "not":
            return not _truthy(_eval_expr(expr.get("arg"), context))
        raise ForgeGateEvaluationError(f"Unsupported op: {op}")
    return expr


def _resolve_var(path: str, context: Dict[str, Any]) -> Any:
    parts = [part for part in path.split('.') if part]
    current: Any = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _truthy(value: Any) -> bool:
    return bool(value)

