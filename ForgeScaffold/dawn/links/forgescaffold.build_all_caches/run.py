import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from index_utils import canonical_json, index_file_sha256, load_index, policy_snapshot_hash  # noqa: E402


def _load_policy(repo_root: Path) -> Dict[str, Any]:
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _latest_checkpoint(checkpoints_dir: Path) -> Optional[Path]:
    if not checkpoints_dir.exists():
        return None
    files = [p for p in checkpoints_dir.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]
    return sorted(files)[-1] if files else None


def _cache_meta(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    conn = sqlite3.connect(str(cache_path))
    try:
        cur = conn.execute(
            "SELECT schema_version, source_index_sha256, source_entry_count, source_last_entry_hash, "
            "checkpoint_last_entry_hash, checkpoint_path, checkpoint_timestamp, policy_snapshot_hash FROM cache_meta LIMIT 1"
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    if row[0] not in {"1.0.0", "1.0.1", "1.0.2"}:
        return None
    return {
        "schema_version": row[0],
        "source_index_sha256": row[1],
        "source_entry_count": row[2],
        "source_last_entry_hash": row[3],
        "checkpoint_last_entry_hash": row[4],
        "checkpoint_path": row[5],
        "checkpoint_timestamp": row[6],
        "policy_snapshot_hash": row[7],
    }


def _build_db(db_path: Path, entries: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE evidence_runs ("
            "line_no INTEGER PRIMARY KEY, "
            "timestamp TEXT, "
            "patchset_id TEXT, "
            "approval_id TEXT, "
            "risk_level TEXT, "
            "pipeline_name TEXT, "
            "verification_mode TEXT, "
            "status TEXT, "
            "review_packet_sha256 TEXT, "
            "bundle_content_sha256 TEXT, "
            "entry_hash TEXT, "
            "prev_entry_hash TEXT, "
            "signer_fingerprints_json TEXT, "
            "signature_count_required INTEGER, "
            "signature_count_valid INTEGER, "
            "approvers_json TEXT, "
            "ticket_id TEXT, "
            "ticket_id_status TEXT, "
            "ticket_event_id TEXT"
            ")"
        )
        conn.execute(
            "CREATE TABLE cache_meta ("
            "schema_version TEXT, "
            "built_at TEXT, "
            "source_index_sha256 TEXT, "
            "source_entry_count INTEGER, "
            "source_last_entry_hash TEXT, "
            "checkpoint_last_entry_hash TEXT, "
            "checkpoint_path TEXT, "
            "checkpoint_timestamp TEXT, "
            "policy_snapshot_hash TEXT"
            ")"
        )

        for idx, entry in enumerate(entries, start=1):
            approvers = entry.get("approvers", []) or []
            signer_fps = entry.get("signer_fingerprints", []) or []
            conn.execute(
                "INSERT INTO evidence_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    idx,
                    entry.get("timestamp"),
                    entry.get("patchset_id"),
                    entry.get("approval_id"),
                    entry.get("risk_level"),
                    entry.get("pipeline_name"),
                    entry.get("verification_mode"),
                    entry.get("status"),
                    entry.get("review_packet_sha256"),
                    entry.get("bundle_content_sha256"),
                    entry.get("entry_hash"),
                    entry.get("prev_entry_hash"),
                    json.dumps(signer_fps, sort_keys=True, separators=(",", ":")),
                    entry.get("signature_count_required"),
                    entry.get("signature_count_valid"),
                    json.dumps(approvers, sort_keys=True, separators=(",", ":")),
                    entry.get("ticket_id") or entry.get("ticket"),
                    entry.get("ticket_id_status"),
                    entry.get("ticket_event_id"),
                ),
            )

        conn.execute(
            "INSERT INTO cache_meta VALUES (?,?,?,?,?,?,?,?,?)",
            (
                meta.get("schema_version"),
                meta.get("built_at"),
                meta.get("source_index_sha256"),
                meta.get("source_entry_count"),
                meta.get("source_last_entry_hash"),
                meta.get("checkpoint_last_entry_hash"),
                meta.get("checkpoint_path"),
                meta.get("checkpoint_timestamp"),
                meta.get("policy_snapshot_hash"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    config = link_config.get("config", {}) if isinstance(link_config, dict) else {}
    force_rebuild = bool(config.get("force_rebuild", False))

    repo_root = Path(__file__).resolve().parents[3]
    catalog_path = Path(config.get("catalog_path") or (repo_root / "evidence" / "global" / "catalog.json"))
    catalog = json.loads(catalog_path.read_text())
    policy = _load_policy(repo_root)

    report_entries: List[Dict[str, Any]] = []

    for entry in catalog.get("projects", []):
        project = entry.get("project")
        index_path = Path(entry.get("index_path"))
        entries = load_index(index_path)
        index_sha = index_file_sha256(index_path)
        entry_count = len(entries)
        last_hash = entries[-1].get("entry_hash") if entries else None

        proj_root = repo_root / "projects" / project
        cache_path = proj_root / "evidence" / "cache" / "evidence_index_cache.sqlite"
        cache_meta = _cache_meta(cache_path)

        checkpoints_dir = proj_root / "evidence" / "checkpoints"
        checkpoint_last = None
        checkpoint_path_value = None
        checkpoint_timestamp = None
        if policy.get("forgescaffold", {}).get("index_integrity", {}).get("checkpoint_enabled", False):
            latest = _latest_checkpoint(checkpoints_dir)
            if latest:
                payload = json.loads(latest.read_text())
                checkpoint_last = payload.get("last_entry_hash")
                checkpoint_path_value = str(latest)
                checkpoint_timestamp = payload.get("created_at")

        policy_hash = policy_snapshot_hash(policy)
        built_at = entries[-1].get("timestamp") if entries else ""
        meta = {
            "schema_version": "1.0.2",
            "built_at": built_at,
            "source_index_sha256": index_sha,
            "source_entry_count": entry_count,
            "source_last_entry_hash": last_hash,
            "checkpoint_last_entry_hash": checkpoint_last,
            "checkpoint_path": checkpoint_path_value,
            "checkpoint_timestamp": checkpoint_timestamp,
            "policy_snapshot_hash": policy_hash,
        }

        cache_uptodate = False
        if cache_meta:
            cache_uptodate = (
                cache_meta.get("source_index_sha256") == index_sha
                and cache_meta.get("source_last_entry_hash") == last_hash
                and int(cache_meta.get("source_entry_count") or 0) == entry_count
                and cache_meta.get("policy_snapshot_hash") == policy_hash
            )

        if force_rebuild or not cache_uptodate:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(".tmp")
            _build_db(tmp_path, entries, meta)
            tmp_path.replace(cache_path)
            status = "BUILT"
            reason = "rebuild" if force_rebuild else "stale_or_missing"
        else:
            status = "SKIPPED"
            reason = "up_to_date"

        report_entries.append(
            {
                "project": project,
                "status": status,
                "reason": reason,
                "cache_path": str(cache_path),
                "cache_meta": meta,
            }
        )

    report = {
        "schema_version": "1.0.0",
        "projects": report_entries,
    }

    report_path = sandbox.publish(
        "forgescaffold.cache_batch_report.json",
        "evidence/global/cache_batch_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.cache_batch_report.json": {"path": report_path}},
        "metrics": {"projects": len(report_entries)},
    }
