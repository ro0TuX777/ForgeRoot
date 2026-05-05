from typing import Any, Dict, Optional

from .expr import InvalidExpression, MissingSignal, eval_expr
from .budgets import evaluate_budgets
from .hashing import compute_decision_id, compute_input_hash
from .intent_validation import validate_intent_spec


GATE_VERSION = "0.4.1"


def _decision_record_base(intent_spec: Dict[str, Any], decision: str, input_hash: str, decision_id: str) -> Dict[str, Any]:
    record = {
        "schema_version": "0.1",
        "gate_version": GATE_VERSION,
        "intent_id": intent_spec.get("intent_id", ""),
        "intent_version": intent_spec.get("intent_version", ""),
        "decision": decision,
        "decision_id": decision_id,
        "input_hash": input_hash,
        "reasons": {"triggered_rules": []},
    }
    redactions = intent_spec.get("redactions")
    if redactions:
        record["redactions_applied"] = list(redactions)
    return record


def _allow_missing(intent_spec: Dict[str, Any], path: str) -> bool:
    allowed = intent_spec.get("allow_missing_signals") or []
    return path in allowed


def _missing_behavior(rule: Dict[str, Any], default_behavior: str) -> str:
    return (rule.get("on_missing_signals") or default_behavior).lower()


def _handle_missing(intent_spec: Dict[str, Any], rule: Dict[str, Any], path: str, default_behavior: str, input_hash: str, decision_id: str):
    if _allow_missing(intent_spec, path):
        return "skip", None
    behavior = _missing_behavior(rule, default_behavior)
    if behavior == "skip":
        return "skip", None
    if behavior == "deny":
        record = _decision_record_base(intent_spec, "DENY", input_hash, decision_id)
        record["reasons"]["triggered_rules"].append({"id": "missing_signal", "type": "policy_conflict", "path": path})
        return "deny", record
    record = _missing_signal_record(intent_spec, input_hash, decision_id, path)
    return "escalate", record


def _missing_signal_record(intent_spec: Dict[str, Any], input_hash: str, decision_id: str, path: str) -> Dict[str, Any]:
    record = _decision_record_base(intent_spec, "ESCALATE", input_hash, decision_id)
    record["reasons"]["triggered_rules"].append({"id": "missing_signal", "type": "policy_conflict", "path": path})
    escalation = intent_spec.get("escalation", {}) or {}
    record["escalation"] = {
        "kind": escalation.get("kind", "policy_conflict"),
        "channels": escalation.get("channels", []),
        "required_payload_fields": escalation.get("required_payload_fields", []),
        "sla_minutes": escalation.get("sla_minutes"),
    }
    return record


def _invalid_spec_record(
    intent_spec: Dict[str, Any],
    input_hash: str,
    decision_id: str,
    errors: list,
) -> Dict[str, Any]:
    record = _decision_record_base(intent_spec, "ESCALATE", input_hash, decision_id)
    record["reasons"]["triggered_rules"].append(
        {
            "id": "invalid_intent_spec",
            "type": "policy_conflict",
            "errors": errors,
        }
    )
    escalation = intent_spec.get("escalation", {}) or {}
    record["escalation"] = {
        "kind": escalation.get("kind", "policy_conflict"),
        "channels": escalation.get("channels", []),
        "required_payload_fields": escalation.get("required_payload_fields", []),
        "sla_minutes": escalation.get("sla_minutes"),
    }
    return record


def _known_actions(intent_spec: Dict[str, Any]) -> Optional[set]:
    actions = set(intent_spec.get("actions", []) or [])
    for constraint in intent_spec.get("constraints", []) or []:
        for action in constraint.get("applies_to_actions", []) or []:
            actions.add(action)
    for boundary in intent_spec.get("boundaries", []) or []:
        action = boundary.get("action")
        if action:
            actions.add(action)
    return actions if actions else None


def evaluate(
    intent_spec: Dict[str, Any],
    proposed_action: Dict[str, Any],
    signals: Dict[str, Any],
    budget_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    input_hash = compute_input_hash(proposed_action, signals, budget_snapshot)
    decision_id = compute_decision_id(intent_spec.get("intent_version", ""), input_hash)
    validation_errors, _ = validate_intent_spec(intent_spec, strict=True)
    if validation_errors:
        return _invalid_spec_record(intent_spec, input_hash, decision_id, validation_errors)

    context = {
        "signals": (signals or {}).get("values", {}),
        "proposed_action": proposed_action,
    }

    known_actions = _known_actions(intent_spec)
    action_id = proposed_action.get("action_id")
    if known_actions is not None and action_id not in known_actions:
        record = _decision_record_base(intent_spec, "DENY", input_hash, decision_id)
        record["reasons"]["triggered_rules"].append({"id": "unknown_action", "type": "constraint", "action_id": action_id})
        return record

    # (1) Constraints
    for constraint in intent_spec.get("constraints", []) or []:
        applies = constraint.get("applies_to_actions")
        if applies and action_id not in applies:
            continue
        try:
            if eval_expr(constraint.get("when"), context):
                effect = constraint.get("effect", "deny").upper()
                decision = "DENY" if effect == "DENY" else "ESCALATE"
                record = _decision_record_base(intent_spec, decision, input_hash, decision_id)
                record["reasons"]["triggered_rules"].append(
                    {"id": constraint.get("id"), "type": "constraint", "effect": effect.lower()}
                )
                if decision == "ESCALATE":
                    escalation = intent_spec.get("escalation", {}) or {}
                    record["escalation"] = {
                        "kind": escalation.get("kind", "constraint"),
                        "channels": escalation.get("channels", []),
                        "required_payload_fields": escalation.get("required_payload_fields", []),
                        "sla_minutes": escalation.get("sla_minutes"),
                    }
                return record
        except MissingSignal as exc:
            status, record = _handle_missing(intent_spec, constraint, str(exc), "escalate", input_hash, decision_id)
            if status == "skip":
                continue
            return record
        except InvalidExpression as exc:
            return _invalid_spec_record(intent_spec, input_hash, decision_id, [str(exc)])

    # (2) Boundaries
    boundary_result_info = None
    for boundary in intent_spec.get("boundaries", []) or []:
        if boundary.get("action") and boundary.get("action") != action_id:
            continue
        if boundary.get("agent_profile") and boundary.get("agent_profile") != proposed_action.get("actor_profile"):
            continue
        try:
            if eval_expr(boundary.get("when"), context):
                allowed = boundary.get("autonomy")
                requested = proposed_action.get("autonomy", 0)
                result = "ok"
                if allowed is not None and requested > allowed:
                    result = "exceeded"
                    record = _decision_record_base(intent_spec, "ESCALATE", input_hash, decision_id)
                    record["reasons"]["triggered_rules"].append(
                        {"id": boundary.get("id"), "type": "boundary", "result": result}
                    )
                    record["reasons"]["boundary_result"] = {
                        "boundary_id": boundary.get("id"),
                        "action": action_id,
                        "allowed_autonomy": allowed,
                        "requested_autonomy": requested,
                        "result": result,
                    }
                    escalation = intent_spec.get("escalation", {}) or {}
                    record["escalation"] = {
                        "kind": escalation.get("kind", "boundary"),
                        "channels": escalation.get("channels", []),
                        "required_payload_fields": escalation.get("required_payload_fields", []),
                        "sla_minutes": escalation.get("sla_minutes"),
                    }
                    return record
                boundary_result_info = {
                    "boundary_id": boundary.get("id"),
                    "action": action_id,
                    "allowed_autonomy": allowed,
                    "requested_autonomy": requested,
                    "result": result,
                }
        except MissingSignal as exc:
            status, record = _handle_missing(intent_spec, boundary, str(exc), "escalate", input_hash, decision_id)
            if status == "skip":
                continue
            return record
        except InvalidExpression as exc:
            return _invalid_spec_record(intent_spec, input_hash, decision_id, [str(exc)])

    # (3) Budgets
    budget_state_info = None
    budgets_spec = intent_spec.get("budgets", []) or []
    if budgets_spec:
        budgets_to_eval = []
        for budget in budgets_spec:
            try:
                if eval_expr(budget.get("when"), context):
                    budgets_to_eval.append(budget)
            except MissingSignal as exc:
                status, record = _handle_missing(intent_spec, budget, str(exc), "escalate", input_hash, decision_id)
                if status == "skip":
                    continue
                return record
            except InvalidExpression as exc:
                return _invalid_spec_record(intent_spec, input_hash, decision_id, [str(exc)])

        evaluated = evaluate_budgets(budgets_to_eval, budget_snapshot)
        budget_state_info = {"budgets": evaluated}
        for state in evaluated:
            if state.get("status") == "exceeded":
                effect = "ESCALATE"
                for budget in budgets_spec:
                    if budget.get("id") == state.get("id"):
                        effect = budget.get("effect", "ESCALATE").upper()
                        break
                decision = "DENY" if effect == "DENY" else "ESCALATE"
                record = _decision_record_base(intent_spec, decision, input_hash, decision_id)
                record["reasons"]["triggered_rules"].append(
                    {"id": state.get("id"), "type": "budget", "effect": effect.lower(), "used": state.get("used"), "limit": state.get("limit")}
                )
                record["reasons"]["budget_state"] = budget_state_info
                if decision == "ESCALATE":
                    escalation = intent_spec.get("escalation", {}) or {}
                    record["escalation"] = {
                        "kind": escalation.get("kind", "budget"),
                        "channels": escalation.get("channels", []),
                        "required_payload_fields": escalation.get("required_payload_fields", []),
                        "sla_minutes": escalation.get("sla_minutes"),
                    }
                return record

    # (4) Tradeoffs
    active_tradeoff_id = None
    for tradeoff in intent_spec.get("tradeoffs", []) or []:
        try:
            if eval_expr(tradeoff.get("when"), context):
                active_tradeoff_id = tradeoff.get("id")
                break
        except MissingSignal as exc:
            status, record = _handle_missing(intent_spec, tradeoff, str(exc), "skip", input_hash, decision_id)
            if status == "skip":
                continue
            return record
        except InvalidExpression as exc:
            return _invalid_spec_record(intent_spec, input_hash, decision_id, [str(exc)])

    # (5) Shaping
    mods = None
    for shaping in intent_spec.get("shaping", []) or []:
        try:
            if eval_expr(shaping.get("when"), context):
                mods = shaping.get("mods") or {}
                break
        except MissingSignal as exc:
            status, record = _handle_missing(intent_spec, shaping, str(exc), "skip", input_hash, decision_id)
            if status == "skip":
                continue
            return record
        except InvalidExpression as exc:
            return _invalid_spec_record(intent_spec, input_hash, decision_id, [str(exc)])

    decision = "ALLOW_WITH_MODS" if mods else "ALLOW"
    record = _decision_record_base(intent_spec, decision, input_hash, decision_id)
    if active_tradeoff_id:
        record["reasons"]["active_tradeoff_id"] = active_tradeoff_id
    if boundary_result_info:
        record["reasons"]["boundary_result"] = boundary_result_info
    if budget_state_info:
        record["reasons"]["budget_state"] = budget_state_info
    if mods:
        record["mods"] = mods
        record["reasons"]["triggered_rules"].append({"id": "shaping", "type": "shaping"})
    return record
