# MCP Router Adapter (reference)

## Goal
Intercept MCP tool calls, build a ProposedAction + Signals, run ForgeGate, and enforce the DecisionRecord.

## Steps
1) Before tool execution, create ProposedAction:
   - action_id = tool name
   - actor_id / actor_profile from session
   - params = tool arguments
2) Compute Signals:
   - values = latency, cost, risk, env, etc.
3) Call ForgeGate:
   - `forgegate evaluate --intent intent.json --action action.json --signals signals.json --budget budget.json`
4) Enforce decision:
   - ALLOW/ALLOW_WITH_MODS -> proceed (apply `mods`)
   - ESCALATE/DENY -> block and record DecisionRecord

## Notes
- The gate is deterministic; do not add non-deterministic fields to ProposedAction or BudgetSnapshot.
- Capture DecisionRecord to your audit log.
