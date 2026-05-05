import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .hashutil import compute_workcell_hash


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _score_total(score_path: Path) -> Optional[float]:
    if not score_path.exists():
        return None
    try:
        score = _load_json(score_path)
        return float(score.get("total_score")) if score.get("total_score") is not None else None
    except Exception:
        return None


def _check_score_thresholds(score: Optional[float], expected: Dict[str, Any]) -> Optional[str]:
    if score is None:
        return "missing_score"
    min_score = expected.get("score_min")
    max_score = expected.get("score_max")
    if min_score is not None and score < float(min_score):
        return "score_below_min"
    if max_score is not None and score > float(max_score):
        return "score_above_max"
    return None


def regression_check(manifest_path: str) -> Dict[str, Any]:
    manifest = _load_json(Path(manifest_path))
    batches = manifest.get("batches", [])
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for batch in batches:
        name = batch.get("name", "unnamed")
        workcell_path = Path(batch["workcell_path"])
        results_path = Path(batch["results_path"])
        expected = batch.get("expected", {})

        computed: Dict[str, Any] = {
            "workcell_hash": compute_workcell_hash(str(workcell_path)),
            "ledger_sha256": _sha256_path(results_path / "decision_ledger.jsonl"),
            "approvals_sha256": None,
            "score_total": _score_total(results_path / "score.json"),
        }
        approvals_path = results_path / "approval_records.jsonl"
        if approvals_path.exists():
            computed["approvals_sha256"] = _sha256_path(approvals_path)

        status = "ok"
        error_codes: List[str] = []

        if expected.get("workcell_hash") and computed["workcell_hash"] != expected["workcell_hash"]:
            status = "fail"
            error_codes.append("workcell_hash_mismatch")
        if expected.get("ledger_sha256") and computed["ledger_sha256"] != expected["ledger_sha256"]:
            status = "fail"
            error_codes.append("ledger_hash_mismatch")
        if expected.get("approvals_sha256") and computed["approvals_sha256"] != expected["approvals_sha256"]:
            status = "fail"
            error_codes.append("approvals_hash_mismatch")

        score_error = _check_score_thresholds(computed["score_total"], expected)
        if score_error:
            status = "fail"
            error_codes.append(score_error)

        result = {
            "name": name,
            "workcell_path": str(workcell_path),
            "results_path": str(results_path),
            "status": status,
            "expected": expected,
            "computed": computed,
            "error_codes": error_codes,
        }
        results.append(result)
        if status != "ok":
            failures.append(result)

    summary = {
        "schema_version": "0.1",
        "manifest_path": str(manifest_path),
        "checked": len(results),
        "failed": len(failures),
        "status": "ok" if not failures else "fail",
        "results": results,
    }
    return summary
