import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

COMMON_DIR = Path(__file__).resolve().parents[1] / "forgescaffold_common"
import sys
sys.path.append(str(COMMON_DIR))

from ticket_utils import verify_event_chain  # noqa: E402


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


def run(project_context: Dict[str, Any], link_config: Dict[str, Any]) -> Dict[str, Any]:
    sandbox = project_context.get("sandbox")
    project_root = Path(project_context["project_root"])
    if not sandbox:
        raise RuntimeError("Sandbox missing")

    report = {
        "status": "PASS",
        "error_codes": [],
    }

    events_path = project_root / "tickets" / "ticket_events.jsonl"
    cache_path = project_root / "tickets" / "ticket_ledger_cache.sqlite"

    ok_chain, bad_line, error = verify_event_chain(events_path)
    if not ok_chain:
        report["status"] = "FAIL"
        report["error_codes"].append(error or "EVENT_HASH_MISMATCH")
        report["first_bad_line"] = bad_line

    events = _load_events(events_path)
    events_sha = _sha256_bytes(events_path.read_bytes() if events_path.exists() else b"")
    event_count = len(events)
    last_hash = events[-1].get("event_hash") if events else None

    if not cache_path.exists():
        report["status"] = "FAIL"
        report["error_codes"].append("CACHE_META_MISMATCH")
    else:
        conn = sqlite3.connect(str(cache_path))
        try:
            cur = conn.execute(
                "SELECT schema_version, source_events_sha256, source_event_count, source_last_event_hash FROM cache_meta LIMIT 1"
            )
            row = cur.fetchone()
            if not row or row[0] != "1.0.0":
                report["status"] = "FAIL"
                report["error_codes"].append("CACHE_META_MISMATCH")
            else:
                if row[1] != events_sha or int(row[2] or 0) != event_count or row[3] != last_hash:
                    report["status"] = "FAIL"
                    report["error_codes"].append("CACHE_META_MISMATCH")

                if events:
                    sample_lines = [1, len(events)] if len(events) > 1 else [1]
                    for line_no in dict.fromkeys(sample_lines):
                        event = events[line_no - 1]
                        cur2 = conn.execute(
                            "SELECT line_no, event_id, timestamp, ticket_id, event_type, actor, payload_json, prev_event_hash, event_hash FROM ticket_events WHERE line_no=?",
                            (line_no,),
                        )
                        row2 = cur2.fetchone()
                        if not row2:
                            report["status"] = "FAIL"
                            report["error_codes"].append("CACHE_ROW_MISMATCH")
                            continue
                        expected_payload = json.dumps(event.get("payload") or {}, sort_keys=True, separators=(",", ":"))
                        if (
                            row2[1] != event.get("event_id")
                            or row2[2] != event.get("timestamp")
                            or row2[3] != event.get("ticket_id")
                            or row2[4] != event.get("event_type")
                            or row2[5] != event.get("actor")
                            or row2[6] != expected_payload
                            or row2[7] != event.get("prev_event_hash")
                            or row2[8] != event.get("event_hash")
                        ):
                            report["status"] = "FAIL"
                            report["error_codes"].append("CACHE_ROW_MISMATCH")
        finally:
            conn.close()

    report_path = sandbox.publish(
        "forgescaffold.ticket_cache_integrity_report.json",
        "ticket_cache_integrity_report.json",
        report,
        schema="json",
    )

    return {
        "status": "SUCCEEDED",
        "outputs": {"forgescaffold.ticket_cache_integrity_report.json": {"path": report_path}},
        "metrics": {"errors": len(report.get("error_codes", []))},
    }
