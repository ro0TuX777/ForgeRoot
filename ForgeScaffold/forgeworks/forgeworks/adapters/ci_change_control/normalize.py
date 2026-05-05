import json
from pathlib import Path
from typing import Dict, List

from ...core.hashutil import compute_workcell_hash
from ...core.validate import validate_workcell
from ..base import AdapterError
from .signals import extract_signals


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _write_jsonl(path: Path, records: List[Dict]) -> None:
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records]
    path.write_text("\n".join(lines) + "\n")


def normalize(raw_dir: str, out_workcell_dir: str) -> Dict:
    raw = Path(raw_dir)
    if not raw.exists():
        raise AdapterError(f"raw dir not found: {raw_dir}")

    required = ["ci_log_01.txt", "repo_snapshot_manifest.json", "failing_tests.json"]
    for name in required:
        if not (raw / name).exists():
            raise AdapterError(f"missing required raw file: {name}")

    failing = _load_json(raw / "failing_tests.json")
    manifest = _load_json(raw / "repo_snapshot_manifest.json")

    out = Path(out_workcell_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts_dir = out / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    intent_dir = out / "intent_bundle" / "intent"
    intent_dir.mkdir(parents=True, exist_ok=True)

    # Copy raw artifacts
    artifact_map = {
        "ART-CI-LOG": "ci_log_01.txt",
        "ART-REPO-SNAPSHOT": "repo_snapshot_manifest.json",
        "ART-FAILING-TESTS": "failing_tests.json",
    }
    if (raw / "policy.json").exists():
        artifact_map["ART-POLICY"] = "policy.json"
    for artifact_id, filename in artifact_map.items():
        src = raw / filename
        if not src.exists():
            raise AdapterError(f"missing required raw file: {filename}")
        (artifacts_dir / filename).write_text(src.read_text())

    tests = failing.get("failing_tests", [])
    tickets: List[Dict] = []
    if tests:
        for idx, test_name in enumerate(tests, start=1):
            ticket_id = f"CI-{idx:03d}"
            tickets.append(
                {
                    "schema_version": "0.1",
                    "ticket_id": ticket_id,
                    "domain": "ci_change_control",
                    "priority": "MEDIUM",
                    "type": "fix_ci_failure",
                    "ticket_intent": f"Fix CI failure: {test_name}",
                    "inputs": {"artifact_refs": list(artifact_map.keys()), "failing_test": test_name},
                    "expected_outcome_ref": f"oracle://{ticket_id}",
                }
            )
    else:
        ticket_id = "CI-001"
        tickets.append(
            {
                "schema_version": "0.1",
                "ticket_id": ticket_id,
                "domain": "ci_change_control",
                "priority": "LOW",
                "type": "lint_fix",
                "ticket_intent": "Fix lint failures in CI",
                "inputs": {"artifact_refs": list(artifact_map.keys())},
                "expected_outcome_ref": f"oracle://{ticket_id}",
            }
        )

    ticket_ids = [t["ticket_id"] for t in tickets]
    signals = extract_signals(raw_dir, ticket_ids)

    artifact_index = {
        "schema_version": "0.1",
        "artifacts": [
            {"artifact_id": artifact_id, "path": f"artifacts/{filename}", "kind": "text"}
            for artifact_id, filename in artifact_map.items()
        ],
    }

    run_config = {
        "schema_version": "0.1",
        "domain": "ci_change_control",
        "mode": "shadow",
        "seed": 123,
        "intent_bundle_path": "./intent_bundle",
        "approval_policy": {
            "require_for_allow": True,
            "require_for_allow_with_mods": True,
            "ramped_auto_allow_risk_tiers": ["low"],
            "ramped_auto_allow_side_effects": ["none", "read"],
            "auto_reject_actions": [],
        },
    }

    intent_spec = {
        "intent_id": "ci_change_control",
        "intent_version": "1",
        "constraints": [
            {
                "id": "hard_deny_action_class",
                "effect": "deny",
                "applies_to_actions": ["phase.builder", "execute_sandbox_test", "deploy_verified_artifact"],
                "when": {
                    "op": "in",
                    "left": {"var": "signals.action.class"},
                    "right": {"var": "signals.policy.hard_deny_actions"},
                },
            },
            {
                "id": "core_path_patch",
                "effect": "escalate",
                "applies_to_actions": ["phase.builder"],
                "when": {
                    "op": "eq",
                    "left": {"var": "signals.action.class"},
                    "right": "core_path_patch",
                },
            },
            {
                "id": "forbidden_action_class",
                "effect": "escalate",
                "applies_to_actions": ["phase.builder", "execute_sandbox_test", "deploy_verified_artifact"],
                "when": {
                    "op": "in",
                    "left": {"var": "signals.action.class"},
                    "right": {"var": "signals.policy.forbidden_actions"},
                },
            }
        ],
        "escalation": {
            "kind": "policy_conflict",
            "channels": ["human_review"],
            "required_payload_fields": ["ticket_id", "action_id"],
        },
    }

    _write_jsonl(out / "tickets.jsonl", tickets)
    _write_json(out / "artifact_index.json", artifact_index)
    _write_jsonl(out / "signals.jsonl", signals)
    _write_json(out / "run_config.json", run_config)
    _write_json(intent_dir / "intent_spec.json", intent_spec)

    # Validate and hash
    validate_workcell(str(out))
    workcell_hash = compute_workcell_hash(str(out))

    return {
        "status": "OK",
        "domain": "ci_change_control",
        "raw": str(raw),
        "workcell": str(out),
        "tickets": len(tickets),
        "artifacts": len(artifact_index["artifacts"]),
        "signals": len(signals),
        "workcell_hash": workcell_hash,
    }
