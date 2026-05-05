import json
from pathlib import Path
from typing import Dict, List

from ...core.hashutil import compute_workcell_hash
from ...core.validate import validate_workcell
from ..base import AdapterError
from .signals import extract_signals


def _write_json(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _write_jsonl(path: Path, records: List[Dict]) -> None:
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records]
    path.write_text("\n".join(lines) + "\n")


def normalize(raw_dir: str, out_workcell_dir: str) -> Dict:
    raw = Path(raw_dir)
    if not raw.exists():
        raise AdapterError(f"raw dir not found: {raw_dir}")

    runbook_name = "runbook_service_health.md" if (raw / "runbook_service_health.md").exists() else "runbook_service_down.md"
    incident_name = "incident_log_001.txt" if (raw / "incident_log_001.txt").exists() else "incident_log_01.txt"
    required = [runbook_name, incident_name, "metrics_snapshot.json"]
    for name in required:
        if not (raw / name).exists():
            raise AdapterError(f"missing required raw file: {name}")

    out = Path(out_workcell_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifacts_dir = out / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    intent_dir = out / "intent_bundle" / "intent"
    intent_dir.mkdir(parents=True, exist_ok=True)

    artifact_map = {
        "ART-RUNBOOK": runbook_name,
        "ART-INCIDENT": incident_name,
        "ART-METRICS": "metrics_snapshot.json",
    }
    optional_artifacts = {
        "ART-SERVICE-CONTEXT": "service_context.json",
        "ART-POLICY": "policy.json",
        "ART-METADATA": "metadata.json",
    }
    for artifact_id, filename in optional_artifacts.items():
        if (raw / filename).exists():
            artifact_map[artifact_id] = filename

    for artifact_id, filename in artifact_map.items():
        src = raw / filename
        (artifacts_dir / filename).write_text(src.read_text())

    ticket_id = "OPS-001"
    ticket_type = "service_health_review" if runbook_name == "runbook_service_health.md" else "service_down"
    ticket_intent = (
        "Review service health signals and recommend safe next steps (no destructive actions)"
        if ticket_type == "service_health_review"
        else "Service down: follow runbook to restore service safely"
    )
    tickets = [
        {
            "schema_version": "0.1",
            "ticket_id": ticket_id,
            "domain": "it_ops_runbook",
            "priority": "HIGH",
            "type": ticket_type,
            "ticket_intent": ticket_intent,
            "inputs": {"artifact_refs": list(artifact_map.keys())},
            "expected_outcome_ref": f"oracle://{ticket_id}",
        }
    ]

    signals = extract_signals(raw_dir, [ticket_id])

    artifact_index = {
        "schema_version": "0.1",
        "artifacts": [
            {"artifact_id": artifact_id, "path": f"artifacts/{filename}", "kind": "text"}
            for artifact_id, filename in artifact_map.items()
        ],
    }

    run_config = {
        "schema_version": "0.1",
        "domain": "it_ops_runbook",
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
        "intent_id": "it_ops_runbook",
        "intent_version": "1",
    }

    _write_jsonl(out / "tickets.jsonl", tickets)
    _write_json(out / "artifact_index.json", artifact_index)
    _write_jsonl(out / "signals.jsonl", signals)
    _write_json(out / "run_config.json", run_config)
    _write_json(intent_dir / "intent_spec.json", intent_spec)

    validate_workcell(str(out))
    workcell_hash = compute_workcell_hash(str(out))

    return {
        "status": "OK",
        "domain": "it_ops_runbook",
        "raw": str(raw),
        "workcell": str(out),
        "tickets": len(tickets),
        "artifacts": len(artifact_index["artifacts"]),
        "signals": len(signals),
        "workcell_hash": workcell_hash,
    }
