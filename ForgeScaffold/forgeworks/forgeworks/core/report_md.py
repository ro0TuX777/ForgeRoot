import json
from pathlib import Path
from typing import Any, Dict, List


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def generate_report(results_dir: str, score_json: str, out_path: str) -> str:
    base = Path(results_dir)
    summary = _load_json(base / "run_summary.json")
    score = _load_json(Path(score_json))
    ticket_dir = base / "tickets"
    tickets = sorted(ticket_dir.glob("*.json"))

    lines: List[str] = []
    lines.append("# ForgeWorks Run Report")
    lines.append("")
    lines.append(f"Workcell: {summary['workcell_path']}")
    lines.append(f"Mode: {summary['mode']}")
    lines.append(f"Workcell hash: {summary['workcell_hash']}")
    lines.append(f"Tickets: {summary['ticket_count']}")
    lines.append(f"Decisions: {summary['decision_count']}")
    if summary.get("approval_count") is not None:
        lines.append(f"Approvals: {summary['approval_count']}")
    if summary.get("escalation_count") is not None:
        lines.append(f"Escalations: {summary['escalation_count']}")
    if summary.get("deny_count") is not None:
        lines.append(f"Denies: {summary['deny_count']}")
    if summary.get("oracle_mismatch_count") is not None:
        lines.append(f"Oracle mismatches: {summary['oracle_mismatch_count']}")
    lines.append("")
    lines.append("## Scores")
    lines.append(f"Total: {score['total_score']} (pass={score['pass_fail']})")
    lines.append("- Correctness: " + str(score["correctness_score"]))
    lines.append("- Safety: " + str(score["safety_score"]))
    lines.append("- Governance: " + str(score["governance_score"]))
    lines.append("- Efficiency: " + str(score["efficiency_score"]))
    if score.get("penalty_count") is not None:
        lines.append("- Penalty count: " + str(score["penalty_count"]))
    if score["penalties_applied"]:
        lines.append("- Penalties: " + ", ".join(score["penalties_applied"]))

    drift_events = summary.get("drift_events_applied", [])
    lines.append("")
    lines.append("## Drift events")
    if drift_events:
        for event in drift_events:
            lines.append(f"- step {event.get('at_step')}: {event.get('type')}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Tickets")
    lines.append("| Ticket | Domain | Decisions | Approvals | Final Status |")
    lines.append("|---|---|---|---|---|")
    for ticket_path in tickets:
        payload = _load_json(ticket_path)
        approvals = payload.get("approval_events", [])
        lines.append(
            f"| {payload.get('ticket_id')} | {payload.get('domain')} | {len(payload.get('decisions_received', []))} | {len(approvals)} | {payload.get('final_status')} |"
        )

    content = "\n".join(lines) + "\n"
    Path(out_path).write_text(content)
    return out_path
