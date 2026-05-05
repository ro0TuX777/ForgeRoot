import json
from pathlib import Path

from forgegate.core.drift import compute_drift, load_ledger


def test_drift_report(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    entries = [
        {
            "schema_version": "0.1",
            "timestamp": "2026-01-01T00:00:00Z",
            "intent_id": "demo",
            "intent_version": "1",
            "decision": "ALLOW",
            "decision_id": "a" * 64,
            "input_hash": "b" * 64,
            "action_id": "read",
            "actor_id": "agent",
            "actor_profile": "dev",
            "decision_record": {"reasons": {"triggered_rules": []}},
        },
        {
            "schema_version": "0.1",
            "timestamp": "2026-01-01T00:00:01Z",
            "intent_id": "demo",
            "intent_version": "1",
            "decision": "ESCALATE",
            "decision_id": "c" * 64,
            "input_hash": "d" * 64,
            "action_id": "write",
            "actor_id": "agent",
            "actor_profile": "dev",
            "decision_record": {"reasons": {"triggered_rules": [{"id": "missing_signal", "type": "policy_conflict"}]}},
        },
    ]
    ledger.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    data = load_ledger(str(ledger))
    report = compute_drift(data, {"min_samples": 1, "escalation_rate_threshold": 0.5})
    assert report["total_entries"] == 2
    assert any(item["id"] == "ESCALATE" for item in report["decision_distribution"])
    assert report["missing_signal_rate"] > 0
