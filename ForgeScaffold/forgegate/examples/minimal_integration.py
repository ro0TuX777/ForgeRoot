import json
from forgegate.core.evaluate import evaluate

intent_spec = {
    "intent_id": "demo",
    "intent_version": "1",
    "escalation": {"channels": ["ops"], "required_payload_fields": ["ticket"]},
}

proposed_action = {
    "schema_version": "0.1",
    "action_id": "read",
    "actor_id": "agent",
    "params": {"path": "README.md"},
}

signals = {"schema_version": "0.1", "values": {"risk": 0.1}}

record = evaluate(intent_spec, proposed_action, signals)
print(json.dumps(record, indent=2))
