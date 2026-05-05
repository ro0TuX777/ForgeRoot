import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_entry_hash(entry: Dict[str, Any]) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    return sha256_text(canonical_json(payload))


def load_index(index_path: Path) -> List[Dict[str, Any]]:
    entries = []
    if not index_path.exists():
        return entries
    for line in index_path.read_text().splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def last_entry_hash(index_path: Path) -> Optional[str]:
    entries = load_index(index_path)
    if not entries:
        return None
    return entries[-1].get("entry_hash")


def policy_snapshot_hash(policy: Dict[str, Any]) -> str:
    forgescaffold = policy.get("forgescaffold", {}) if isinstance(policy, dict) else {}
    snapshot = {
        "risk_rules": forgescaffold.get("risk_rules"),
        "min_signatures_by_risk": forgescaffold.get("min_signatures_by_risk"),
        "retention": forgescaffold.get("retention"),
        "lock_ttl_minutes": forgescaffold.get("lock_ttl_minutes"),
        "index_integrity": forgescaffold.get("index_integrity"),
        "tickets": forgescaffold.get("tickets"),
        "global_catalog": forgescaffold.get("global_catalog"),
    }
    return sha256_text(canonical_json(snapshot))


def index_file_sha256(index_path: Path) -> str:
    data = index_path.read_bytes() if index_path.exists() else b""
    return hashlib.sha256(data).hexdigest()


def append_index_entry(index_path: Path, entry: Dict[str, Any]) -> Dict[str, Any]:
    prev_hash = last_entry_hash(index_path)
    entry["prev_entry_hash"] = prev_hash or "GENESIS"
    entry_hash = compute_entry_hash(entry)
    entry["entry_hash"] = entry_hash
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a") as fh:
        fh.write(canonical_json(entry) + "\n")
    return entry


def verify_index_chain(index_path: Path) -> Tuple[bool, Optional[int], Optional[str]]:
    if not index_path.exists():
        return True, None, None
    prev_hash = "GENESIS"
    line_no = 0
    for line in index_path.read_text().splitlines():
        if not line.strip():
            continue
        line_no += 1
        entry = json.loads(line)
        if entry.get("prev_entry_hash") != prev_hash:
            return False, line_no, "CHAIN_BREAK"
        expected = compute_entry_hash(entry)
        if entry.get("entry_hash") != expected:
            return False, line_no, "ENTRY_HASH_MISMATCH"
        prev_hash = entry.get("entry_hash")
    return True, None, None
