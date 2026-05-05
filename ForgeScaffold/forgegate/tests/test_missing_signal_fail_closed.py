from forgegate.core.evaluate import evaluate


def test_missing_signal_fail_closed():
    intent = {
        "intent_id": "demo",
        "intent_version": "1",
        "constraints": [
            {"id": "needs_signal", "when": {"op": "eq", "left": {"var": "signals.required"}, "right": "yes"}, "effect": "deny"}
        ],
        "escalation": {"channels": ["ops"], "required_payload_fields": []},
    }
    action = {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}}
    signals = {"schema_version": "0.1", "values": {}}

    record = evaluate(intent, action, signals)
    assert record["decision"] == "ESCALATE"
    assert record["reasons"]["triggered_rules"][0]["id"] == "missing_signal"
