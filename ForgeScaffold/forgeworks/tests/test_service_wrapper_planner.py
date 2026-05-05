import json
from pathlib import Path

from forgeworks.sam import service_wrapper


def _spec(source_path: str) -> dict:
    workcell_root = "packs/ci_change_control/planner_batch_001"
    return {
        "schema_version": "0.1",
        "spec_id": "spec-001",
        "request_id": "req-001",
        "goal": "Fix flaky CI tests in Domain A",
        "domain": "ci_change_control",
        "mode": "shadow",
        "source": {"source_path": source_path},
        "workcell": {"out_path": workcell_root},
        "run": {"out_path": f"{workcell_root}/run"},
        "score": {
            "oracle_path": f"{workcell_root}/oracle/expectations.jsonl",
            "scoring_path": f"{workcell_root}/scoring/scoring.json",
        },
        "report": {"out_path": f"{workcell_root}/run/report.md"},
        "loop_policy": {
            "max_iterations": 3,
            "target_score": 90,
            "require_zero_oracle_mismatch": True,
            "require_zero_deny": True,
            "max_no_progress_iters": 2,
        },
    }


def test_execute_planner_request_invalid_spec():
    receipt = service_wrapper.execute_planner_request("not-an-object")  # type: ignore[arg-type]
    assert receipt["status"] == "REPLAN"
    assert receipt["failure_reason"] == "INVALID_PLANNER_SPEC"
    assert receipt["gates_passed"] == 0


def test_execute_planner_request_service_error_mapping(tmp_path: Path, monkeypatch):
    src = tmp_path / "raw"
    src.mkdir(parents=True)
    spec = _spec(str(src))

    monkeypatch.setattr(
        service_wrapper,
        "ingest",
        lambda *_args, **_kwargs: {
            "status": "error",
            "error": {"code": "INVALID_DOMAIN", "message": "bad", "stage": "ingest", "details": {}},
        },
    )

    receipt = service_wrapper.execute_planner_request(spec)
    assert receipt["status"] == "REPLAN"
    assert receipt["failure_reason"] == "UNSUPPORTED_DOMAIN"
    assert receipt["gates_passed"] == 2


def test_execute_planner_request_done(tmp_path: Path, monkeypatch):
    src = tmp_path / "raw"
    src.mkdir(parents=True)
    spec = _spec(str(src))

    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True)
    run_summary_path = results_dir / "run_summary.json"
    score_path = results_dir / "score.json"
    report_path = results_dir / "report.md"
    ledger_path = results_dir / "decision_ledger.jsonl"
    report_path.write_text("# report\n")
    ledger_path.write_text("{}\n")
    run_summary_path.write_text(
        json.dumps(
            {
                "deny_count": 0,
                "escalation_count": 0,
                "drift_events_applied": [],
            }
        )
    )
    score_path.write_text(
        json.dumps(
            {
                "total_score": 95.5,
                "pass_fail": True,
                "oracle_mismatch_count": 0,
            }
        )
    )

    workcell_root = tmp_path / "workcell"
    run_root = workcell_root / "run"
    monkeypatch.setitem(spec["workcell"], "out_path", str(workcell_root))
    monkeypatch.setitem(spec["run"], "out_path", str(run_root))
    monkeypatch.setitem(spec["report"], "out_path", str(run_root / "report.md"))
    monkeypatch.setitem(spec["score"], "oracle_path", str(workcell_root / "oracle" / "expectations.jsonl"))
    monkeypatch.setitem(spec["score"], "scoring_path", str(workcell_root / "scoring" / "scoring.json"))

    monkeypatch.setattr(
        service_wrapper,
        "ingest",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"staged_raw_path": "ingest/staged"}},
    )
    monkeypatch.setattr(
        service_wrapper,
        "normalize",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"workcell": "packs/ci_change_control/planner_batch_001"}},
    )
    monkeypatch.setattr(
        service_wrapper,
        "validate",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"workcell_hash": "abc"}},
    )
    monkeypatch.setattr(
        service_wrapper,
        "run",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "payload": {
                "results_path": str(results_dir),
                "run_summary_path": str(run_summary_path),
                "ledger_path": str(ledger_path),
            },
        },
    )
    monkeypatch.setattr(
        service_wrapper,
        "score",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "payload": {
                "score_path": str(score_path),
            },
        },
    )
    monkeypatch.setattr(
        service_wrapper,
        "report",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"report_path": str(report_path)}},
    )

    receipt = service_wrapper.execute_planner_request(spec)
    assert receipt["status"] == "DONE"
    assert receipt["failure_reason"] == "NONE"
    assert receipt["gates_passed"] == 9
    assert receipt["artifacts"]["decision_ledger"] == str(ledger_path)


def test_execute_planner_request_replan_due_policy(tmp_path: Path, monkeypatch):
    src = tmp_path / "raw"
    src.mkdir(parents=True)
    spec = _spec(str(src))

    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True)
    run_summary_path = results_dir / "run_summary.json"
    score_path = results_dir / "score.json"
    report_path = results_dir / "report.md"
    ledger_path = results_dir / "decision_ledger.jsonl"
    report_path.write_text("# report\n")
    ledger_path.write_text("{}\n")
    run_summary_path.write_text(
        json.dumps(
            {
                "deny_count": 1,
                "escalation_count": 0,
                "drift_events_applied": [],
            }
        )
    )
    score_path.write_text(
        json.dumps(
            {
                "total_score": 99.0,
                "pass_fail": True,
                "oracle_mismatch_count": 0,
            }
        )
    )

    workcell_root = tmp_path / "workcell"
    run_root = workcell_root / "run"
    monkeypatch.setitem(spec["workcell"], "out_path", str(workcell_root))
    monkeypatch.setitem(spec["run"], "out_path", str(run_root))
    monkeypatch.setitem(spec["report"], "out_path", str(run_root / "report.md"))
    monkeypatch.setitem(spec["score"], "oracle_path", str(workcell_root / "oracle" / "expectations.jsonl"))
    monkeypatch.setitem(spec["score"], "scoring_path", str(workcell_root / "scoring" / "scoring.json"))

    monkeypatch.setattr(
        service_wrapper,
        "ingest",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"staged_raw_path": "ingest/staged"}},
    )
    monkeypatch.setattr(
        service_wrapper,
        "normalize",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"workcell": "packs/ci_change_control/planner_batch_001"}},
    )
    monkeypatch.setattr(
        service_wrapper,
        "validate",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"workcell_hash": "abc"}},
    )
    monkeypatch.setattr(
        service_wrapper,
        "run",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "payload": {
                "results_path": str(results_dir),
                "run_summary_path": str(run_summary_path),
                "ledger_path": str(ledger_path),
            },
        },
    )
    monkeypatch.setattr(
        service_wrapper,
        "score",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"score_path": str(score_path)}},
    )
    monkeypatch.setattr(
        service_wrapper,
        "report",
        lambda *_args, **_kwargs: {"status": "ok", "payload": {"report_path": str(report_path)}},
    )

    receipt = service_wrapper.execute_planner_request(spec)
    assert receipt["status"] == "REPLAN"
    assert receipt["failure_reason"] == "NONE"
    assert receipt["gates_passed"] == 9


def test_execute_planner_request_invalid_path_alignment(tmp_path: Path):
    src = tmp_path / "raw"
    src.mkdir(parents=True)
    spec = _spec(str(src))
    spec["run"]["out_path"] = "results/not_under_workcell"

    receipt = service_wrapper.execute_planner_request(spec)
    assert receipt["status"] == "REPLAN"
    assert receipt["failure_reason"] == "INVALID_PLANNER_SPEC"
    assert receipt["gates_passed"] == 1
