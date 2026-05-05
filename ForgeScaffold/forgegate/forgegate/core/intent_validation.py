from typing import Any, Dict, List, Tuple


KNOWN_TOP_LEVEL_KEYS = {
    "intent_id",
    "intent_version",
    "constraints",
    "boundaries",
    "budgets",
    "tradeoffs",
    "escalation",
    "tradeoff_objective",
    "shaping",
    "actions",
    "redactions",
    "allow_missing_signals",
    "payload_limits",
}

LOGICAL_OPS = {"and", "or", "not"}
BINARY_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "contains", "has_substr"}
VALID_OPS = LOGICAL_OPS | BINARY_OPS


def _validate_expr(expr: Any, label: str, errors: List[str]) -> None:
    if expr is None or isinstance(expr, bool):
        return
    if isinstance(expr, (int, float, str)):
        errors.append(f"{label}: expression must be AST object, boolean, or null")
        return
    if not isinstance(expr, dict):
        errors.append(f"{label}: expression must be AST object")
        return

    if "var" in expr and "op" not in expr:
        var_name = expr.get("var")
        if not isinstance(var_name, str) or not var_name:
            errors.append(f"{label}: var reference must be a non-empty string")
        return

    op = expr.get("op")
    if not isinstance(op, str) or op not in VALID_OPS:
        errors.append(f"{label}: unknown operator {op!r}")
        return

    if op in {"and", "or"}:
        args = expr.get("args")
        if not isinstance(args, list) or not args:
            errors.append(f"{label}: '{op}' operator requires non-empty list args")
            return
        for idx, arg in enumerate(args):
            _validate_expr(arg, f"{label}.args[{idx}]", errors)
        return

    if op == "not":
        if "arg" not in expr:
            errors.append(f"{label}: 'not' operator requires arg")
            return
        _validate_expr(expr.get("arg"), f"{label}.arg", errors)
        return

    if "left" not in expr or "right" not in expr:
        errors.append(f"{label}: '{op}' operator requires left and right")
        return

    left = expr.get("left")
    right = expr.get("right")
    if isinstance(left, dict) and "var" in left:
        _validate_expr(left, f"{label}.left", errors)
    if isinstance(right, dict) and "var" in right:
        _validate_expr(right, f"{label}.right", errors)


def validate_intent_spec(intent_spec: Dict[str, Any], strict: bool = False) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(intent_spec, dict):
        return ["intent_spec must be a JSON object"], warnings

    for required_key in ("intent_id", "intent_version"):
        if not isinstance(intent_spec.get(required_key), str) or not intent_spec.get(required_key):
            errors.append(f"intent_spec missing required non-empty field: {required_key}")

    unknown_keys = sorted(set(intent_spec.keys()) - KNOWN_TOP_LEVEL_KEYS)
    if unknown_keys:
        msg = f"unknown intent_spec keys (ignored): {', '.join(unknown_keys)}"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    policy_sections = ("constraints", "boundaries", "budgets", "tradeoffs", "shaping")
    policy_markers = policy_sections + ("actions", "redactions", "payload_limits")
    has_policy = any(bool(intent_spec.get(section)) for section in policy_markers)
    if not has_policy:
        warnings.append("intent_spec has no active policy sections")

    for section in policy_sections:
        entries = intent_spec.get(section) or []
        if entries is None:
            continue
        if not isinstance(entries, list):
            errors.append(f"intent_spec.{section} must be a list")
            continue
        for idx, rule in enumerate(entries):
            if not isinstance(rule, dict):
                errors.append(f"intent_spec.{section}[{idx}] must be an object")
                continue
            _validate_expr(rule.get("when"), f"intent_spec.{section}[{idx}].when", errors)

    return errors, warnings
