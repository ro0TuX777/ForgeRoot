import json
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .evaluate import evaluate


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as fh:
        return json.load(fh)


def _collect_triggered_rules(record: Dict[str, Any]) -> List[str]:
    reasons = record.get("reasons", {})
    rules = reasons.get("triggered_rules", []) or []
    ids = []
    for rule in rules:
        rid = rule.get("id") or "unknown"
        ids.append(rid)
    return ids


def replay_ledger(ledger_path: str, intent_path: str) -> Dict[str, Any]:
    intent = _load_json(intent_path)
    flips = []
    skipped = []
    total = 0
    evaluated = 0
    rule_counts = Counter()

    with open(ledger_path, "r") as fh:
        for idx, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            total += 1
            entry = json.loads(line)
            proposed_action = entry.get("proposed_action")
            signals = entry.get("signals")
            budget_snapshot = entry.get("budget_snapshot")
            original = entry.get("decision")
            if not proposed_action or not signals:
                skipped.append({"line": idx, "reason": "missing_action_or_signals"})
                continue
            evaluated += 1
            record = evaluate(intent, proposed_action, signals, budget_snapshot)
            new_decision = record.get("decision")
            if new_decision != original:
                flips.append(
                    {
                        "line": idx,
                        "action_id": entry.get("action_id"),
                        "actor_profile": entry.get("actor_profile"),
                        "from": original,
                        "to": new_decision,
                    }
                )
            for rid in _collect_triggered_rules(record):
                rule_counts[rid] += 1

    return {
        "status": "PASS",
        "total_entries": total,
        "evaluated_entries": evaluated,
        "skipped": skipped,
        "flip_count": len(flips),
        "flips": flips[:20],
        "top_rules": [{"id": k, "count": v} for k, v in rule_counts.most_common(20)],
    }


def replay_diff(ledger_path: str, intent_old_path: str, intent_new_path: str) -> Dict[str, Any]:
    intent_old = _load_json(intent_old_path)
    intent_new = _load_json(intent_new_path)
    flips = []
    skipped = []
    total = 0
    evaluated = 0
    rule_counts = Counter()
    direction_counts = Counter()

    with open(ledger_path, "r") as fh:
        for idx, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            total += 1
            entry = json.loads(line)
            proposed_action = entry.get("proposed_action")
            signals = entry.get("signals")
            budget_snapshot = entry.get("budget_snapshot")
            if not proposed_action or not signals:
                skipped.append({"line": idx, "reason": "missing_action_or_signals"})
                continue
            evaluated += 1
            old_record = evaluate(intent_old, proposed_action, signals, budget_snapshot)
            new_record = evaluate(intent_new, proposed_action, signals, budget_snapshot)
            if old_record.get("decision") != new_record.get("decision"):
                flips.append(
                    {
                        "line": idx,
                        "action_id": entry.get("action_id"),
                        "actor_profile": entry.get("actor_profile"),
                        "from": old_record.get("decision"),
                        "to": new_record.get("decision"),
                    }
                )
                direction_counts[f"{old_record.get('decision')}->{new_record.get('decision')}"] += 1
            for rid in _collect_triggered_rules(new_record):
                rule_counts[rid] += 1

    return {
        "status": "PASS",
        "total_entries": total,
        "evaluated_entries": evaluated,
        "skipped": skipped,
        "flip_count": len(flips),
        "flip_directions": [{"id": k, "count": v} for k, v in direction_counts.most_common()],
        "top_rules": [{"id": k, "count": v} for k, v in rule_counts.most_common(20)],
        "flips": flips[:20],
    }
