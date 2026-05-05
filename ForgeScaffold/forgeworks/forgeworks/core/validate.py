import json
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import Draft202012Validator

from .hashutil import compute_workcell_hash
from .io import WorkcellIOError, ensure_exists, load_json, load_jsonl


class WorkcellValidationError(Exception):
    def __init__(self, errors: List[Dict[str, str]]) -> None:
        super().__init__("validation failed")
        self.errors = errors


def _load_schema(name: str) -> Dict[str, Any]:
    base = Path(__file__).resolve().parents[1] / "schemas"
    return json.loads((base / name).read_text())


def _validate_payload(payload: Dict[str, Any], schema_name: str, file_label: str, errors: List[Dict[str, str]]):
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    for err in validator.iter_errors(payload):
        loc = ".".join([str(p) for p in err.path])
        msg = f"{loc} {err.message}".strip()
        errors.append({"file": file_label, "error": msg})


def validate_workcell(workcell_path: str) -> Dict[str, Any]:
    base = Path(workcell_path)
    required = [
        base / "tickets.jsonl",
        base / "artifact_index.json",
        base / "signals.jsonl",
        base / "run_config.json",
    ]

    errors: List[Dict[str, str]] = []
    missing = ensure_exists(required)
    for msg in missing:
        errors.append({"file": "workcell", "error": msg})

    if errors:
        raise WorkcellValidationError(errors)

    try:
        tickets = load_jsonl(base / "tickets.jsonl")
        signals = load_jsonl(base / "signals.jsonl")
        artifact_index = load_json(base / "artifact_index.json")
        run_config = load_json(base / "run_config.json")
    except WorkcellIOError as exc:
        errors.append({"file": "workcell", "error": str(exc)})
        raise WorkcellValidationError(errors) from exc

    for idx, ticket in enumerate(tickets, start=1):
        _validate_payload(ticket, "ticket.v0_1.json", f"tickets.jsonl:{idx}", errors)
    for idx, signal in enumerate(signals, start=1):
        _validate_payload(signal, "signals.v0_1.json", f"signals.jsonl:{idx}", errors)

    _validate_payload(artifact_index, "artifact_index.v0_1.json", "artifact_index.json", errors)
    _validate_payload(run_config, "run_config.v0_1.json", "run_config.json", errors)

    if errors:
        raise WorkcellValidationError(errors)

    workcell_hash = compute_workcell_hash(workcell_path)

    return {
        "status": "OK",
        "workcell": str(base),
        "schemas_checked": ["ticket", "artifact_index", "signals", "run_config"],
        "workcell_hash": workcell_hash,
    }
