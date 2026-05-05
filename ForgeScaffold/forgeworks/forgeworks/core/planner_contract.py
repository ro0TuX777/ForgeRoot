from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator


class PlannerContractValidationError(Exception):
    def __init__(self, errors: List[Dict[str, str]]) -> None:
        super().__init__("planner contract validation failed")
        self.errors = errors


PLANNER_SPEC_SCHEMA = "planner_spec.v0_1.json"
PLANNER_RECEIPT_SCHEMA = "planner_receipt.v0_1.json"

FAILURE_REASONS = {
    "INVALID_PLANNER_SPEC",
    "UNKNOWN_SPEC_FIELD",
    "UNSUPPORTED_DOMAIN",
    "MISSING_REQUIRED_RAW_FILE",
    "SPEC_COMPILE_FAILED",
    "INVALID_WORKCELL",
    "INVALID_INTENT_BUNDLE_PATH",
    "FORGEGATE_UNAVAILABLE",
    "MALFORMED_DRIFT_PLAN",
    "MALFORMED_ORACLE",
    "RUN_FAILED",
    "SCORE_FAILED",
    "REPORT_FAILED",
    "RESULT_READER_FAILED",
    "NO_PROGRESS_LIMIT_REACHED",
    "MAX_ITERATIONS_EXCEEDED",
    "NONE",
}

_SERVICE_ERROR_MAP = {
    "INVALID_DOMAIN": "UNSUPPORTED_DOMAIN",
    "MISSING_REQUIRED_RAW_FILE": "MISSING_REQUIRED_RAW_FILE",
    "INGEST_FAILED": "SPEC_COMPILE_FAILED",
    "NORMALIZE_FAILED": "SPEC_COMPILE_FAILED",
    "INVALID_WORKCELL": "INVALID_WORKCELL",
    "INVALID_INTENT_BUNDLE_PATH": "INVALID_INTENT_BUNDLE_PATH",
    "FORGEGATE_UNAVAILABLE": "FORGEGATE_UNAVAILABLE",
    "MALFORMED_DRIFT_PLAN": "MALFORMED_DRIFT_PLAN",
    "MALFORMED_ORACLE": "MALFORMED_ORACLE",
    "RUN_FAILED": "RUN_FAILED",
    "SCORE_FAILED": "SCORE_FAILED",
    "REPORT_FAILED": "REPORT_FAILED",
    "SUMMARY_FAILED": "RESULT_READER_FAILED",
}


def _schema_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas"


@lru_cache(maxsize=8)
def _load_schema(schema_name: str) -> Dict[str, Any]:
    schema_path = _schema_dir() / schema_name
    return json.loads(schema_path.read_text())


@lru_cache(maxsize=8)
def _validator_for(schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(_load_schema(schema_name))


def _format_path(error_path: List[Any]) -> str:
    if not error_path:
        return "$"
    return "$." + ".".join(str(part) for part in error_path)


def _collect_schema_errors(
    payload: Dict[str, Any],
    schema_name: str,
    default_code: str,
    unknown_field_code: Optional[str] = None,
) -> List[Dict[str, str]]:
    validator = _validator_for(schema_name)
    errors: List[Dict[str, str]] = []
    for err in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
        code = default_code
        if unknown_field_code and err.validator == "additionalProperties":
            code = unknown_field_code
        errors.append(
            {
                "code": code,
                "path": _format_path(list(err.path)),
                "message": err.message,
            }
        )
    return errors


def validate_planner_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        raise PlannerContractValidationError(
            [{"code": "INVALID_PLANNER_SPEC", "path": "$", "message": "planner spec must be an object"}]
        )

    errors = _collect_schema_errors(
        spec,
        PLANNER_SPEC_SCHEMA,
        default_code="INVALID_PLANNER_SPEC",
        unknown_field_code="UNKNOWN_SPEC_FIELD",
    )
    if errors:
        raise PlannerContractValidationError(errors)

    return {
        "status": "OK",
        "schema": PLANNER_SPEC_SCHEMA,
        "spec_id": spec["spec_id"],
        "request_id": spec["request_id"],
        "domain": spec["domain"],
        "mode": spec["mode"],
    }


def validate_planner_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(receipt, dict):
        raise PlannerContractValidationError(
            [{"code": "RESULT_READER_FAILED", "path": "$", "message": "planner receipt must be an object"}]
        )
    errors = _collect_schema_errors(
        receipt,
        PLANNER_RECEIPT_SCHEMA,
        default_code="RESULT_READER_FAILED",
        unknown_field_code="RESULT_READER_FAILED",
    )
    if errors:
        raise PlannerContractValidationError(errors)
    return {"status": "OK", "schema": PLANNER_RECEIPT_SCHEMA, "spec_id": receipt["spec_id"]}


def map_service_error_code(code: Optional[str]) -> str:
    if not code:
        return "NONE"
    return _SERVICE_ERROR_MAP.get(code, "RESULT_READER_FAILED")


def metrics_from_outputs(
    run_summary: Optional[Dict[str, Any]] = None,
    score: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    summary = run_summary or {}
    score_payload = score or {}
    drift_events = summary.get("drift_events_applied", [])
    drift_count = len(drift_events) if isinstance(drift_events, list) else 0
    return {
        "total_score": float(score_payload.get("total_score", 0.0)),
        "pass_fail": bool(score_payload.get("pass_fail", False)),
        "deny_count": int(summary.get("deny_count", 0)),
        "oracle_mismatch_count": int(
            score_payload.get("oracle_mismatch_count", summary.get("oracle_mismatch_count", 0))
        ),
        "escalation_count": int(summary.get("escalation_count", 0)),
        "drift_events_applied": int(drift_count),
    }


def artifacts_from_outputs(
    run_summary_path: Optional[str] = None,
    decision_ledger_path: Optional[str] = None,
    score_json_path: Optional[str] = None,
    report_md_path: Optional[str] = None,
) -> Dict[str, str]:
    artifacts: Dict[str, str] = {}
    if run_summary_path:
        artifacts["run_summary"] = run_summary_path
    if decision_ledger_path:
        artifacts["decision_ledger"] = decision_ledger_path
    if score_json_path:
        artifacts["score_json"] = score_json_path
    if report_md_path:
        artifacts["report_md"] = report_md_path
    return artifacts


def decide_receipt_status(
    loop_policy: Dict[str, Any],
    metrics: Dict[str, Any],
    failure_reason: str = "NONE",
    stop_failed: bool = False,
) -> str:
    if stop_failed or failure_reason in {"MAX_ITERATIONS_EXCEEDED", "NO_PROGRESS_LIMIT_REACHED"}:
        return "STOP_FAILED"

    if failure_reason != "NONE":
        return "REPLAN"

    target_score = float(loop_policy.get("target_score", 0.0))
    require_zero_oracle = bool(loop_policy.get("require_zero_oracle_mismatch", True))
    require_zero_deny = bool(loop_policy.get("require_zero_deny", True))

    if float(metrics.get("total_score", 0.0)) < target_score:
        return "REPLAN"
    if not bool(metrics.get("pass_fail", False)):
        return "REPLAN"
    if require_zero_oracle and int(metrics.get("oracle_mismatch_count", 0)) > 0:
        return "REPLAN"
    if require_zero_deny and int(metrics.get("deny_count", 0)) > 0:
        return "REPLAN"
    return "DONE"


def build_planner_receipt(
    spec_id: str,
    gates_passed: int,
    metrics: Optional[Dict[str, Any]] = None,
    artifacts: Optional[Dict[str, str]] = None,
    *,
    status: Optional[str] = None,
    failure_reason: str = "NONE",
    loop_policy: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None,
    stop_failed: bool = False,
) -> Dict[str, Any]:
    if failure_reason not in FAILURE_REASONS:
        raise ValueError(f"unsupported failure_reason: {failure_reason}")

    metrics_payload = metrics or metrics_from_outputs()
    artifacts_payload = artifacts or {}
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    if status is None:
        if loop_policy is None:
            raise ValueError("loop_policy is required when status is omitted")
        status = decide_receipt_status(
            loop_policy=loop_policy,
            metrics=metrics_payload,
            failure_reason=failure_reason,
            stop_failed=stop_failed,
        )

    receipt = {
        "schema_version": "0.1",
        "spec_id": spec_id,
        "timestamp": ts,
        "status": status,
        "failure_reason": failure_reason,
        "gates_passed": int(gates_passed),
        "metrics": metrics_payload,
        "artifacts": artifacts_payload,
    }

    validate_planner_receipt(receipt)
    return receipt


def build_failure_receipt(
    spec_id: str,
    gates_passed: int,
    *,
    service_error_code: Optional[str] = None,
    failure_reason: Optional[str] = None,
    timestamp: Optional[str] = None,
    stop_failed: bool = False,
    artifacts: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if failure_reason is None:
        failure_reason = map_service_error_code(service_error_code)
    status = "STOP_FAILED" if stop_failed or failure_reason in {"MAX_ITERATIONS_EXCEEDED", "NO_PROGRESS_LIMIT_REACHED"} else "REPLAN"
    return build_planner_receipt(
        spec_id=spec_id,
        gates_passed=gates_passed,
        metrics=metrics_from_outputs(),
        artifacts=artifacts or {},
        status=status,
        failure_reason=failure_reason,
        timestamp=timestamp,
    )
