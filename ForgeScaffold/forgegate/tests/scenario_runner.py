import json
import sys
from pathlib import Path

from forgegate.core.evaluate import evaluate


def get_path(payload, path):
    parts = path.split(".")
    cur = payload
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def main() -> int:
    base = Path(__file__).parent / "scenarios"
    scenarios = sorted(base.glob("*.json"))
    for path in scenarios:
        scenario = json.loads(path.read_text())
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
        if record1["decision"] != expected.get("decision"):
            print(f"{path.name}: decision mismatch", file=sys.stderr)
            return 1
        if record1["decision_id"] != record2["decision_id"] or record1["input_hash"] != record2["input_hash"]:
            print(f"{path.name}: determinism mismatch", file=sys.stderr)
            return 1
        must_include = expected.get("must_include")
        if isinstance(must_include, list):
            for key in must_include:
                get_path(record1, key)
        elif isinstance(must_include, dict):
            for key, expected_value in must_include.items():
                if get_path(record1, key) != expected_value:
                    raise AssertionError(f"{path.name}: {key} mismatch")
    print(f"Scenario runner complete: {len(scenarios)} scenarios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
