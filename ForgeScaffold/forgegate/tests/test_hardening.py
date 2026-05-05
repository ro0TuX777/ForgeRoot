from pathlib import Path
import json

import pytest

from forgegate.core.bundle import BundleValidationError, validate_bundle
from forgegate.core.evaluate import evaluate
from forgegate.core.expr import eval_expr
from forgegate.core.lint import LintError, lint_intent


def _make_bundle(tmp_path: Path, intent_spec: dict) -> Path:
    bundle = tmp_path / "IntentBundle"
    (bundle / "catalogs").mkdir(parents=True)
    (bundle / "intent").mkdir(parents=True)
    (bundle / "tests" / "scenarios").mkdir(parents=True)
    (bundle / "meta.yaml").write_text("owners: []\n")

    action_catalog = {"schema_version": "0.1", "actions": [{"action_id": "read", "description": "read"}]}
    signal_catalog = {"schema_version": "0.1", "signals": [{"signal_id": "risk", "description": "risk"}]}
    scenario = {
        "proposed_action": {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}},
        "signals": {"schema_version": "0.1", "values": {"risk": "low"}},
        "expected": {"decision": "ALLOW"},
    }

    (bundle / "catalogs" / "action_catalog.json").write_text(json.dumps(action_catalog))
    (bundle / "catalogs" / "signal_catalog.json").write_text(json.dumps(signal_catalog))
    (bundle / "intent" / "intent_spec.json").write_text(json.dumps(intent_spec))
    (bundle / "tests" / "scenarios" / "01.json").write_text(json.dumps(scenario))
    return bundle


def test_contains_and_alias_operator():
    context = {"signals": {"path": "/tmp/sam/orchestration/file.py"}}
    expr_contains = {"op": "contains", "left": {"var": "signals.path"}, "right": "sam/orchestration"}
    expr_alias = {"op": "has_substr", "left": {"var": "signals.path"}, "right": "sam/orchestration"}
    assert eval_expr(expr_contains, context) is True
    assert eval_expr(expr_alias, context) is True


def test_evaluate_string_when_fails_closed():
    intent = {
        "intent_id": "demo",
        "intent_version": "1",
        "constraints": [{"id": "bad", "when": "signal('risk') == high", "effect": "deny"}],
        "escalation": {"channels": ["ops"], "required_payload_fields": []},
    }
    action = {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}}
    signals = {"schema_version": "0.1", "values": {"risk": "low"}}

    record = evaluate(intent, action, signals)
    assert record["decision"] == "ESCALATE"
    assert record["reasons"]["triggered_rules"][0]["id"] == "invalid_intent_spec"


def test_evaluate_unknown_top_level_key_fails_closed():
    intent = {
        "intent_id": "demo",
        "intent_version": "1",
        "rules": [{"id": "r1", "when": {"op": "eq", "left": {"var": "signals.risk"}, "right": "high"}, "effect": "deny"}],
        "escalation": {"channels": ["ops"], "required_payload_fields": []},
    }
    action = {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}}
    signals = {"schema_version": "0.1", "values": {"risk": "high"}}

    record = evaluate(intent, action, signals)
    assert record["decision"] == "ESCALATE"
    assert record["reasons"]["triggered_rules"][0]["id"] == "invalid_intent_spec"


def test_lint_warns_non_strict_for_empty_policy(tmp_path: Path):
    bundle = _make_bundle(
        tmp_path,
        {
            "intent_id": "demo",
            "intent_version": "1",
        },
    )
    result = lint_intent(str(bundle))
    assert result["status"] == "PASS"
    assert any("no active policy sections" in warning for warning in result["warnings"])


def test_lint_fails_in_strict_mode_for_empty_policy(tmp_path: Path):
    bundle = _make_bundle(
        tmp_path,
        {
            "intent_id": "demo",
            "intent_version": "1",
        },
    )
    with pytest.raises(LintError):
        lint_intent(str(bundle), strict=True)


def test_validate_bundle_strict_fails_for_empty_policy(tmp_path: Path):
    bundle = _make_bundle(
        tmp_path,
        {
            "intent_id": "demo",
            "intent_version": "1",
        },
    )
    with pytest.raises(BundleValidationError):
        validate_bundle(str(bundle), strict=True)
