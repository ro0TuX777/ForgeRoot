from typing import Any, Dict, List


class ApprovalPolicyError(Exception):
    pass


def _policy(run_config: Dict[str, Any]) -> Dict[str, Any]:
    policy = run_config.get("approval_policy")
    if not isinstance(policy, dict):
        raise ApprovalPolicyError("approval policy missing in run_config")
    return policy


def requires_approval(
    decision_record: Dict[str, Any],
    proposed_action: Dict[str, Any],
    mode: str,
    run_config: Dict[str, Any],
) -> bool:
    policy = _policy(run_config)
    decision = decision_record.get("decision")
    if decision == "DENY":
        return False
    if decision == "ESCALATE":
        return True

    if mode == "supervised":
        if decision == "ALLOW":
            return bool(policy.get("require_for_allow", True))
        if decision == "ALLOW_WITH_MODS":
            return bool(policy.get("require_for_allow_with_mods", True))
        return True

    if mode == "ramped":
        risk_tier = (proposed_action.get("metadata") or {}).get("risk_tier", "med")
        side_effect = (proposed_action.get("metadata") or {}).get("side_effect", "write")
        action_id = proposed_action.get("action_id", "")
        auto_risk = set(policy.get("ramped_auto_allow_risk_tiers", []))
        auto_side = set(policy.get("ramped_auto_allow_side_effects", []))
        auto_reject = set(policy.get("auto_reject_actions", []))
        if action_id in auto_reject:
            return True

        # Conservative default: only plain ALLOW can be auto-allowed in ramped mode.
        if decision != "ALLOW":
            return True

        if decision == "ALLOW":
            return not (risk_tier in auto_risk and side_effect in auto_side)

    # Unknown mode: safest fallback is to require approval.
    return True


def resolve_approval(
    ticket_id: str,
    action_id: str,
    decision_record: Dict[str, Any],
    proposed_action: Dict[str, Any],
    mode: str,
    run_config: Dict[str, Any],
) -> Dict[str, Any]:
    decision_id = decision_record.get("decision_id", "")
    decision = decision_record.get("decision")
    required = requires_approval(decision_record, proposed_action, mode, run_config)

    if decision == "DENY":
        outcome = "NOT_REQUIRED"
        reason = "denied_by_policy"
    elif decision == "ESCALATE":
        outcome = "REJECTED"
        reason = "escalate_requires_human"
    elif not required:
        outcome = "NOT_REQUIRED"
        reason = "auto_allowed"
    else:
        policy = _policy(run_config)
        auto_reject = policy.get("auto_reject_actions", [])
        if action_id in auto_reject:
            outcome = "REJECTED"
            reason = "auto_reject_policy"
        else:
            outcome = "APPROVED"
            reason = "policy_allows"

    return {
        "schema_version": "0.1",
        "ticket_id": ticket_id,
        "action_id": action_id,
        "decision_id": decision_id,
        "approval_required": required,
        "approval_outcome": outcome,
        "reason": reason,
        "mode": mode,
    }
