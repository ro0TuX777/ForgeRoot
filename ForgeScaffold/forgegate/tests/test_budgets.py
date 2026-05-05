from forgegate.core.budgets import evaluate_budgets


def test_budget_window_warning():
    budgets_spec = [{"id": "cost", "limit": 100, "window": "day"}]
    snapshot = {"budgets": {"cost": {"used": 50, "window": "week"}}}
    results = evaluate_budgets(budgets_spec, snapshot)
    assert results[0]["status"] == "warning"
    assert results[0]["window_ok"] is False


def test_budget_exceeded():
    budgets_spec = [{"id": "cost", "limit": 100, "window": "day"}]
    snapshot = {"budgets": {"cost": {"used": 150, "window": "day"}}}
    results = evaluate_budgets(budgets_spec, snapshot)
    assert results[0]["status"] == "exceeded"
