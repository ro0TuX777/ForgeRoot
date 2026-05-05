import json
from pathlib import Path
from typing import Dict, List, Optional

from .canonicalize import canonical_json
from .signing import sha256_hex


def compute_entry_hash(entry: Dict[str, object]) -> str:
    return sha256_hex(canonical_json(entry).encode("utf-8"))


def load_entries(path: str) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    with open(path, "r") as fh:
        for line in fh:
            if not line.strip():
                continue
            entries.append(json.loads(line))
    return entries


def compute_ledger_hash(path: str) -> str:
    data = Path(path).read_bytes()
    return sha256_hex(data)


def compute_last_entry_hash(path: str) -> Optional[str]:
    entries = load_entries(path)
    if not entries:
        return None
    return compute_entry_hash(entries[-1])


def write_checkpoint(checkpoints_dir: Path, last_entry_hash: str, entry_count: int) -> Path:
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(checkpoints_dir.glob("checkpoint_*.json"))
    prior_hash = None
    if existing:
        prior_hash = sha256_hex(existing[-1].read_bytes())
    payload = {
        "schema_version": "0.1",
        "last_entry_hash": last_entry_hash,
        "entry_count": entry_count,
        "prior_checkpoint_hash": prior_hash,
    }
    name = f"checkpoint_{entry_count}.json"
    path = checkpoints_dir / name
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return path
