import json
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional


def _sorted_counts(counter: Counter) -> List[Dict[str, Any]]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return [{"id": k, "count": v} for k, v in items]


def _escalation_key(entry: Dict[str, Any]) -> str:
    action_id = entry.get("action_id") or "unknown"
    profile = entry.get("actor_profile") or "unknown"
    return f"{action_id}::{profile}"


def compute_drift(ledger_entries: Iterable[Dict[str, Any]], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = config or {}
    esc_threshold = cfg.get("escalation_rate_threshold", 0.5)
    min_samples = cfg.get("min_samples", 3)
    missing_threshold = cfg.get("missing_signal_rate_threshold", 0.1)

    decision_counts = Counter()
    rule_counts = Counter()
    missing_signal_count = 0
    total = 0

    esc_counts = defaultdict(lambda: {"total": 0, "escalate": 0, "action_id": None, "actor_profile": None})

    for entry in ledger_entries:
        total += 1
        decision = entry.get("decision")
        decision_counts[decision] += 1

        record = entry.get("decision_record", {})
        reasons = record.get("reasons", {})
        for rule in reasons.get("triggered_rules", []) or []:
            rid = rule.get("id") or "unknown"
            rule_counts[rid] += 1
            if rid == "missing_signal" or rule.get("type") == "policy_conflict":
                missing_signal_count += 1

        key = _escalation_key(entry)
        esc_counts[key]["total"] += 1
        esc_counts[key]["action_id"] = entry.get("action_id") or "unknown"
        esc_counts[key]["actor_profile"] = entry.get("actor_profile") or "unknown"
        if decision == "ESCALATE":
            esc_counts[key]["escalate"] += 1

    escalation_rates = []
    for key in sorted(esc_counts.keys()):
        data = esc_counts[key]
        total_count = data["total"]
        rate = (data["escalate"] / total_count) if total_count else 0.0
        escalation_rates.append(
            {
                "action_id": data["action_id"],
                "actor_profile": data["actor_profile"],
                "total": total_count,
                "escalations": data["escalate"],
                "rate": rate,
            }
        )

    missing_rate = (missing_signal_count / total) if total else 0.0

    proxy_risk = []
    for row in escalation_rates:
        if row["total"] >= min_samples and row["rate"] >= esc_threshold:
            proxy_risk.append(
                {
                    "type": "high_escalation_rate",
                    "action_id": row["action_id"],
                    "actor_profile": row["actor_profile"],
                    "rate": row["rate"],
                }
            )
    if total and missing_rate >= missing_threshold:
        proxy_risk.append({"type": "missing_signal_rate", "rate": missing_rate})

    return {
        "total_entries": total,
        "decision_distribution": _sorted_counts(decision_counts),
        "top_triggered_rules": _sorted_counts(rule_counts),
        "escalation_rate_by_action_and_role": escalation_rates,
        "missing_signal_rate": missing_rate,
        "proxy_risk": proxy_risk,
        "config": {
            "escalation_rate_threshold": esc_threshold,
            "min_samples": min_samples,
            "missing_signal_rate_threshold": missing_threshold,
        },
    }


def load_ledger(path: str) -> List[Dict[str, Any]]:
    entries = []
    with open(path, "r") as fh:
        for line in fh:
            if not line.strip():
                continue
            entries.append(json.loads(line))
    return entries
