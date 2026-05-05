import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_index(index_path: Path) -> List[Dict[str, Any]]:
    entries = []
    if not index_path.exists():
        return entries
    for line in index_path.read_text().splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    policy = _load_policy(project_root)
    retention = policy.get("forgescaffold", {}).get("retention", {})
    enabled = bool(retention.get("enabled", False))
    max_packs = retention.get("max_packs")
    max_days = retention.get("max_days")
    prune_mode = retention.get("prune_mode", "dry_run")

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    entries = _load_index(index_path)

    report = {
        "status": "SKIPPED_DISABLED" if not enabled else "READY",
        "enabled": enabled,
        "prune_mode": prune_mode,
        "candidates": [],
        "deleted": [],
    }

    if not enabled:
        report_path = sandbox.publish(
            "forgescaffold.prune_report.json",
            "prune_report.json",
            report,
            schema="json",
        )
        return {"status": "SUCCEEDED", "outputs": {"forgescaffold.prune_report.json": {"path": report_path}}}

    now = datetime.now(timezone.utc)
    candidates: Dict[str, Dict[str, Any]] = {}

    if max_days is not None:
        for entry in entries:
            ts = entry.get("timestamp")
            if not ts:
                continue
            if (now - _parse_datetime(ts)).days > int(max_days):
                path = entry.get("evidence_pack_path")
                if path:
                    candidates[path] = {"reason": "max_days", "entry": entry}

    if max_packs is not None:
        sorted_entries = [e for e in entries if e.get("timestamp")]
        sorted_entries.sort(key=lambda e: _parse_datetime(e.get("timestamp")))
        if len(sorted_entries) > int(max_packs):
            for entry in sorted_entries[: len(sorted_entries) - int(max_packs)]:
                path = entry.get("evidence_pack_path")
                if path:
                    candidates[path] = {"reason": "max_packs", "entry": entry}

    report["candidates"] = [
        {"path": path, "reason": meta["reason"], "patchset_id": meta["entry"].get("patchset_id")}
        for path, meta in candidates.items()
    ]

    if prune_mode == "delete":
        for path in list(candidates.keys()):
            target = Path(path)
            if target.exists():
                if target.is_dir():
                    for child in target.rglob("*"):
                        if child.is_file():
                            child.unlink()
                    for child in sorted(target.rglob("*"), reverse=True):
                        if child.is_dir():
                            child.rmdir()
                    target.rmdir()
                else:
                    target.unlink()
                report["deleted"].append(path)

    report["status"] = "DONE" if report["candidates"] else "NOOP"

    report_path = sandbox.publish(
        "forgescaffold.prune_report.json",
        "prune_report.json",
        report,
        schema="json",
    )

    return {"status": "SUCCEEDED", "outputs": {"forgescaffold.prune_report.json": {"path": report_path}}}
