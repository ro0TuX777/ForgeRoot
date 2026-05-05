import json
from pathlib import Path

import pytest

from forgegate.core.evaluate import evaluate


SCENARIO_DIR = Path(__file__).parent / "scenarios"


def _get_path(payload, path):
    parts = path.split(".")
    cur = payload
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def _assert_must_include(record, must_include):
    if isinstance(must_include, list):
        for path in must_include:
            _get_path(record, path)
    elif isinstance(must_include, dict):
        for path, expected in must_include.items():
            value = _get_path(record, path)
            assert value == expected


def _load_scenario(path):
    return json.loads(path.read_text())


@pytest.mark.parametrize("scenario_path", sorted(SCENARIO_DIR.glob("*.json")))
def test_scenarios(scenario_path):
    scenario = _load_scenario(scenario_path)
    record1 = evaluate(
        scenario["intent"],
        scenario["proposed_action"],
        scenario["signals"],
        scenario.get("budget_snapshot"),
    )
    record2 = evaluate(
        scenario["intent"],
        scenario["proposed_action"],
        scenario["signals"],
        scenario.get("budget_snapshot"),
    )

    expected = scenario.get("expected", {})
    assert record1["decision"] == expected.get("decision")
    assert record1["decision_id"] == record2["decision_id"]
    assert record1["input_hash"] == record2["input_hash"]

    must_include = expected.get("must_include")
    if must_include:
        _assert_must_include(record1, must_include)
