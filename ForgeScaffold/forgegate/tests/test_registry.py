import json
from pathlib import Path

from forgegate.core.bundle import validate_bundle
from forgegate.registry.registry import registry_add, registry_list, registry_promote, registry_rollback, registry_approve


def _create_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "IntentBundle"
    (bundle / "catalogs").mkdir(parents=True)
    (bundle / "intent").mkdir(parents=True)
    (bundle / "tests" / "scenarios").mkdir(parents=True)
    (bundle / "meta.yaml").write_text("owners: []\n")

    (bundle / "catalogs" / "action_catalog.json").write_text(json.dumps({
        "schema_version": "0.1",
        "actions": [{"action_id": "read", "description": "read"}],
    }))
    (bundle / "catalogs" / "signal_catalog.json").write_text(json.dumps({
        "schema_version": "0.1",
        "signals": [{"signal_id": "risk", "description": "risk"}],
    }))
    intent_spec = {"intent_id": "demo", "intent_version": "1"}
    (bundle / "intent" / "intent_spec.json").write_text(json.dumps(intent_spec))
    scenario = {
        "proposed_action": {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}},
        "signals": {"schema_version": "0.1", "values": {}},
        "expected": {"decision": "ALLOW"},
    }
    (bundle / "tests" / "scenarios" / "01.json").write_text(json.dumps(scenario))
    return bundle


def test_registry_add_promote_rollback(tmp_path: Path):
    bundle = _create_bundle(tmp_path)
    validate_bundle(str(bundle))

    registry_add(str(tmp_path), str(bundle), "demo", "1")
    manifest = registry_list(str(tmp_path))
    assert manifest["intents"][0]["intent_id"] == "demo"

    registry_promote(str(tmp_path), "demo", "1")
    manifest = registry_list(str(tmp_path))
    assert manifest["intents"][0]["active_version"] == "1"

    registry_rollback(str(tmp_path), "demo", "1")
    manifest = registry_list(str(tmp_path))
    assert manifest["intents"][0]["active_version"] == "1"


def test_registry_approve(tmp_path: Path):
    bundle = _create_bundle(tmp_path)
    registry_add(str(tmp_path), str(bundle), "demo", "1")
    stamp = registry_approve(str(tmp_path), "demo", "1", "operator", "ok")
    assert stamp.exists()
