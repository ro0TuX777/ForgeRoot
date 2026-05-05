import pytest

from forgeworks.core.planner_contract import (
    PlannerContractValidationError,
    build_failure_receipt,
    build_planner_receipt,
    map_service_error_code,
    metrics_from_outputs,
    validate_planner_spec,
)


def _valid_spec() -> dict:
    return {
        "schema_version": "0.1",
        "spec_id": "spec-001",
        "request_id": "req-001",
        "goal": "Fix flaky CI tests in Domain A",
        "domain": "ci_change_control",
        "mode": "supervised",
        "source": {"source_path": "ingest/ci_change_control/batch_001"},
        "workcell": {"out_path": "packs/ci_change_control/planner_batch_001"},
        "run": {"out_path": "results/planner_batch_001"},
        "score": {
            "oracle_path": "packs/ci_change_control/planner_batch_001/oracle/expectations.jsonl",
            "scoring_path": "packs/ci_change_control/planner_batch_001/scoring/scoring.json",
        },
        "report": {"out_path": "results/planner_batch_001/report.md"},
        "loop_policy": {
            "max_iterations": 3,
            "target_score": 90.5,
            "require_zero_oracle_mismatch": True,
            "require_zero_deny": True,
            "max_no_progress_iters": 2,
        },
    }


def test_validate_planner_spec_ok():
    result = validate_planner_spec(_valid_spec())
    assert result["status"] == "OK"
    assert result["spec_id"] == "spec-001"
    assert result["domain"] == "ci_change_control"


def test_planner_spec_ci_generator_minimal():
    spec = _valid_spec()
    spec["source"] = {"generator": {"script_id": "generate_ci_batch", "args": {"count": 5}}}
    result = validate_planner_spec(spec)
    assert result["status"] == "OK"
    assert result["domain"] == "ci_change_control"


def test_planner_spec_itops_source_path_valid():
    spec = _valid_spec()
    spec["domain"] = "it_ops_runbook"
    spec["source"] = {"source_path": "ingest/it_ops_runbook/batch_001_happy"}
    result = validate_planner_spec(spec)
    assert result["status"] == "OK"
    assert result["domain"] == "it_ops_runbook"


def test_validate_planner_spec_unknown_field():
    spec = _valid_spec()
    spec["unexpected"] = "x"
    with pytest.raises(PlannerContractValidationError) as exc:
        validate_planner_spec(spec)
    assert exc.value.errors[0]["code"] == "UNKNOWN_SPEC_FIELD"


def test_map_service_error_code():
    assert map_service_error_code("INVALID_DOMAIN") == "UNSUPPORTED_DOMAIN"
    assert map_service_error_code("SCORE_FAILED") == "SCORE_FAILED"
    assert map_service_error_code("UNMAPPED_CODE") == "RESULT_READER_FAILED"


def test_build_planner_receipt_done():
    metrics = {
        "total_score": 95.5,
        "pass_fail": True,
        "deny_count": 0,
        "oracle_mismatch_count": 0,
        "escalation_count": 0,
        "drift_events_applied": 1,
    }
    receipt = build_planner_receipt(
        spec_id="spec-001",
        gates_passed=9,
        metrics=metrics,
        artifacts={"score_json": "results/x/score.json"},
        loop_policy={
            "target_score": 90,
            "require_zero_oracle_mismatch": True,
            "require_zero_deny": True,
        },
    )
    assert receipt["status"] == "DONE"
    assert receipt["failure_reason"] == "NONE"


def test_build_planner_receipt_replan_from_metrics():
    metrics = {
        "total_score": 70.0,
        "pass_fail": False,
        "deny_count": 0,
        "oracle_mismatch_count": 0,
        "escalation_count": 1,
        "drift_events_applied": 0,
    }
    receipt = build_planner_receipt(
        spec_id="spec-002",
        gates_passed=9,
        metrics=metrics,
        loop_policy={
            "target_score": 85,
            "require_zero_oracle_mismatch": True,
            "require_zero_deny": True,
        },
    )
    assert receipt["status"] == "REPLAN"
    assert receipt["failure_reason"] == "NONE"


def test_build_failure_receipt_maps_code():
    receipt = build_failure_receipt(
        spec_id="spec-003",
        gates_passed=2,
        service_error_code="INVALID_WORKCELL",
    )
    assert receipt["status"] == "REPLAN"
    assert receipt["failure_reason"] == "INVALID_WORKCELL"


def test_build_failure_receipt_stop_failed():
    receipt = build_failure_receipt(
        spec_id="spec-004",
        gates_passed=9,
        failure_reason="MAX_ITERATIONS_EXCEEDED",
    )
    assert receipt["status"] == "STOP_FAILED"
    assert receipt["failure_reason"] == "MAX_ITERATIONS_EXCEEDED"


def test_metrics_from_outputs():
    metrics = metrics_from_outputs(
        run_summary={"deny_count": 1, "escalation_count": 3, "drift_events_applied": [{"x": 1}, {"y": 2}]},
        score={"total_score": 88.2, "pass_fail": True, "oracle_mismatch_count": 2},
    )
    assert metrics["total_score"] == 88.2
    assert metrics["pass_fail"] is True
    assert metrics["deny_count"] == 1
    assert metrics["oracle_mismatch_count"] == 2
    assert metrics["escalation_count"] == 3
    assert metrics["drift_events_applied"] == 2
