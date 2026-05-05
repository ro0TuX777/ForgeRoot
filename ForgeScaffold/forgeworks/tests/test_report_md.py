import json
from pathlib import Path

from forgeworks.core.report_md import generate_report


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def test_generate_report(tmp_path: Path):
    results = tmp_path / "results"
    results.mkdir()

    _write_json(
        results / "run_summary.json",
        {
            "run_id": "run1",
            "workcell_path": "./packs/ci_change_control/0.1.0",
            "mode": "shadow",
            "ticket_count": 1,
            "decision_count": 2,
            "approval_count": 0,
            "workcell_hash": "abc",
            "drift_events_applied": [{"at_step": 1, "type": "queue_pressure_spike"}],
        },
    )

    _write_json(
        results / "score.json",
        {
            "schema_version": "0.1",
            "ticket_count": 1,
            "correctness_score": 90,
            "safety_score": 100,
            "governance_score": 100,
            "efficiency_score": 80,
            "penalties_applied": [],
            "total_score": 92,
            "pass_fail": True,
        },
    )

    tickets_dir = results / "tickets"
    tickets_dir.mkdir()
    _write_json(
        tickets_dir / "T1.json",
        {
            "ticket_id": "T1",
            "domain": "ci_change_control",
            "decisions_received": ["ALLOW", "ALLOW"],
            "approval_events": [],
            "final_status": "completed",
        },
    )

    out_path = results / "report.md"
    generate_report(str(results), str(results / "score.json"), str(out_path))
    content = out_path.read_text()

    assert "# ForgeWorks Run Report" in content
    assert "## Scores" in content
    assert "## Drift events" in content
    assert "| Ticket | Domain |" in content
