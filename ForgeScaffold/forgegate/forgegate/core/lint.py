import json
from pathlib import Path
from typing import Any, Dict, List, Set

from .intent_validation import validate_intent_spec


class LintError(Exception):
    def __init__(self, errors: List[str], warnings: List[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _collect_vars(expr: Any, vars_out: Set[str]) -> None:
    if isinstance(expr, dict):
        if "var" in expr:
            vars_out.add(expr["var"])
        for value in expr.values():
            _collect_vars(value, vars_out)
    elif isinstance(expr, list):
        for item in expr:
            _collect_vars(item, vars_out)


def lint_intent(bundle_path: str, strict: bool = False) -> Dict[str, Any]:
    base = Path(bundle_path)
    errors: List[str] = []
    warnings: List[str] = []

    action_catalog = _load_json(base / "catalogs" / "action_catalog.json")
    signal_catalog = _load_json(base / "catalogs" / "signal_catalog.json")
    intent_spec = _load_json(base / "intent" / "intent_spec.json")

    actions = {a.get("action_id") for a in action_catalog.get("actions", [])}
    signals = {s.get("signal_id") for s in signal_catalog.get("signals", [])}

    spec_errors, spec_warnings = validate_intent_spec(intent_spec, strict=strict)
    errors.extend(spec_errors)
    warnings.extend(spec_warnings)

    # validate action references
    for constraint in intent_spec.get("constraints", []) or []:
        for action in constraint.get("applies_to_actions", []) or []:
            if action not in actions:
                errors.append(f"constraint {constraint.get('id')}: unknown action {action}")

    for boundary in intent_spec.get("boundaries", []) or []:
        action = boundary.get("action")
        if action and action not in actions:
            errors.append(f"boundary {boundary.get('id')}: unknown action {action}")

    # validate signal references in expressions
    def check_expr(expr: Any, label: str):
        vars_found: Set[str] = set()
        _collect_vars(expr, vars_found)
        for var in vars_found:
            if var.startswith("signals."):
                signal_id = var.split(".", 1)[1]
                if signal_id not in signals:
                    errors.append(f"{label}: unknown signal {signal_id}")
            elif var.startswith("proposed_action."):
                continue
            else:
                warnings.append(f"{label}: non-standard var reference {var}")

    for constraint in intent_spec.get("constraints", []) or []:
        check_expr(constraint.get("when"), f"constraint {constraint.get('id')}")
    for boundary in intent_spec.get("boundaries", []) or []:
        check_expr(boundary.get("when"), f"boundary {boundary.get('id')}")
    for budget in intent_spec.get("budgets", []) or []:
        check_expr(budget.get("when"), f"budget {budget.get('id')}")
    for tradeoff in intent_spec.get("tradeoffs", []) or []:
        check_expr(tradeoff.get("when"), f"tradeoff {tradeoff.get('id')}")

    if strict and warnings:
        errors.extend(warnings)

    if errors:
        raise LintError(errors, warnings)

    return {"status": "PASS", "errors": errors, "warnings": warnings}
