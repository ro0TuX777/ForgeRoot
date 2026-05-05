import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_policy(repo_root: Path) -> Dict[str, Any]:
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _load_trusted_signers(repo_root: Path) -> List[Dict[str, Any]]:
    policy_path = repo_root / "dawn" / "policy" / "trusted_signers.yaml"
    if not policy_path.exists():
        return []
    payload = yaml.safe_load(policy_path.read_text()) or {}
    return payload.get("trusted_signers", []) or []


def _load_catalog(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _load_index(index_path: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not index_path.exists():
        return entries
    line_no = 0
    for line in index_path.read_text().splitlines():
        if line.strip():
            line_no += 1
            entry = json.loads(line)
            entry["line_no"] = line_no
            entries.append(entry)
    return entries


def _render_md(status: Dict[str, Any]) -> str:
    lines = [
        f"# Global Status",
        f"Projects: {status.get('projects_count')}",
        f"Cache coverage: {status.get('cache_coverage_percent')}%",
        "",
        "## Stale caches",
    ]
    stale = status.get("stale_caches", [])
    if not stale:
        lines.append("- None")
    else:
        for entry in stale:
            lines.append(f"- {entry.get('project')}: {entry.get('reason')}")
    lines.append("")
    lines.append("## Recent runs")
    for entry in status.get("recent_runs", [])[:10]:
        lines.append(f"- {entry.get('timestamp')} {entry.get('project')} {entry.get('status')}")
    return "\n".join(lines)


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    config = link_config.get("config", {}) if isinstance(link_config, dict) else {}
    repo_root = Path(__file__).resolve().parents[3]
    policy = _load_policy(repo_root)
    checkpoint_enabled = bool(
        policy.get("forgescaffold", {}).get("index_integrity", {}).get("checkpoint_enabled", False)
    )
    catalog_path = Path(config.get("catalog_path") or (repo_root / "evidence" / "global" / "catalog.json"))
    catalog = _load_catalog(catalog_path)

    built_at = catalog.get("built_at") or "1970-01-01T00:00:00Z"
    built_dt = _parse_datetime(built_at)

    projects = catalog.get("projects", [])
    projects_count = len(projects)
    cache_uptodate_count = sum(1 for entry in projects if entry.get("cache_uptodate"))
    cache_coverage = round((cache_uptodate_count / projects_count) * 100, 2) if projects_count else 0.0

    stale = []
    for entry in projects:
        if not entry.get("cache_uptodate"):
            stale.append({"project": entry.get("project"), "reason": "cache_stale_or_missing"})

    checkpoints = []
    for entry in projects:
        checkpoint_path = entry.get("latest_checkpoint_path")
        age_seconds = None
        if checkpoint_path and Path(checkpoint_path).exists():
            payload = json.loads(Path(checkpoint_path).read_text())
            created_at = payload.get("created_at")
            if created_at:
                try:
                    age_seconds = max(0, int((built_dt - _parse_datetime(created_at)).total_seconds()))
                except Exception:
                    age_seconds = None
        checkpoints.append(
            {
                "project": entry.get("project"),
                "checkpointing_enabled": checkpoint_enabled,
                "latest_checkpoint_path": checkpoint_path,
                "latest_checkpoint_age_seconds": age_seconds,
            }
        )

    trusted = _load_trusted_signers(repo_root)
    warnings: List[Dict[str, Any]] = []
    for signer in trusted:
        if signer.get("revoked"):
            warnings.append({"type": "revoked", "fingerprint": signer.get("fingerprint")})
        if signer.get("expires_at"):
            try:
                if _parse_datetime(str(signer.get("expires_at"))) < built_dt:
                    warnings.append({"type": "expired", "fingerprint": signer.get("fingerprint")})
            except Exception:
                warnings.append({"type": "expired", "fingerprint": signer.get("fingerprint")})
        scopes = signer.get("scopes") or {}
        projects_scope = scopes.get("projects")
        if projects_scope and "*" not in projects_scope:
            for entry in projects:
                if entry.get("project") not in projects_scope:
                    warnings.append(
                        {
                            "type": "scope_violation",
                            "fingerprint": signer.get("fingerprint"),
                            "project": entry.get("project"),
                        }
                    )

    recent_limit = int(config.get("recent_limit", 20))
    all_entries: List[Dict[str, Any]] = []
    for entry in projects:
        index_path = Path(entry.get("index_path"))
        rows = _load_index(index_path)
        for row in rows:
            row_with_project = dict(row)
            row_with_project["project"] = entry.get("project")
            all_entries.append(row_with_project)

    def _sort_key(entry: Dict[str, Any]) -> Tuple:
        ts = entry.get("timestamp")
        if ts:
            try:
                ts_val = _parse_datetime(ts)
            except Exception:
                ts_val = datetime.min
        else:
            ts_val = datetime.min
        return (-ts_val.timestamp(), entry.get("project", ""), entry.get("line_no", 0))

    recent_runs = sorted(all_entries, key=_sort_key)[:recent_limit]

    status = {
        "schema_version": "1.0.0",
        "built_at": built_at,
        "projects_count": projects_count,
        "cache_coverage_percent": cache_coverage,
        "stale_caches": stale,
        "checkpoints": checkpoints,
        "checkpointing_enabled": checkpoint_enabled,
        "trust_warnings": warnings,
        "recent_runs": recent_runs,
    }

    json_path = sandbox.publish(
        "forgescaffold.status_global.json",
        "evidence/global/status.json",
        status,
        schema="json",
    )
    md_path = sandbox.publish_text(
        "forgescaffold.status_global.md",
        "evidence/global/status.md",
        _render_md(status),
        schema="text",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.status_global.json": {"path": json_path},
            "forgescaffold.status_global.md": {"path": md_path},
        },
        "metrics": {"projects": projects_count},
    }
