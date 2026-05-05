import json
from pathlib import Path
from typing import Any, Dict, List


class DriftPlanError(Exception):
    pass


def load_drift_plan(path: str) -> Dict[str, Any]:
    drift_path = Path(path)
    if not drift_path.exists():
        raise DriftPlanError(f"drift plan not found: {path}")
    try:
        return json.loads(drift_path.read_text())
    except Exception as exc:
        raise DriftPlanError("invalid drift plan json") from exc


def validate_drift_plan(plan: Dict[str, Any]) -> None:
    if plan.get("schema_version") != "0.1":
        raise DriftPlanError("drift plan schema_version must be 0.1")
    events = plan.get("events")
    if not isinstance(events, list):
        raise DriftPlanError("drift plan events must be a list")
    for event in events:
        if "at_step" not in event or "type" not in event:
            raise DriftPlanError("drift event missing at_step or type")
        if not isinstance(event["at_step"], int):
            raise DriftPlanError("drift event at_step must be integer")
        if event["type"] == "metric_schema_change":
            payload = event.get("payload", {})
            if "renamed_key" not in payload:
                raise DriftPlanError("drift event type 'metric_schema_change' missing required payload field 'renamed_key'")


def apply_drift_events(
    events: List[Dict[str, Any]],
    step: int,
    signals_values: Dict[str, Any],
) -> List[Dict[str, Any]]:
    applied: List[Dict[str, Any]] = []
    for event in events:
        if event.get("at_step") != step:
            continue
        ev_type = event.get("type")
        payload = event.get("payload", {})
        if ev_type == "queue_pressure_spike":
            signals_values["queue.pressure"] = payload.get("pressure", signals_values.get("queue.pressure"))
            if "fidelity" in payload:
                signals_values["echo.fidelity"] = payload["fidelity"]
        elif ev_type == "tool_version_bump":
            signals_values["tool.version"] = payload.get("version", "v2")
        elif ev_type == "policy_change":
            signals_values["policy.version"] = payload.get("version", "v2")
        elif ev_type == "metric_schema_change":
            old_key = payload.get("old_key")
            new_key = payload.get("renamed_key")
            if old_key and old_key in signals_values:
                signals_values[new_key] = signals_values.pop(old_key)
        applied.append({"at_step": step, "type": ev_type, "payload": payload})
    return applied
