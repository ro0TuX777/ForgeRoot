import json
from pathlib import Path
from typing import Any, Dict, List


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not path.exists():
        return records
    for raw in path.read_text().splitlines():
        if not raw.strip():
            continue
        records.append(json.loads(raw))
    return records


def _escalation_rate(summary: Dict[str, Any], summary_path: Path) -> str:
    if "escalation_rate" in summary:
        return str(summary.get("escalation_rate"))
    ledger_path = summary_path.parent / "decision_ledger.jsonl"
    entries = _load_jsonl(ledger_path)
    if not entries:
        return ""
    escalations = len([e for e in entries if e.get("decision_record", {}).get("decision") == "ESCALATE"])
    return str(round(escalations / max(1, len(entries)), 4))


def _drift_summary(summary: Dict[str, Any]) -> str:
    events = summary.get("drift_events_applied", [])
    types = sorted({e.get("type") for e in events if e.get("type")})
    return ",".join(types)


def generate_summary(results_root: str, out_path: str) -> str:
    root = Path(results_root)
    runs = []
    for summary_path in sorted(root.glob("*/run_summary.json")):
        summary = _load_json(summary_path)
        score_path = summary_path.parent / "score.json"
        score = _load_json(score_path) if score_path.exists() else {}
        runs.append((summary, score, summary_path))

    lines: List[str] = []
    lines.append("# ForgeWorks Run Summary")
    lines.append("")
    lines.append("| Run | Workcell | Mode | Total Score | Pass | Penalties | Penalty Count | Oracle Mismatches | Denies | Escalation Rate | Approvals | Drift |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")

    for summary, score, summary_path in runs:
        penalties = ",".join(score.get("penalties_applied", [])) if score else ""
        penalty_count = score.get("penalty_count", "")
        oracle_mismatches = summary.get("oracle_mismatch_count", "")
        deny_count = summary.get("deny_count", "")
        approvals = summary.get("approval_count", 0)
        escalation_rate = _escalation_rate(summary, summary_path)
        drift = _drift_summary(summary)
        lines.append(
            f"| {summary.get('run_id')} | {summary.get('workcell_path')} | {summary.get('mode')} | {score.get('total_score', '')} | {score.get('pass_fail', '')} | {penalties} | {penalty_count} | {oracle_mismatches} | {deny_count} | {escalation_rate} | {approvals} | {drift} |"
        )

    content = "\n".join(lines) + "\n"
    Path(out_path).write_text(content)
    return out_path
