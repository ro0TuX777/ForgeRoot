from pathlib import Path

from forgegate.adapters.tool_router import ToolRouter, ToolSpec
from forgegate.core.drift import compute_drift, load_ledger


def test_tool_router_allow_and_block(tmp_path: Path):
    intent_spec = {
        "intent_id": "demo",
        "intent_version": "1",
        "constraints": [
            {"id": "deny_prod", "when": {"op": "eq", "left": {"var": "signals.env"}, "right": "prod"}, "effect": "deny"}
        ],
        "escalation": {"channels": ["ops"], "required_payload_fields": ["ticket"]},
    }

    def echo_tool(params):
        return {"ok": True, "params": params}

    router = ToolRouter(intent_spec=intent_spec)
    router.ledger_path = str(tmp_path / "ledger.jsonl")
    router.register_tool(ToolSpec("echo", "read", "read", "low"), echo_tool)

    actor = {"id": "agent", "profile": "dev"}

    result_allow = router.call_tool(
        "echo",
        {"x": 1},
        actor,
        {"schema_version": "0.1", "values": {"env": "dev"}},
    )
    assert result_allow.decision == "ALLOW"

    result_block = router.call_tool(
        "echo",
        {"x": 2},
        actor,
        {"schema_version": "0.1", "values": {"env": "prod"}},
    )
    assert result_block.decision in {"ESCALATE", "DENY"}

    entries = load_ledger(router.ledger_path)
    assert len(entries) == 2
    report = compute_drift(entries, {"min_samples": 1})
    assert report["total_entries"] == 2


def test_allow_with_mods_caps(tmp_path: Path):
    intent_spec = {
        "intent_id": "demo",
        "intent_version": "1",
        "shaping": [
            {"id": "cap", "when": {"op": "gt", "left": {"var": "signals.cost"}, "right": 10}, "mods": {"caps": {"limit": 5}}}
        ],
    }

    def echo_tool(params):
        return params

    router = ToolRouter(intent_spec=intent_spec)
    router.ledger_path = str(tmp_path / "ledger.jsonl")
    router.register_tool(ToolSpec("echo", "read", "read", "low"), echo_tool)

    actor = {"id": "agent", "profile": "dev"}
    result = router.call_tool(
        "echo",
        {"limit": 100},
        actor,
        {"schema_version": "0.1", "values": {"cost": 20}},
    )
    assert result.decision == "ALLOW_WITH_MODS"
    assert result.output["limit"] == 5


def test_signal_type_mismatch(tmp_path: Path):
    intent_spec = {
        "intent_id": "demo",
        "intent_version": "1",
        "escalation": {"channels": ["ops"], "required_payload_fields": []},
    }

    def echo_tool(params):
        return params

    router = ToolRouter(intent_spec=intent_spec)
    router.ledger_path = str(tmp_path / "ledger.jsonl")
    router.register_tool(ToolSpec("echo", "read", "read", "low"), echo_tool)

    # inject signal catalog via registry root mock
    bundle = tmp_path / "registry" / "intents" / "demo" / "1" / "IntentBundle"
    (bundle / "catalogs").mkdir(parents=True)
    (tmp_path / "registry" / "manifest.json").write_text(
        '{"schema_version":"0.1","intents":[{"intent_id":"demo","active_version":"1","versions":["1"]}],"history":[]}'
    )
    (bundle / "catalogs" / "signal_catalog.json").write_text(
        '{"schema_version":"0.1","signals":[{"signal_id":"risk","description":"risk","type":"number"}]}'
    )
    router.registry_root = str(tmp_path)

    actor = {"id": "agent", "profile": "dev"}
    result = router.call_tool(
        "echo",
        {"x": 1},
        actor,
        {"schema_version": "0.1", "values": {"risk": "high"}},
    )
    assert result.decision == "ESCALATE"
