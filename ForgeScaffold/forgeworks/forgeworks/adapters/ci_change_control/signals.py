import json
from pathlib import Path
from typing import Dict, List


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def _action_class_from_test_name(test_name: str) -> str:
    name = test_name.lower()
    if "missing_signal" in name or "missing-signal" in name:
        return ""
    if "approval" in name or "bypass" in name:
        return "approval_bypass"
    if "disable" in name or "skip" in name:
        return "disable_tests"
    if "workflow" in name or "ci_yaml" in name:
        return "edit_ci_workflows"
    if "core" in name or "auth" in name:
        return "core_path_patch"
    if "drift" in name:
        return "edit_ci_workflows"
    return "code_patch"


def extract_signals(raw_dir: str, ticket_ids: List[str]) -> List[Dict]:
    base = Path(raw_dir)
    failing = _load_json(base / "failing_tests.json")
    manifest = _load_json(base / "repo_snapshot_manifest.json")

    policy_path = base / "policy.json"
    policy = _load_json(policy_path) if policy_path.exists() else {}
    forbidden_actions = policy.get("forbidden_actions", []) or []
    hard_deny_actions = policy.get("hard_deny_actions", []) or []

    tests = failing.get("failing_tests", []) or []
    retry_count = int(len(tests))
    touches_ci = bool(manifest.get("touches_ci_config"))
    touches_core = bool(manifest.get("touches_core_paths"))

    signals: List[Dict] = []
    for idx, ticket_id in enumerate(ticket_ids):
        test_name = tests[idx] if idx < len(tests) else ""
        action_class = _action_class_from_test_name(test_name) if test_name else "code_patch"
        values = {
            "queue.pressure": 0.2,
            "echo.fidelity": "D4",
            "retry.count": retry_count,
            "change.touches_ci_config": touches_ci,
            "change.touches_core_paths": touches_core,
            "spec.present": True,
            "policy.forbidden_actions": forbidden_actions,
            "policy.hard_deny_actions": hard_deny_actions,
            "action.class": action_class,
            "policy": {"forbidden_actions": forbidden_actions, "hard_deny_actions": hard_deny_actions},
            "change": {"touches_ci_config": touches_ci, "touches_core_paths": touches_core},
            "action": {"class": action_class},
        }
        if not action_class:
            # Missing-signal test case: omit action/policy to force fail-closed escalation
            values.pop("action.class", None)
            values.pop("action", None)
            values.pop("policy.forbidden_actions", None)
            values.pop("policy.hard_deny_actions", None)
            values.pop("policy", None)
        signals.append(
            {
                "schema_version": "0.1",
                "ticket_id": ticket_id,
                "values": values,
            }
        )
    return signals
