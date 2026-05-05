import json
import subprocess
import sys

import pytest

from forgegate.core.evaluate import ForgeGateEvaluationError, evaluate


def _intent(*constraints):
    return {
        "intent_id": "intent-001",
        "intent_version": "v1",
        "constraints": list(constraints),
    }


def _action(action_id="deploy-prod"):
    return {"action_id": action_id, "type": "deploy"}


def test_evaluate_allows_when_no_constraints_trigger():
    result = evaluate(
        _intent({
            "id": "deny-critical-risk",
            "effect": "DENY",
            "when": {"op": "eq", "left": {"var": "signals.risk"}, "right": "critical"},
        }),
        _action(),
        {"risk": "low"},
    )

    assert result == {
        "decision": "ALLOW",
        "reasons": {"triggered_rules": []},
        "intent_id": "intent-001",
        "intent_version": "v1",
        "action_id": "deploy-prod",
    }


def test_deny_short_circuits_later_constraints():
    result = evaluate(
        _intent(
            {
                "id": "deny-critical-risk",
                "effect": "DENY",
                "when": {"op": "eq", "left": {"var": "signals.risk"}, "right": "critical"},
            },
            {
                "id": "escalate-prod",
                "effect": "ESCALATE",
                "when": {"op": "eq", "left": {"var": "action.type"}, "right": "deploy"},
            },
        ),
        _action(),
        {"risk": "critical"},
    )

    assert result["decision"] == "DENY"
    assert result["reasons"]["triggered_rules"] == ["deny-critical-risk"]


def test_escalate_takes_precedence_over_allow_with_mods():
    result = evaluate(
        _intent(
            {
                "id": "escalate-approval",
                "effect": "ESCALATE",
                "when": {"var": "signals.requires_approval"},
            },
            {
                "id": "shape-output",
                "effect": "ALLOW_WITH_MODS",
                "when": {"var": "signals.can_shape"},
            },
        ),
        _action(),
        {"values": {"requires_approval": True, "can_shape": True}},
    )

    assert result["decision"] == "ESCALATE"
    assert result["reasons"]["triggered_rules"] == ["escalate-approval", "shape-output"]


def test_allow_with_mods_applies_when_no_stronger_effect_triggered():
    result = evaluate(
        _intent({
            "id": "shape-output",
            "effect": "ALLOW_WITH_MODS",
            "when": {"op": "contains", "left": {"var": "signals.tags"}, "right": "redact"},
        }),
        _action(),
        {"tags": ["redact", "summarize"]},
    )

    assert result["decision"] == "ALLOW_WITH_MODS"
    assert result["reasons"]["triggered_rules"] == ["shape-output"]


def test_constraints_can_target_specific_action_ids():
    result = evaluate(
        _intent({
            "id": "deny-prod-deploy",
            "effect": "DENY",
            "applies_to_actions": ["deploy-prod"],
            "when": True,
        }),
        _action("deploy-staging"),
        {"risk": "critical"},
    )

    assert result["decision"] == "ALLOW"
    assert result["reasons"]["triggered_rules"] == []


def test_expression_supports_in_operator_against_budget_snapshot():
    result = evaluate(
        _intent({
            "id": "deny-disallowed-cost-center",
            "effect": "DENY",
            "when": {
                "op": "not",
                "arg": {
                    "op": "in",
                    "left": {"var": "budget.cost_center"},
                    "right": ["research", "qa"],
                },
            },
        }),
        _action(),
        {"risk": "low"},
        {"cost_center": "sales"},
    )

    assert result["decision"] == "DENY"
    assert result["reasons"]["triggered_rules"] == ["deny-disallowed-cost-center"]


def test_same_inputs_produce_same_decision_record():
    intent = _intent({
        "id": "deny-critical-risk",
        "effect": "DENY",
        "when": {"op": "eq", "left": {"var": "signals.risk"}, "right": "critical"},
    })
    action = _action()
    signals = {"risk": "critical"}

    assert evaluate(intent, action, signals) == evaluate(intent, action, signals)


def test_unsupported_operator_raises_evaluation_error():
    with pytest.raises(ForgeGateEvaluationError, match="Unsupported op: gt"):
        evaluate(
            _intent({
                "id": "unsupported",
                "effect": "DENY",
                "when": {"op": "gt", "left": {"var": "signals.risk_score"}, "right": 80},
            }),
            _action(),
            {"risk_score": 90},
        )


def test_cli_evaluate_outputs_decision_record_json(tmp_path):
    intent_path = tmp_path / "intent.json"
    action_path = tmp_path / "action.json"
    signals_path = tmp_path / "signals.json"
    intent_path.write_text(
        json.dumps(_intent({
            "id": "deny-critical-risk",
            "effect": "DENY",
            "when": {"op": "eq", "left": {"var": "signals.risk"}, "right": "critical"},
        })),
        encoding="utf-8",
    )
    action_path.write_text(json.dumps(_action()), encoding="utf-8")
    signals_path.write_text(json.dumps({"risk": "critical"}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "forgegate.cli.main",
            "evaluate",
            "--intent",
            str(intent_path),
            "--action",
            str(action_path),
            "--signals",
            str(signals_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    result = json.loads(completed.stdout)
    assert result["decision"] == "DENY"
    assert result["reasons"]["triggered_rules"] == ["deny-critical-risk"]
    assert result["intent_version"] == "v1"
    assert result["action_id"] == "deploy-prod"
