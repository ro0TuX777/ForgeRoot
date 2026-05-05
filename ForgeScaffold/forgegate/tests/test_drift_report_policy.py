import json
from pathlib import Path

from forgegate.cli.main import cmd_drift_report


def test_drift_report_exit_codes(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    entry = {
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
    }
    ledger.write_text(json.dumps(entry) + "\n")

    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"thresholds": {"deny_rate.max": 0.0}, "severities": {"critical": ["deny_rate.max"]}}))

    class Args:
        def __init__(self, ledger_path: str, policy_path: str):
            self.ledger = ledger_path
            self.config = None
            self.policy = policy_path

    exit_code = cmd_drift_report(Args(str(ledger), str(policy)))
    assert exit_code == 3
