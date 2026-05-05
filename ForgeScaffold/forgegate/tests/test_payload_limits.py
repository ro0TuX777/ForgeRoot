from forgegate.adapters.tool_router import ToolRouter, ToolSpec


def test_payload_limits_trigger():
    intent_spec = {
        "intent_id": "demo",
        "intent_version": "1",
        "payload_limits": {"max_params_bytes": 10, "max_signals_bytes": 10},
        "escalation": {"channels": ["ops"], "required_payload_fields": []},
    }

    def echo(params):
        return params

    router = ToolRouter(intent_spec=intent_spec)
    router.register_tool(ToolSpec("echo", "read", "read", "low"), echo)

    actor = {"id": "agent", "profile": "dev"}
    result = router.call_tool(
        "echo",
        {"long": "012345678901234"},
        actor,
        {"schema_version": "0.1", "values": {"v": "012345678901234"}},
    )
    assert result.decision == "ESCALATE"
