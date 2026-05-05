from forgegate.core.evaluate import evaluate


def test_nonce_ignored_for_hash():
    intent = {"intent_id": "demo", "intent_version": "1"}
    action1 = {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}, "nonce": "a"}
    action2 = {"schema_version": "0.1", "action_id": "read", "actor_id": "agent", "params": {}, "nonce": "b"}
    signals = {"schema_version": "0.1", "values": {}}

    rec1 = evaluate(intent, action1, signals)
    rec2 = evaluate(intent, action2, signals)

    assert rec1["input_hash"] == rec2["input_hash"]
    assert rec1["decision_id"] == rec2["decision_id"]
