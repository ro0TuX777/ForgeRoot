import json
from pathlib import Path

from forgeworks.core.summary import generate_summary


def _write_json(path: Path, payload):
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def test_generate_summary(tmp_path: Path):
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir()
    run_b.mkdir()

    _write_json(
        run_a / "run_summary.json",
        {
            "run_id": "run_a",
            "workcell_path": "./packs/ci_change_control/0.1.0",
            "mode": "shadow",
            "decision_count": 2,
            "approval_count": 0,
            "escalation_rate": 0.0,
            "drift_events_applied": [{"type": "queue_pressure_spike"}],
        },
    )
    _write_json(
        run_a / "score.json",
        {
            "schema_version": "0.1",
            "ticket_count": 1,
            "correctness_score": 90,
            "safety_score": 90,
            "governance_score": 90,
            "efficiency_score": 90,
            "penalties_applied": [],
            "total_score": 90,
            "pass_fail": True,
        },
    )

    _write_json(
        run_b / "run_summary.json",
        {
            "run_id": "run_b",
            "workcell_path": "./packs/it_ops_runbook/0.1.0",
            "mode": "ramped",
            "decision_count": 3,
            "approval_count": 2,
            "escalation_rate": 0.33,
            "drift_events_applied": [{"type": "tool_version_bump"}],
        },
    )
    _write_json(
        run_b / "score.json",
        {
            "schema_version": "0.1",
            "ticket_count": 1,
            "correctness_score": 80,
            "safety_score": 85,
            "governance_score": 85,
            "efficiency_score": 70,
            "penalties_applied": ["unsafe_side_effect"],
            "total_score": 70,
            "pass_fail": False,
        },
    )

    out_path = tmp_path / "summary.md"
    generate_summary(str(tmp_path), str(out_path))
    content = out_path.read_text()

    assert "# ForgeWorks Run Summary" in content
    assert "run_a" in content
    assert "run_b" in content
    assert "queue_pressure_spike" in content
