import json
from pathlib import Path
from typing import Any, Dict, List


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def write_ticket_outcome(out_dir: Path, ticket_id: str, payload: Dict[str, Any]) -> Path:
    path = out_dir / "tickets" / f"{ticket_id}.json"
    _write_json(path, payload)
    return path


def write_run_summary(out_dir: Path, payload: Dict[str, Any]) -> Path:
    path = out_dir / "run_summary.json"
    _write_json(path, payload)
    return path


def write_ledger(out_dir: Path, entries: List[Dict[str, Any]]) -> Path:
    path = out_dir / "decision_ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, sort_keys=True, separators=(",", ":")) for entry in entries]
    path.write_text("\n".join(lines) + "\n")
    return path


def write_approvals(out_dir: Path, entries: List[Dict[str, Any]]) -> Path:
    path = out_dir / "approval_records.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(entry, sort_keys=True, separators=(",", ":")) for entry in entries]
    path.write_text("\n".join(lines) + "\n")
    return path
