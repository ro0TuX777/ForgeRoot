import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def _matches(entry: Dict[str, Any], config: Dict[str, Any]) -> bool:
    if config.get("patchset_id") and entry.get("patchset_id") != config.get("patchset_id"):
        return False
    if config.get("ticket_id"):
        ticket_value = entry.get("ticket_id") or entry.get("ticket")
        if ticket_value != config.get("ticket_id"):
            return False
    if config.get("approval_id") and entry.get("approval_id") != config.get("approval_id"):
        return False
    if config.get("risk_level") and entry.get("risk_level") != config.get("risk_level"):
        return False
    if config.get("status") and entry.get("status") != config.get("status"):
        return False
    if config.get("pipeline_name") and entry.get("pipeline_name") != config.get("pipeline_name"):
        return False
    if config.get("approver"):
        if config.get("approver") not in entry.get("approvers", []):
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
        if config.get("approval_id"):
            clauses.append("approval_id = ?")
            params.append(config.get("approval_id"))
        if config.get("risk_level"):
            clauses.append("risk_level = ?")
            params.append(config.get("risk_level"))
        if config.get("status"):
            clauses.append("status = ?")
            params.append(config.get("status"))
        if config.get("pipeline_name"):
            clauses.append("pipeline_name = ?")
            params.append(config.get("pipeline_name"))
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
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    config = link_config.get("config", {}) if isinstance(link_config, dict) else {}
    repo_root = Path(__file__).resolve().parents[3]
    catalog_path = Path(config.get("catalog_path") or (repo_root / "evidence" / "global" / "catalog.json"))
    catalog = _load_catalog(catalog_path)

    projects_filter = config.get("projects") or []
    query_projects = []
    for entry in catalog.get("projects", []):
        if projects_filter and entry.get("project") not in projects_filter:
            continue
        query_projects.append(entry)

    results: List[Dict[str, Any]] = []
    cache_projects: List[str] = []
    scan_projects: List[str] = []

    for entry in query_projects:
        project = entry.get("project")
        index_path = Path(entry.get("index_path"))
        cache_path = Path(entry.get("cache_path")) if entry.get("cache_path") else None
        rows = None
        if entry.get("cache_uptodate") and cache_path and cache_path.exists():
            rows = _query_cache(cache_path, config)
            if rows is not None:
                cache_projects.append(project)
        if rows is None:
            rows = _load_index(index_path)
            rows = [row for row in rows if _matches(row, config)]
            scan_projects.append(project)
        for row in rows:
            row_with_project = dict(row)
            row_with_project["project"] = project
            results.append(row_with_project)

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

    results = sorted(results, key=_sort_key)

    limit = config.get("limit")
    if isinstance(limit, int) and limit >= 0:
        results = results[:limit]

    payload = {
        "filters": config,
        "query_backend_summary": {
            "cache_sqlite_projects": sorted(cache_projects),
            "scan_jsonl_projects": sorted(scan_projects),
        },
        "count": len(results),
        "results": results,
    }

    json_path = sandbox.publish(
        "forgescaffold.evidence_global_query_results.json",
        "evidence_global_query_results.json",
        payload,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.evidence_global_query_results.json": {"path": json_path}},
        "metrics": {"count": len(results)},
    }
