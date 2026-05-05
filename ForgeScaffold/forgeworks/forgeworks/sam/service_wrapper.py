from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional

from ..adapters.base import AdapterError, get_adapter
from ..adapters.registry import register_builtin_adapters
from ..core.planner_contract import (
    PlannerContractValidationError,
    artifacts_from_outputs,
    build_failure_receipt,
    build_planner_receipt,
    metrics_from_outputs,
    validate_planner_spec,
)
from ..core.validate import WorkcellValidationError, validate_workcell
from ..core.score import ScoreError, score_results
from ..core.report_md import generate_report
from ..core.summary import generate_summary
from ..runner.sam_like_runner import RunnerError, run_workcell
from ..core.review_bundle import assemble_review_bundle


@dataclass(frozen=True)
class ServiceError(Exception):
    code: str
    message: str
    stage: str
    details: Optional[Dict[str, Any]] = None


def _error(code: str, message: str, stage: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"status": "error", "error": {"code": code, "message": message, "stage": stage, "details": details or {}}}


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status": "ok", "payload": payload}


def ingest(domain: str, source_path: str, batch_id: Optional[str] = None, out_path: Optional[str] = None) -> Dict[str, Any]:
    register_builtin_adapters()
    try:
        adapter = get_adapter(domain)
        staged = out_path or f"ingest/{domain}/staged_{batch_id or 'batch'}"
        adapter.ingest(source_path, staged)
        return _ok({"domain": domain, "batch_id": batch_id, "staged_raw_path": staged})
    except AdapterError as exc:
        msg = str(exc)
        if "unsupported domain" in msg:
            return _error("INVALID_DOMAIN", msg, "ingest", {"domain": domain})
        if "missing required raw file" in msg:
            return _error("MISSING_REQUIRED_RAW_FILE", msg, "ingest", {"domain": domain})
        return _error("INGEST_FAILED", msg, "ingest", {"domain": domain})
    except Exception as exc:
        return _error("INGEST_FAILED", str(exc), "ingest", {"domain": domain})


def normalize(domain: str, staged_raw_path: str, out_path: Optional[str] = None) -> Dict[str, Any]:
    register_builtin_adapters()
    try:
        adapter = get_adapter(domain)
        out = out_path or f"packs/{domain}/normalized"
        result = adapter.normalize(staged_raw_path, out)
        return _ok(result)
    except AdapterError as exc:
        msg = str(exc)
        if "unsupported domain" in msg:
            return _error("INVALID_DOMAIN", msg, "normalize", {"domain": domain})
        if "missing required raw file" in msg:
            return _error("MISSING_REQUIRED_RAW_FILE", msg, "normalize", {"domain": domain})
        return _error("NORMALIZE_FAILED", msg, "normalize", {"domain": domain})
    except Exception as exc:
        return _error("NORMALIZE_FAILED", str(exc), "normalize", {"domain": domain})


def validate(workcell_path: str) -> Dict[str, Any]:
    try:
        result = validate_workcell(workcell_path)
        return _ok(result)
    except WorkcellValidationError as exc:
        return _error("INVALID_WORKCELL", "validation failed", "validate", {"errors": exc.errors})
    except Exception as exc:
        return _error("INVALID_WORKCELL", str(exc), "validate")


def run(workcell_path: str, mode: str, out_path: str, drift_plan_path: Optional[str] = None) -> Dict[str, Any]:
    try:
        summary = run_workcell(workcell_path, out_path, mode=mode, drift_plan_path=drift_plan_path)
        payload = {
            "workcell_path": workcell_path,
            "mode": mode,
            "results_path": out_path,
            "run_summary_path": str(Path(out_path) / "run_summary.json"),
            "ledger_path": summary.get("ledger_path"),
            "approval_records_path": summary.get("approval_records_path"),
            "ticket_count": summary.get("ticket_count"),
            "decision_count": summary.get("decision_count"),
            "approval_count": summary.get("approval_count"),
            "workcell_hash": summary.get("workcell_hash"),
        }
        return _ok(payload)
    except RunnerError as exc:
        return _error("RUN_FAILED", str(exc), "run", {"workcell_path": workcell_path})
    except Exception as exc:
        return _error("RUN_FAILED", str(exc), "run", {"workcell_path": workcell_path})


def score(results_path: str, oracle_path: str, scoring_path: str) -> Dict[str, Any]:
    try:
        result = score_results(results_path, oracle_path, scoring_path)
        payload = {
            "results_path": results_path,
            "score_path": str(Path(results_path) / "score.json"),
            "total_score": result.get("total_score"),
            "pass": result.get("pass_fail"),
            "penalty_count": result.get("penalty_count", 0),
        }
        return _ok(payload)
    except ScoreError as exc:
        return _error("SCORE_FAILED", str(exc), "score", {"results_path": results_path})
    except Exception as exc:
        return _error("SCORE_FAILED", str(exc), "score", {"results_path": results_path})


def report(results_path: str, score_path: str, out_path: str) -> Dict[str, Any]:
    try:
        report_path = generate_report(results_path, score_path, out_path)
        return _ok({"report_path": report_path})
    except Exception as exc:
        return _error("REPORT_FAILED", str(exc), "report", {"results_path": results_path})


def summary(results_root: str, out_path: str) -> Dict[str, Any]:
    try:
        summary_path = generate_summary(results_root, out_path)
        runs = len(list(Path(results_root).glob("*/run_summary.json")))
        return _ok({"summary_path": summary_path, "runs_summarized": runs})
    except Exception as exc:
        return _error("SUMMARY_FAILED", str(exc), "summary", {"results_root": results_root})


_GENERATOR_SCRIPT_BY_ID = {
    "generate_ci_batch": "scripts/generate_ci_batch.py",
    "generate_it_ops_batch": "scripts/generate_it_ops_batch.py",
}

_DOMAIN_BY_GENERATOR = {
    "generate_ci_batch": "ci_change_control",
    "generate_it_ops_batch": "it_ops_runbook",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _args_to_cli_flags(args: Dict[str, Any]) -> list[str]:
    flags: list[str] = []
    for key in sorted(args.keys()):
        if key == "out":
            continue
        value = args[key]
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            if value:
                flags.append(flag)
            continue
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                flags.extend([flag, str(item)])
            continue
        flags.extend([flag, str(value)])
    return flags


def _compile_source(spec: Dict[str, Any]) -> str:
    source = spec["source"]
    if "source_path" in source:
        source_path = source["source_path"]
        if not Path(source_path).exists():
            raise FileNotFoundError(f"source path not found: {source_path}")
        return source_path

    generator = source["generator"]
    script_id = generator["script_id"]
    expected_domain = _DOMAIN_BY_GENERATOR.get(script_id)
    if expected_domain and spec["domain"] != expected_domain:
        raise ValueError(
            f"generator '{script_id}' is incompatible with domain '{spec['domain']}' (expected '{expected_domain}')"
        )

    script_rel_path = _GENERATOR_SCRIPT_BY_ID[script_id]
    script_path = _repo_root() / script_rel_path
    if not script_path.exists():
        raise FileNotFoundError(f"generator script not found: {script_path}")

    args = generator.get("args", {})
    if not isinstance(args, dict):
        raise ValueError("generator args must be an object")
    out_path = args.get("out") or f"ingest/{spec['domain']}/planner_{spec['spec_id']}"
    cmd = [sys.executable, str(script_path), "--out", str(out_path)] + _args_to_cli_flags(args)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "generator failed"
        raise RuntimeError(detail)

    if not Path(out_path).exists():
        raise FileNotFoundError(f"generated source path not found: {out_path}")
    return str(out_path)


def _load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text())


def _is_same_or_child_path(candidate: str, root: str) -> bool:
    candidate_path = Path(candidate).resolve()
    root_path = Path(root).resolve()
    try:
        candidate_path.relative_to(root_path)
        return True
    except ValueError:
        return False


def _validate_planner_path_alignment(spec: Dict[str, Any]) -> Optional[str]:
    workcell_root = spec["workcell"]["out_path"]
    run_out = spec["run"]["out_path"]
    oracle_path = spec["score"]["oracle_path"]
    scoring_path = spec["score"]["scoring_path"]
    report_path = spec["report"]["out_path"]
    drift_plan_path = spec["run"].get("drift_plan_path")

    if not _is_same_or_child_path(run_out, workcell_root):
        return "run.out_path must be under workcell.out_path"
    if not _is_same_or_child_path(oracle_path, workcell_root):
        return "score.oracle_path must be under workcell.out_path"
    if not _is_same_or_child_path(scoring_path, workcell_root):
        return "score.scoring_path must be under workcell.out_path"
    if not _is_same_or_child_path(report_path, run_out):
        return "report.out_path must be under run.out_path"
    if drift_plan_path and not _is_same_or_child_path(drift_plan_path, workcell_root):
        return "run.drift_plan_path must be under workcell.out_path"
    return None


def execute_planner_request(raw_spec_json: Dict[str, Any]) -> Dict[str, Any]:
    spec_id = raw_spec_json.get("spec_id", "unknown-spec") if isinstance(raw_spec_json, dict) else "unknown-spec"
    gates_passed = 0

    # Accumulated pipeline payload snapshots — populated as each stage succeeds.
    # Used by _attach_bundle so partial failures still get a meaningful bundle.
    _run_summary_payload: Optional[Dict[str, Any]] = None
    _score_payload: Optional[Dict[str, Any]] = None

    def _attach_bundle(receipt: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
        """Assemble a ReviewBundle and embed it in the receipt dict in-place."""
        try:
            bundle = assemble_review_bundle(
                spec=spec,
                receipt=receipt,
                run_summary=_run_summary_payload,
                score_result=_score_payload,
            )
            receipt["review_bundle"] = bundle.to_dict()
        except Exception:  # never let bundle assembly break the receipt
            receipt["review_bundle"] = None
        return receipt

    try:
        validate_planner_spec(raw_spec_json)
    except PlannerContractValidationError as exc:
        failure_reason = exc.errors[0]["code"] if exc.errors else "INVALID_PLANNER_SPEC"
        receipt = build_failure_receipt(
            spec_id=spec_id,
            gates_passed=gates_passed,
            failure_reason=failure_reason,
        )
        # spec failed validation — use raw_spec_json as-is for best-effort bundle
        _attach_bundle(receipt, raw_spec_json if isinstance(raw_spec_json, dict) else {})
        return receipt

    spec = raw_spec_json
    gates_passed = 1

    alignment_error = _validate_planner_path_alignment(spec)
    if alignment_error:
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            failure_reason="INVALID_PLANNER_SPEC",
        )
        _attach_bundle(receipt, spec)
        return receipt

    try:
        source_path = _compile_source(spec)
    except FileNotFoundError:
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            failure_reason="MISSING_REQUIRED_RAW_FILE",
        )
        _attach_bundle(receipt, spec)
        return receipt
    except Exception:
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            failure_reason="SPEC_COMPILE_FAILED",
        )
        _attach_bundle(receipt, spec)
        return receipt

    gates_passed = 2
    ingest_result = ingest(spec["domain"], source_path, batch_id=spec["spec_id"])
    if ingest_result["status"] != "ok":
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            service_error_code=ingest_result.get("error", {}).get("code"),
        )
        _attach_bundle(receipt, spec)
        return receipt

    gates_passed = 3
    staged_raw_path = ingest_result["payload"]["staged_raw_path"]
    normalize_result = normalize(spec["domain"], staged_raw_path, out_path=spec["workcell"]["out_path"])
    if normalize_result["status"] != "ok":
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            service_error_code=normalize_result.get("error", {}).get("code"),
        )
        _attach_bundle(receipt, spec)
        return receipt

    gates_passed = 4
    workcell_path = normalize_result["payload"].get("workcell") or normalize_result["payload"].get("workcell_path")
    validate_result = validate(workcell_path)
    if validate_result["status"] != "ok":
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            service_error_code=validate_result.get("error", {}).get("code"),
        )
        _attach_bundle(receipt, spec)
        return receipt

    gates_passed = 5
    run_result = run(
        workcell_path=workcell_path,
        mode=spec["mode"],
        out_path=spec["run"]["out_path"],
        drift_plan_path=spec["run"].get("drift_plan_path"),
    )
    if run_result["status"] != "ok":
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            service_error_code=run_result.get("error", {}).get("code"),
        )
        _attach_bundle(receipt, spec)
        return receipt

    # Run succeeded — capture run_summary payload for bundle assembly.
    try:
        _run_summary_payload = _load_json(run_result["payload"]["run_summary_path"])
    except Exception:
        pass

    gates_passed = 6
    score_result = score(
        results_path=run_result["payload"]["results_path"],
        oracle_path=spec["score"]["oracle_path"],
        scoring_path=spec["score"]["scoring_path"],
    )
    if score_result["status"] != "ok":
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            service_error_code=score_result.get("error", {}).get("code"),
            artifacts=artifacts_from_outputs(
                run_summary_path=run_result["payload"].get("run_summary_path"),
                decision_ledger_path=run_result["payload"].get("ledger_path"),
            ),
        )
        _attach_bundle(receipt, spec)
        return receipt

    # Score succeeded — capture score payload for bundle assembly.
    try:
        _score_payload = _load_json(score_result["payload"]["score_path"])
    except Exception:
        pass

    gates_passed = 7
    report_result = report(
        results_path=run_result["payload"]["results_path"],
        score_path=score_result["payload"]["score_path"],
        out_path=spec["report"]["out_path"],
    )
    if report_result["status"] != "ok":
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            service_error_code=report_result.get("error", {}).get("code"),
            artifacts=artifacts_from_outputs(
                run_summary_path=run_result["payload"].get("run_summary_path"),
                decision_ledger_path=run_result["payload"].get("ledger_path"),
                score_json_path=score_result["payload"].get("score_path"),
            ),
        )
        _attach_bundle(receipt, spec)
        return receipt

    gates_passed = 8
    artifacts = artifacts_from_outputs(
        run_summary_path=run_result["payload"].get("run_summary_path"),
        decision_ledger_path=run_result["payload"].get("ledger_path"),
        score_json_path=score_result["payload"].get("score_path"),
        report_md_path=report_result["payload"].get("report_path"),
    )

    try:
        run_summary_payload = _load_json(run_result["payload"]["run_summary_path"])
        score_payload = _load_json(score_result["payload"]["score_path"])
        metrics = metrics_from_outputs(run_summary=run_summary_payload, score=score_payload)
        receipt = build_planner_receipt(
            spec_id=spec["spec_id"],
            gates_passed=9,
            metrics=metrics,
            artifacts=artifacts,
            loop_policy=spec["loop_policy"],
        )
        _attach_bundle(receipt, spec)
        return receipt
    except Exception:
        receipt = build_failure_receipt(
            spec_id=spec["spec_id"],
            gates_passed=gates_passed,
            failure_reason="RESULT_READER_FAILED",
            artifacts=artifacts,
        )
        _attach_bundle(receipt, spec)
        return receipt
