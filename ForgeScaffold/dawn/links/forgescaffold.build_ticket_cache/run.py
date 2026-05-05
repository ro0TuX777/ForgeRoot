import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from index_utils import canonical_json  # noqa: E402


def _load_events(events_path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not events_path.exists():
        return events
    for line in events_path.read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _index_sha(events_path: Path) -> str:
    data = events_path.read_bytes() if events_path.exists() else b""
    return _sha256_bytes(data)


def _cache_meta(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT schema_version, built_at, source_events_sha256, source_event_count, source_last_event_hash FROM cache_meta LIMIT 1"
    )
    row = cur.fetchone()
    if not row:
        return None
    if row[0] != "1.0.0":
        return None
    return {
        "schema_version": row[0],
        "built_at": row[1],
        "source_events_sha256": row[2],
        "source_event_count": row[3],
        "source_last_event_hash": row[4],
    }


def _build_db(db_path: Path, events: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE ticket_events ("
            "line_no INTEGER PRIMARY KEY, "
            "event_id TEXT, "
            "timestamp TEXT, "
            "ticket_id TEXT, "
            "event_type TEXT, "
            "actor TEXT, "
            "payload_json TEXT, "
            "prev_event_hash TEXT, "
            "event_hash TEXT"
            ")"
        )
        conn.execute(
            "CREATE TABLE cache_meta ("
            "schema_version TEXT, "
            "built_at TEXT, "
            "source_events_sha256 TEXT, "
            "source_event_count INTEGER, "
            "source_last_event_hash TEXT"
            ")"
        )

        for idx, event in enumerate(events, start=1):
            conn.execute(
                "INSERT INTO ticket_events VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    idx,
                    event.get("event_id"),
                    event.get("timestamp"),
                    event.get("ticket_id"),
                    event.get("event_type"),
                    event.get("actor"),
                    json.dumps(event.get("payload") or {}, sort_keys=True, separators=(",", ":")),
                    event.get("prev_event_hash"),
                    event.get("event_hash"),
                ),
            )

        conn.execute(
            "INSERT INTO cache_meta VALUES (?,?,?,?,?)",
            (
                meta.get("schema_version"),
                meta.get("built_at"),
                meta.get("source_events_sha256"),
                meta.get("source_event_count"),
                meta.get("source_last_event_hash"),
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

    events_path = project_root / "tickets" / "ticket_events.jsonl"
    events = _load_events(events_path)
    events_sha = _index_sha(events_path)
    event_count = len(events)
    last_hash = events[-1].get("event_hash") if events else None

    built_at = events[-1].get("timestamp") if events else ""
    meta = {
        "schema_version": "1.0.0",
        "built_at": built_at,
        "source_events_sha256": events_sha,
        "source_event_count": event_count,
        "source_last_event_hash": last_hash,
    }

    cache_dir = project_root / "tickets"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "ticket_ledger_cache.sqlite"

    if cache_path.exists():
        conn = sqlite3.connect(str(cache_path))
        try:
            existing = _cache_meta(conn)
        except sqlite3.Error:
            existing = None
        finally:
            conn.close()
        if existing and existing == meta:
            report = {
                "status": "SKIPPED_CACHE_UPTODATE",
                "cache_path": str(cache_path),
                "source_events_sha256": events_sha,
                "event_count": event_count,
                "last_event_hash": last_hash,
            }
            report_path = sandbox.publish(
                "forgescaffold.ticket_cache_build_report.json",
                "ticket_cache_build_report.json",
                report,
                schema="json",
            )
            return {
                "status": "SUCCEEDED",
                "outputs": {"forgescaffold.ticket_cache_build_report.json": {"path": report_path}},
                "metrics": {"cache_built": False, "reason": "up_to_date"},
            }

    _build_db(cache_path, events, meta)

    report = {
        "status": "BUILT",
        "cache_path": str(cache_path),
        "source_events_sha256": events_sha,
        "event_count": event_count,
        "last_event_hash": last_hash,
    }
    report_path = sandbox.publish(
        "forgescaffold.ticket_cache_build_report.json",
        "ticket_cache_build_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.ticket_cache_build_report.json": {"path": report_path}},
        "metrics": {"cache_built": True},
    }
