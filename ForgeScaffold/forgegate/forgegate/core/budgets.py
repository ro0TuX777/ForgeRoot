from typing import Any, Dict, List, Optional


def evaluate_budgets(budgets_spec: List[Dict[str, Any]], budget_snapshot: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    snapshot = (budget_snapshot or {}).get("budgets", {}) if budget_snapshot else {}
    results: List[Dict[str, Any]] = []
    for budget in budgets_spec:
        bid = budget.get("id")
        limit = budget.get("limit")
        warning_threshold = budget.get("warning_threshold")
        expected_window = budget.get("window")
        entry = snapshot.get(bid, {})
        used = entry.get("used", entry.get("current"))
        window = entry.get("window")
        status = "ok"
        if used is None:
            status = "unknown"
        elif limit is not None and used > limit:
            status = "exceeded"
        elif warning_threshold is not None and used >= warning_threshold:
            status = "warning"

        window_ok = True
        if expected_window is not None and window is not None and expected_window != window:
            window_ok = False
            if status == "ok":
                status = "warning"

        results.append(
            {
                "id": bid,
                "used": used,
                "limit": limit,
                "status": status,
                "window": window or expected_window,
                "window_ok": window_ok,
            }
        )
    return results
