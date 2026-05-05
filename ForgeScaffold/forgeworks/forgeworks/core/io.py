import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


class WorkcellIOError(Exception):
    pass


def read_text(path: Path) -> str:
    try:
        return path.read_text()
    except Exception as exc:
        raise WorkcellIOError(f"failed to read {path}") from exc


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(read_text(path))
    except Exception as exc:
        raise WorkcellIOError(f"invalid json: {path}") from exc


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for idx, raw in enumerate(read_text(path).splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except Exception as exc:
            raise WorkcellIOError(f"invalid jsonl: {path} line {idx}") from exc
        if not isinstance(record, dict):
            raise WorkcellIOError(f"invalid jsonl: {path} line {idx} not an object")
        records.append(record)
    return records


def ensure_exists(paths: Iterable[Path]) -> List[str]:
    errors: List[str] = []
    for path in paths:
        if not path.exists():
            errors.append(f"missing file: {path.name}")
    return errors
