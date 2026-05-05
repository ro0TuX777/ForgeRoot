import json
from pathlib import Path

from forgegate.core.bundle import validate_bundle


def test_validate_bundle(tmp_path: Path):
    bundle = tmp_path / "IntentBundle"
    (bundle / "catalogs").mkdir(parents=True)
    (bundle / "intent").mkdir(parents=True)
    (bundle / "tests" / "scenarios").mkdir(parents=True)
    (bundle / "meta.yaml").write_text("owners: []\n")

    action_catalog = {"schema_version": "0.1", "actions": [{"action_id": "read", "description": "read"}]}
    signal_catalog = {"schema_version": "0.1", "signals": [{"signal_id": "risk", "description": "risk"}]}
    intent_spec = {"intent_id": "demo", "intent_version": "1"}

    (bundle / "catalogs" / "action_catalog.json").write_text(json.dumps(action_catalog))
    (bundle / "catalogs" / "signal_catalog.json").write_text(json.dumps(signal_catalog))
    (bundle / "intent" / "intent_spec.json").write_text(json.dumps(intent_spec))

    scenario = {
        "intent": intent_spec,
        "proposed_action": {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}},
        "signals": {"schema_version": "0.1", "values": {}},
        "expected": {"decision": "ALLOW"},
    }
    (bundle / "tests" / "scenarios" / "01.json").write_text(json.dumps(scenario))

    result = validate_bundle(str(bundle))
    assert result["status"] == "PASS"
