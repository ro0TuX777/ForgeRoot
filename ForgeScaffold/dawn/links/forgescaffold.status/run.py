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


def _load_trusted_signers(project_root: Path) -> List[Dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        return []
    payload = yaml.safe_load(policy_path.read_text()) or {}
    return payload.get("trusted_signers", []) or []


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
    forgescaffold_policy = policy.get("forgescaffold", {})

    trusted_signers = _load_trusted_signers(project_root)
    signer_summary = []
    now = datetime.now(timezone.utc)
    for signer in trusted_signers:
        expired = False
        if signer.get("expires_at"):
            try:
                expired = _parse_datetime(str(signer.get("expires_at"))) < now
            except Exception:
                expired = True
        signer_summary.append({
            "fingerprint": signer.get("fingerprint"),
            "label": signer.get("label"),
            "revoked": bool(signer.get("revoked")),
            "expired": expired,
            "scopes": signer.get("scopes"),
        })

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    entries = _load_index(index_path)
    limit = int(link_config.get("config", {}).get("limit", 5))
    latest = sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)[:limit]

    lock_path = project_root / ".locks" / "forgescaffold_apply.lock"
    lock_status = {"present": lock_path.exists(), "path": str(lock_path)}
    if lock_path.exists():
        try:
            payload = json.loads(lock_path.read_text())
        except Exception:
            payload = None
        lock_status["payload"] = payload
        if payload and payload.get("started_at"):
            try:
                started = _parse_datetime(payload.get("started_at"))
                lock_status["age_minutes"] = (now - started).total_seconds() / 60.0
            except Exception:
                lock_status["age_minutes"] = None

    status = {
        "policy": {
            "risk_rules": forgescaffold_policy.get("risk_rules"),
            "min_signatures_by_risk": forgescaffold_policy.get("min_signatures_by_risk"),
            "retention": forgescaffold_policy.get("retention"),
            "lock_ttl_minutes": forgescaffold_policy.get("lock_ttl_minutes"),
        },
        "latest_runs": latest,
        "signers": signer_summary,
        "lock": lock_status,
    }

    json_path = sandbox.publish(
        "forgescaffold.status.json",
        "status.json",
        status,
        schema="json",
    )

    md_lines = [
        "# ForgeScaffold Status",
        "",
        f"- lock_present: {lock_status['present']}",
        f"- latest_runs: {len(latest)}",
        f"- signers: {len(signer_summary)}",
    ]
    md_path = sandbox.publish_text(
        "forgescaffold.status.md",
        "status.md",
        "\n".join(md_lines),
        schema="text",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.status.json": {"path": json_path},
            "forgescaffold.status.md": {"path": md_path},
        },
        "metrics": {"latest_runs": len(latest)},
    }
