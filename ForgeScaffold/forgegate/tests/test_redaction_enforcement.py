from pathlib import Path

from forgegate.adapters.tool_router import ToolRouter, ToolSpec
from forgegate.core.drift import load_ledger


def test_redaction_enforced(tmp_path: Path):
    intent_spec = {
        "intent_id": "demo",
        "intent_version": "1",
        "redactions": ["params.secret", "values.token"],
    }

    def echo(params):
        return params

    router = ToolRouter(intent_spec=intent_spec)
    router.ledger_path = str(tmp_path / "ledger.jsonl")
    router.register_tool(ToolSpec("echo", "read", "read", "low"), echo)

    actor = {"id": "agent", "profile": "dev"}
    router.call_tool(
        "echo",
        {"secret": "top", "visible": "ok"},
        actor,
        {"schema_version": "0.1", "values": {"token": "t", "ok": True}},
    )

    entry = load_ledger(router.ledger_path)[0]
    assert "secret" not in entry["proposed_action"]["params"]
    assert "token" not in entry["signals"]["values"]
