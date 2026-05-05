import json
from pathlib import Path

from forgeworks.core.regression import regression_check
from forgeworks.core.hashutil import compute_workcell_hash


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _write_jsonl(path: Path, records: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records]
    path.write_text("\n".join(lines) + "\n")


def test_regression_check_ok_and_fail(tmp_path: Path) -> None:
    workcell = tmp_path / "workcell"
    _write_jsonl(workcell / "tickets.jsonl", [{"schema_version": "0.1", "ticket_id": "T-1"}])
    _write_json(workcell / "artifact_index.json", {"schema_version": "0.1", "artifacts": []})
    _write_jsonl(workcell / "signals.jsonl", [{"schema_version": "0.1", "ticket_id": "T-1", "values": {}}])
    _write_json(workcell / "run_config.json", {"schema_version": "0.1", "domain": "x", "mode": "shadow", "seed": 1, "intent_bundle_path": "./intent"})

    results = tmp_path / "results"
    _write_jsonl(results / "decision_ledger.jsonl", [{"schema_version": "0.1", "ticket_id": "T-1"}])
    _write_jsonl(results / "approval_records.jsonl", [])
    _write_json(results / "score.json", {"total_score": 90.0})

    manifest = {
        "schema_version": "0.1",
        "batches": [
            {
                "name": "test",
                "workcell_path": str(workcell),
                "results_path": str(results),
                "expected": {
                    "workcell_hash": compute_workcell_hash(str(workcell)),
                    "ledger_sha256": (results / "decision_ledger.jsonl").read_bytes().hex(),
                    "approvals_sha256": (results / "approval_records.jsonl").read_bytes().hex(),
                    "score_min": 80.0,
                },
            }
        ],
    }

    # Fix expected hashes to sha256
    import hashlib

    manifest["batches"][0]["expected"]["ledger_sha256"] = hashlib.sha256(
        (results / "decision_ledger.jsonl").read_bytes()
    ).hexdigest()
    manifest["batches"][0]["expected"]["approvals_sha256"] = hashlib.sha256(
        (results / "approval_records.jsonl").read_bytes()
    ).hexdigest()

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))

    ok = regression_check(str(manifest_path))
    assert ok["status"] == "ok"

    # Tamper ledger
    _write_jsonl(results / "decision_ledger.jsonl", [{"schema_version": "0.1", "ticket_id": "T-2"}])
    bad = regression_check(str(manifest_path))
    assert bad["status"] == "fail"
