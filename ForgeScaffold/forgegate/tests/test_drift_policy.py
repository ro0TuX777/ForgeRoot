import json
from pathlib import Path

from forgegate.core.drift import compute_drift


def test_drift_policy_thresholds(tmp_path: Path):
    entries = [
        {
            "schema_version": "0.1",
            "timestamp": "2026-01-01T00:00:00Z",
            "intent_id": "demo",
            "intent_version": "1",
            "decision": "DENY",
            "decision_id": "a" * 64,
            "input_hash": "b" * 64,
            "action_id": "write",
            "actor_id": "agent",
            "actor_profile": "dev",
            "decision_record": {"reasons": {"triggered_rules": []}},
        },
        {
            "schema_version": "0.1",
            "timestamp": "2026-01-01T00:00:01Z",
            "intent_id": "demo",
            "intent_version": "1",
            "decision": "ALLOW",
            "decision_id": "c" * 64,
            "input_hash": "d" * 64,
            "action_id": "read",
            "actor_id": "agent",
            "actor_profile": "dev",
            "decision_record": {"reasons": {"triggered_rules": []}},
        },
    ]
    report = compute_drift(entries, {"min_samples": 1, "escalation_rate_threshold": 0.1})
    assert report["total_entries"] == 2
    deny_rate = next((item for item in report["decision_distribution"] if item["id"] == "DENY"), None)
    assert deny_rate is not None
