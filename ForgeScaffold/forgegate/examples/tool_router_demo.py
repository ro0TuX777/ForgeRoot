import json
from pathlib import Path

from forgegate.adapters.tool_router import ToolRouter, ToolSpec
from forgegate.core.drift import load_ledger, compute_drift


def file_write(params):
    base = Path("/tmp/forgegate_demo")
    base.mkdir(parents=True, exist_ok=True)
    target = base / params.get("name", "out.txt")
    target.write_text(params.get("content", ""))
    return {"path": str(target)}


def sqlite_write(params):
    return {"status": "ok", "db": params.get("db", ":memory:")}


def subprocess_run(params):
    cmd = params.get("cmd", [])
    if not cmd:
        return {"status": "noop"}
    return {"status": "ok", "cmd": cmd}


def main():
    bundle = Path(__file__).resolve().parents[1] / "intent_bundle_example"
    intent_spec = json.loads((bundle / "intent" / "intent_spec.json").read_text())

    router = ToolRouter(intent_spec=intent_spec)
    router.ledger_path = str(Path("/tmp/forgegate_demo_ledger.jsonl"))

    router.register_tool(
        ToolSpec("file_write", "write", "write", "high"),
        file_write,
    )
    router.register_tool(
        ToolSpec("sqlite_write", "write_db", "write", "med"),
        sqlite_write,
    )
    router.register_tool(
        ToolSpec("subprocess_run", "subprocess", "external_write", "critical"),
        subprocess_run,
    )

    actor = {"id": "agent", "profile": "dev"}

    # allow
    result1 = router.call_tool(
        "file_write",
        {"name": "ok.txt", "content": "hello"},
        actor,
        {"schema_version": "0.1", "values": {"env": "dev", "cost": 10}},
    )
    print("ALLOW:", result1.decision, result1.output)

    # allow with mods (cost tradeoff)
    result2 = router.call_tool(
        "file_write",
        {"name": "cap.txt", "content": "data", "max_tokens": 5000},
        actor,
        {"schema_version": "0.1", "values": {"env": "dev", "cost": 100}},
    )
    print("ALLOW_WITH_MODS:", result2.decision)

    # deny/escalate
    result3 = router.call_tool(
        "subprocess_run",
        {"cmd": ["rm", "-rf", "/"]},
        actor,
        {"schema_version": "0.1", "values": {"env": "prod", "cost": 10}},
    )
    print("BLOCKED:", result3.decision)

    ledger_entries = load_ledger(router.ledger_path)
    report = compute_drift(ledger_entries, {"min_samples": 1, "escalation_rate_threshold": 0.1})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
