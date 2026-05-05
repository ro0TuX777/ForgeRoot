from forgegate.core.evaluate import evaluate


def test_allow_missing_signal_override():
    intent = {
        "intent_id": "demo",
        "intent_version": "1",
        "constraints": [
            {
                "id": "needs_optional",
                "when": {"op": "eq", "left": {"var": "signals.optional"}, "right": "yes"},
                "effect": "deny",
                "on_missing_signals": "skip",
            }
        ],
        "escalation": {"channels": ["ops"], "required_payload_fields": []},
    }
    action = {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}}
    signals = {"schema_version": "0.1", "values": {}}

    record = evaluate(intent, action, signals)
    assert record["decision"] == "ALLOW"
