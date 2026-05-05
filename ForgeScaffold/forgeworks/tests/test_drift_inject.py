import pytest

from forgeworks.core.drift_inject import DriftPlanError, apply_drift_events, validate_drift_plan


def test_apply_drift_events_queue_pressure():
    plan = {
        "schema_version": "0.1",
        "domain": "ci_change_control",
        "events": [
            {"at_step": 1, "type": "queue_pressure_spike", "payload": {"pressure": 0.9, "fidelity": "D1"}},
        ],
    }
    validate_drift_plan(plan)
    signals = {"queue.pressure": 0.1, "echo.fidelity": "D4"}
    applied = apply_drift_events(plan["events"], 1, signals)
    assert applied
    assert signals["queue.pressure"] == 0.9
    assert signals["echo.fidelity"] == "D1"


def test_validate_drift_plan_metric_schema_requires_payload():
    plan = {
        "schema_version": "0.1",
        "domain": "it_ops_runbook",
        "events": [{"at_step": 1, "type": "metric_schema_change", "payload": {"old_key": "a"}}],
    }
    with pytest.raises(DriftPlanError):
        validate_drift_plan(plan)
