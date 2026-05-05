# Tool Router Adapter

This is the framework-agnostic interception point for tool calls.

## Flow
1) Convert tool call → ProposedAction
2) Validate ProposedAction + Signals
3) Evaluate with ForgeGate
4) Enforce decision and record ledger entry

## Expected behavior
- ALLOW: execute tool
- ALLOW_WITH_MODS: apply overrides/caps, then execute
- ESCALATE/DENY: do not execute; return structured error

## Ledger
Write `decision_ledger_entry.v0_1.jsonl` entries for every tool call.

See `examples/tool_router_demo.py` for a runnable example.
