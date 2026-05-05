import json
from pathlib import Path

import pytest

from forgeworks.runner.forgegate_bridge import ForgeGateBridgeError, evaluate_action


@pytest.fixture()
def intent_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "intent_bundle"
    (bundle / "intent").mkdir(parents=True)
    (bundle / "intent" / "intent_spec.json").write_text(
        json.dumps({"intent_id": "demo", "intent_version": "1"})
    )
    return bundle


def test_bridge_returns_decision(intent_bundle: Path):
    forgegate = pytest.importorskip("forgegate")
    proposed = {
        "schema_version": "0.1",
        "action_id": "ticket.advance_phase",
        "actor_id": "tester",
        "actor_profile": "shadow",
        "params": {"ticket_id": "T1"},
    }
    signals = {"schema_version": "0.1", "values": {}}
    result = evaluate_action(str(intent_bundle), proposed, signals)
    assert "decision" in result
    assert "decision_id" in result


def test_bridge_missing_package(monkeypatch, intent_bundle: Path):
    import builtins

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("forgegate"):
            raise ModuleNotFoundError("forgegate")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    with pytest.raises(ForgeGateBridgeError):
        evaluate_action(
            str(intent_bundle),
            {"schema_version": "0.1", "action_id": "x", "actor_id": "a", "actor_profile": "shadow", "params": {}},
            {"schema_version": "0.1", "values": {}},
        )


def test_bridge_invalid_intent_path(tmp_path: Path):
    with pytest.raises(ForgeGateBridgeError):
        evaluate_action(str(tmp_path / "missing"), {"schema_version": "0.1", "action_id": "x", "actor_id": "a", "actor_profile": "shadow", "params": {}}, {"schema_version": "0.1", "values": {}})
