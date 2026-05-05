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


def _load_policy(project_root: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    policy_path = repo_root / "dawn" / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        policy_path = project_root / "policy" / "runtime_policy.yaml"
    if not policy_path.exists():
        return {}
    return yaml.safe_load(policy_path.read_text()) or {}


def _resolve_checkpoint_dir(project_root: Path, index_policy: Dict[str, Any]) -> Path:
    root_value = index_policy.get("checkpoint_write_root", "evidence/checkpoints")
    path = Path(root_value)
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[3]
    if str(root_value).startswith("projects/"):
        return repo_root / path
    return project_root / path


def _latest_checkpoint(checkpoints_dir: Path) -> Optional[Path]:
    if not checkpoints_dir.exists():
        return None
    files = [p for p in checkpoints_dir.glob("checkpoint_*.json") if not p.name.endswith(".signature.json")]
    return sorted(files)[-1] if files else None


def _cache_meta_from_db(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT schema_version, built_at, source_index_sha256, source_entry_count, source_last_entry_hash, "
        "checkpoint_last_entry_hash, checkpoint_path, checkpoint_timestamp, policy_snapshot_hash "
        "FROM cache_meta LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        return None
    meta = {
        "schema_version": row[0],
        "built_at": row[1],
        "source_index_sha256": row[2],
        "source_entry_count": row[3],
        "source_last_entry_hash": row[4],
        "checkpoint_last_entry_hash": row[5],
        "checkpoint_path": row[6],
        "checkpoint_timestamp": row[7],
        "policy_snapshot_hash": row[8],
    }
    if meta.get("schema_version") not in {"1.0.1", "1.0.2"}:
        return None
    return meta


def _up_to_date(
    meta: Dict[str, Any],
    index_sha: str,
    entry_count: int,
    last_hash: Optional[str],
    policy_hash: str,
    checkpoint_hash: Optional[str],
    checkpoint_path: Optional[str],
    checkpoint_timestamp: Optional[str],
) -> bool:
    return (
        meta.get("source_index_sha256") == index_sha
        and int(meta.get("source_entry_count") or 0) == entry_count
        and meta.get("source_last_entry_hash") == last_hash
        and meta.get("policy_snapshot_hash") == policy_hash
        and meta.get("checkpoint_last_entry_hash") == checkpoint_hash
        and meta.get("checkpoint_path") == checkpoint_path
        and meta.get("checkpoint_timestamp") == checkpoint_timestamp
    )


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
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    index_path = project_root / "evidence" / "evidence_index.jsonl"
    entries = load_index(index_path)
    index_sha = index_file_sha256(index_path)
    entry_count = len(entries)
    last_hash = entries[-1].get("entry_hash") if entries else None

    policy = _load_policy(project_root)
    index_policy = policy.get("forgescaffold", {}).get("index_integrity", {})
    checkpoints_dir = _resolve_checkpoint_dir(project_root, index_policy)
    checkpoint_last = None
    checkpoint_policy_hash = None
    checkpoint_path_value = None
    checkpoint_timestamp = None
    if index_policy.get("checkpoint_enabled", False):
        checkpoint_path = _latest_checkpoint(checkpoints_dir)
        if checkpoint_path:
            checkpoint_payload = json.loads(checkpoint_path.read_text())
            checkpoint_last = checkpoint_payload.get("last_entry_hash")
            checkpoint_policy_hash = checkpoint_payload.get("policy_snapshot_hash")
            checkpoint_path_value = str(checkpoint_path)
            checkpoint_timestamp = checkpoint_payload.get("created_at")

    policy_hash = checkpoint_policy_hash or policy_snapshot_hash(policy)

    built_at = ""
    if entries:
        built_at = entries[-1].get("timestamp") or ""

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

    cache_dir = project_root / "evidence" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "evidence_index_cache.sqlite"

    if cache_path.exists():
        conn = sqlite3.connect(str(cache_path))
        try:
            existing = _cache_meta_from_db(conn)
        except sqlite3.Error:
            existing = None
        finally:
            conn.close()
        if existing and _up_to_date(
            existing,
            index_sha,
            entry_count,
            last_hash,
            policy_hash,
            checkpoint_last,
            checkpoint_path_value,
            checkpoint_timestamp,
        ):
            report = {
                "status": "SKIPPED_CACHE_UPTODATE",
                "cache_path": str(cache_path),
                "source_index_sha256": index_sha,
                "entry_count": entry_count,
                "last_entry_hash": last_hash,
                "checkpoint_last_entry_hash": checkpoint_last,
                "checkpoint_path": checkpoint_path_value,
                "checkpoint_timestamp": checkpoint_timestamp,
            }
            report_path = sandbox.publish(
                "forgescaffold.cache_build_report.json",
                "cache_build_report.json",
                report,
                schema="json",
            )
            return {
                "status": "SUCCEEDED",
                "outputs": {"forgescaffold.cache_build_report.json": {"path": report_path}},
                "metrics": {"cache_built": False, "reason": "up_to_date"},
            }

    tmp_path = cache_path.with_suffix(".tmp")
    _build_db(tmp_path, entries, meta)
    tmp_path.replace(cache_path)

    report = {
        "status": "BUILT",
        "cache_path": str(cache_path),
        "source_index_sha256": index_sha,
        "entry_count": entry_count,
        "last_entry_hash": last_hash,
        "checkpoint_last_entry_hash": checkpoint_last,
        "checkpoint_path": checkpoint_path_value,
        "checkpoint_timestamp": checkpoint_timestamp,
    }
    report_path = sandbox.publish(
        "forgescaffold.cache_build_report.json",
        "cache_build_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.evidence_index_cache.sqlite": {"path": str(cache_path)},
            "forgescaffold.cache_build_report.json": {"path": report_path},
        },
        "metrics": {"cache_built": True},
    }
