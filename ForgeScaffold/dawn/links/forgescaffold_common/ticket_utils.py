import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from index_utils import canonical_json, sha256_text  # type: ignore


DEFAULT_REGEX = r"^FC-[0-9]+$"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_ticket_id(raw: Optional[str], allowed_regex: Optional[str] = None) -> str:
    if raw is None:
        raise ValueError("ticket_id missing")
    value = str(raw).strip()
    if not value:
        raise ValueError("ticket_id missing")
    upper = value.upper()
    match = re.match(r"^FC-([0-9]+)$", upper)
    if match:
        return f"FC-{match.group(1)}"
    regex = allowed_regex or DEFAULT_REGEX
    if re.match(regex, value):
        return value
    if re.match(regex, upper):
        return upper
    raise ValueError("ticket_id invalid")


def validate_ticket_ref(ticket_ref: Dict[str, Any], allowed_regex: Optional[str] = None) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(ticket_ref, dict):
        return False, ["ticket_ref must be object"]
    if "schema_version" not in ticket_ref:
        errors.append("schema_version missing")
    raw_id = ticket_ref.get("ticket_id")
    if raw_id is None:
        errors.append("ticket_id missing")
    else:
        try:
            normalize_ticket_id(raw_id, allowed_regex=allowed_regex)
        except ValueError:
            errors.append("ticket_id invalid")
    return len(errors) == 0, errors


def compute_event_hash(event: Dict[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    return sha256_text(canonical_json(payload))


def last_event_hash(events_path: Path) -> Optional[str]:
    if not events_path.exists():
        return None
    lines = events_path.read_text().splitlines()
    for line in reversed(lines):
        if line.strip():
            try:
                entry = json.loads(line)
                return entry.get("event_hash")
            except Exception:
                return None
    return None


def append_ticket_event(
    events_path: Path,
    ticket_id: str,
    event_type: str,
    actor: Optional[str],
    payload: Dict[str, Any],
    event_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    prev_hash = last_event_hash(events_path) or "GENESIS"
    event = {
        "event_id": event_id or uuid.uuid4().hex,
        "timestamp": timestamp or _now_iso(),
        "ticket_id": ticket_id,
        "event_type": event_type,
        "actor": actor,
        "payload": payload or {},
        "prev_event_hash": prev_hash,
    }
    event_hash = compute_event_hash(event)
    event["event_hash"] = event_hash
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a") as fh:
        fh.write(canonical_json(event) + "\n")
    return event


def verify_event_chain(events_path: Path) -> Tuple[bool, Optional[int], Optional[str]]:
    if not events_path.exists():
        return True, None, None
    prev_hash = "GENESIS"
    line_no = 0
    for line in events_path.read_text().splitlines():
        if not line.strip():
            continue
        line_no += 1
        entry = json.loads(line)
        if entry.get("prev_event_hash") != prev_hash:
            return False, line_no, "CHAIN_BREAK"
        expected = compute_event_hash(entry)
        if entry.get("event_hash") != expected:
            return False, line_no, "EVENT_HASH_MISMATCH"
        prev_hash = entry.get("event_hash")
    return True, None, None
