import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def _matches(entry: Dict[str, Any], config: Dict[str, Any]) -> bool:
    if config.get("patchset_id") and entry.get("patchset_id") != config.get("patchset_id"):
        return False
    if config.get("ticket_id"):
        ticket_value = entry.get("ticket_id") or entry.get("ticket")
        if ticket_value != config.get("ticket_id"):
            return False
    if config.get("status") and entry.get("status") != config.get("status"):
        return False
    if config.get("approver"):
        if config.get("approver") not in entry.get("approvers", []):
            return False
    if config.get("risk_level") and entry.get("risk_level") != config.get("risk_level"):
        return False
    if config.get("since"):
        if not entry.get("timestamp"):
            return False
        if _parse_datetime(entry.get("timestamp")) < _parse_datetime(config.get("since")):
            return False
    if config.get("until"):
        if not entry.get("timestamp"):
            return False
        if _parse_datetime(entry.get("timestamp")) > _parse_datetime(config.get("until")):
            return False
    return True


def _render_md(entries: List[Dict[str, Any]]) -> str:
    lines = [
        "| timestamp | patchset_id | risk | approvers | status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        lines.append(
            f"| {entry.get('timestamp')} | {entry.get('patchset_id')} | {entry.get('risk_level')} | {', '.join(entry.get('approvers', []))} | {entry.get('status')} |"
        )
    return "\n".join(lines)


def _cache_meta(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(cache_path))
        cur = conn.execute(
            "SELECT source_index_sha256, source_entry_count, source_last_entry_hash FROM cache_meta LIMIT 1"
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"source_index_sha256": row[0], "source_entry_count": row[1], "source_last_entry_hash": row[2]}


def _index_meta(index_path: Path, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    import hashlib

    data = index_path.read_bytes() if index_path.exists() else b""
    return {
        "source_index_sha256": hashlib.sha256(data).hexdigest(),
        "source_entry_count": len(entries),
        "source_last_entry_hash": entries[-1].get("entry_hash") if entries else None,
    }


def _cache_up_to_date(cache_path: Path, index_path: Path, entries: List[Dict[str, Any]]) -> bool:
    meta = _cache_meta(cache_path)
    if not meta:
        return False
    index_meta = _index_meta(index_path, entries)
    return meta == index_meta


def _query_cache(cache_path: Path, config: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    conn = sqlite3.connect(str(cache_path))
    try:
        clauses = []
        params: List[Any] = []
        if config.get("patchset_id"):
            clauses.append("patchset_id = ?")
            params.append(config.get("patchset_id"))
        if config.get("ticket_id"):
            clauses.append("ticket_id = ?")
            params.append(config.get("ticket_id"))
        if config.get("risk_level"):
            clauses.append("risk_level = ?")
            params.append(config.get("risk_level"))
        if config.get("status"):
            clauses.append("status = ?")
            params.append(config.get("status"))
        if config.get("since"):
            clauses.append("timestamp >= ?")
            params.append(config.get("since"))
        if config.get("until"):
            clauses.append("timestamp <= ?")
            params.append(config.get("until"))

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            "SELECT line_no, timestamp, patchset_id, approval_id, risk_level, pipeline_name, verification_mode, status, "
            "review_packet_sha256, bundle_content_sha256, entry_hash, prev_entry_hash, signer_fingerprints_json, "
            "signature_count_required, signature_count_valid, approvers_json, ticket_id, ticket_id_status, ticket_event_id FROM evidence_runs "
            f"{where} ORDER BY (timestamp IS NULL), timestamp, line_no"
        )
        rows = conn.execute(query, params).fetchall()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    results: List[Dict[str, Any]] = []
    for row in rows:
        entry = {
            "line_no": row[0],
            "timestamp": row[1],
            "patchset_id": row[2],
            "approval_id": row[3],
            "risk_level": row[4],
            "pipeline_name": row[5],
            "verification_mode": row[6],
            "status": row[7],
            "review_packet_sha256": row[8],
            "bundle_content_sha256": row[9],
            "entry_hash": row[10],
            "prev_entry_hash": row[11],
            "signer_fingerprints": json.loads(row[12] or "[]"),
            "signature_count_required": row[13],
            "signature_count_valid": row[14],
            "approvers": json.loads(row[15] or "[]"),
            "ticket_id": row[16],
            "ticket_id_status": row[17],
            "ticket_event_id": row[18],
        }
        results.append(entry)
    if config.get("approver"):
        results = [entry for entry in results if config.get("approver") in entry.get("approvers", [])]
    return results


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    config = link_config.get("config", {}) if isinstance(link_config, dict) else {}
    index_path = project_root / "evidence" / "evidence_index.jsonl"
    entries = _load_index(index_path)
    cache_path = project_root / "evidence" / "cache" / "evidence_index_cache.sqlite"
    use_cache = not config.get("no_cache", False)

    filtered = None
    backend = "scan_jsonl"
    if use_cache and _cache_up_to_date(cache_path, index_path, entries):
        filtered = _query_cache(cache_path, config)
        if filtered is not None:
            backend = "cache_sqlite"
    if filtered is None:
        filtered = [entry for entry in entries if _matches(entry, config)]
        filtered = sorted(
            filtered,
            key=lambda e: (
                _parse_datetime(e["timestamp"]) if e.get("timestamp") else datetime.max,
                e.get("line_no", 0),
            ),
        )
        backend = "scan_jsonl"

    limit = config.get("limit")
    if isinstance(limit, int) and limit >= 0:
        filtered = filtered[:limit]

    payload = {
        "filters": config,
        "count": len(filtered),
        "query_backend": backend,
        "results": filtered,
    }

    json_path = sandbox.publish(
        "forgescaffold.evidence_query_results.json",
        "evidence_query_results.json",
        payload,
        schema="json",
    )
    md_path = sandbox.publish_text(
        "forgescaffold.evidence_query_results.md",
        "evidence_query_results.md",
        _render_md(filtered),
        schema="text",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {
            "forgescaffold.evidence_query_results.json": {"path": json_path},
            "forgescaffold.evidence_query_results.md": {"path": md_path},
        },
        "metrics": {"count": len(filtered)},
    }
