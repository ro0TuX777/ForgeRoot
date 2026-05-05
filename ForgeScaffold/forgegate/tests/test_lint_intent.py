import json
from pathlib import Path

import pytest

from forgegate.core.lint import lint_intent, LintError


def _make_bundle(tmp_path: Path, signal_id: str = "risk", action_id: str = "read") -> Path:
    bundle = tmp_path / "IntentBundle"
    (bundle / "catalogs").mkdir(parents=True)
    (bundle / "intent").mkdir(parents=True)
    (bundle / "tests" / "scenarios").mkdir(parents=True)
    (bundle / "meta.yaml").write_text("owners: []\n")

    (bundle / "catalogs" / "action_catalog.json").write_text(json.dumps({
        "schema_version": "0.1",
        "actions": [{"action_id": action_id, "description": "read"}],
    }))
    (bundle / "catalogs" / "signal_catalog.json").write_text(json.dumps({
        "schema_version": "0.1",
        "signals": [{"signal_id": signal_id, "description": "risk"}],
    }))

    intent_spec = {
        "intent_id": "demo",
        "intent_version": "1",
        "constraints": [
            {"id": "c1", "when": {"op": "eq", "left": {"var": "signals.risk"}, "right": "high"}, "effect": "deny"}
        ],
    }
    (bundle / "intent" / "intent_spec.json").write_text(json.dumps(intent_spec))

    scenario = {
        "proposed_action": {"schema_version": "0.1", "action_id": action_id, "actor_id": "agent", "params": {}},
        "signals": {"schema_version": "0.1", "values": {}},
        "expected": {"decision": "ALLOW"},
    }
    (bundle / "tests" / "scenarios" / "01.json").write_text(json.dumps(scenario))
    return bundle


def test_lint_intent_pass(tmp_path: Path):
    bundle = _make_bundle(tmp_path)
    result = lint_intent(str(bundle))
    assert result["status"] == "PASS"


def test_lint_intent_unknown_signal(tmp_path: Path):
    bundle = _make_bundle(tmp_path, signal_id="other")
    with pytest.raises(LintError):
        lint_intent(str(bundle))
