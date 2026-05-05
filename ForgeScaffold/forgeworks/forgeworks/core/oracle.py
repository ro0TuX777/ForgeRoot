import json
from pathlib import Path
from typing import Dict, List


class OracleError(Exception):
    pass


def load_oracle(path: str) -> List[Dict]:
    oracle_path = Path(path)
    if not oracle_path.exists():
        raise OracleError(f"oracle not found: {path}")
    records: List[Dict] = []
    for idx, raw in enumerate(oracle_path.read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except Exception as exc:
            raise OracleError(f"invalid oracle jsonl line {idx}") from exc
        records.append(record)
    return records


def oracle_by_ticket(records: List[Dict]) -> Dict[str, Dict]:
    mapping: Dict[str, Dict] = {}
    for rec in records:
        ticket_id = rec.get("ticket_id")
        if ticket_id:
            mapping[ticket_id] = rec
    return mapping
