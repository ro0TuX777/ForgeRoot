import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List

REQUIRED_FILES = ["tickets.jsonl", "artifact_index.json", "signals.jsonl", "run_config.json"]


def _canonical_json(obj: Dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _canonical_jsonl(records: List[Dict]) -> str:
    lines = [_canonical_json(r) for r in records]
    return "\n".join(lines)


def _read_required(workcell_path: Path) -> Dict[str, str]:
    contents: Dict[str, str] = {}
    for name in REQUIRED_FILES:
        path = workcell_path / name
        if name.endswith(".jsonl"):
            raw_lines = path.read_text().splitlines()
            records = []
            for raw in raw_lines:
                if not raw.strip():
                    continue
                record = json.loads(raw)
                records.append(record)
            contents[name] = _canonical_jsonl(records)
        else:
            contents[name] = _canonical_json(json.loads(path.read_text()))
    return contents


def compute_workcell_hash(workcell_path: str) -> str:
    base = Path(workcell_path)
    contents = _read_required(base)
    hasher = hashlib.sha256()
    for name in REQUIRED_FILES:
        hasher.update(f"FILE:{name}\n".encode("utf-8"))
        hasher.update(contents[name].encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()
