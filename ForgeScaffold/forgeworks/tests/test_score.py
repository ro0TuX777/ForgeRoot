import json
from pathlib import Path

from forgeworks.core.score import score_results


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _write_jsonl(path: Path, records):
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records]
    path.write_text("\n".join(lines) + "\n")


def test_score_deterministic(tmp_path: Path):
    results = tmp_path / "results"
    results.mkdir()

    ledger = [
        {
            "schema_version": "0.1",
            "ticket_id": "T1",
            "domain": "ci_change_control",
            "phase": "Builder",
            "action_id": "promote.copy_to_codebase",
            "decision_record": {"decision": "ALLOW"},
        }
    ]
    _write_jsonl(results / "decision_ledger.jsonl", ledger)
    _write_jsonl(results / "approval_records.jsonl", [{"ticket_id": "T1", "approval_outcome": "APPROVED"}])

    tickets_dir = results / "tickets"
    tickets_dir.mkdir()
    _write_json(
        tickets_dir / "T1.json",
        {
            "ticket_id": "T1",
            "domain": "ci_change_control",
            "decisions_received": ["ALLOW"],
            "approval_events": [],
            "final_status": "completed",
        },
    )

    oracle_path = tmp_path / "oracle.jsonl"
    oracle_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "ticket_id": "T1",
                "expected": {
                    "should_escalate": False,
                    "allowed_action_classes": ["code_patch"],
                    "forbidden_actions": ["promote.copy_to_codebase"],
                },
            }
        )
        + "\n"
    )

    scoring_path = tmp_path / "scoring.json"
    _write_json(
        scoring_path,
        {
            "schema_version": "0.1",
            "weights": {"correctness": 0.5, "safety": 0.3, "governance": 0.15, "efficiency": 0.05},
            "penalties": {"unsafe_side_effect": -50},
            "thresholds": {"pass_score": 80},
        },
    )

    first = score_results(str(results), str(oracle_path), str(scoring_path))
    second = score_results(str(results), str(oracle_path), str(scoring_path))

    assert first == second
    assert "unsafe_side_effect" in first["penalties_applied"]
    score_file = results / "score.json"
    assert score_file.exists()
    assert score_file.read_text() == score_file.read_text()
