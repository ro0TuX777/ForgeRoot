# LangGraph Adapter (reference)

## Goal
Intercept tool node execution, gate the action, and enforce the DecisionRecord.

## Pattern
- Wrap tool nodes with a gate check.
- Build ProposedAction from node name + inputs.
- Compute Signals from runtime context (cost, latency, policy flags).
- Call ForgeGate and enforce decision.

## Pseudocode
```
proposed_action = {
  "schema_version": "0.1",
  "action_id": node.name,
  "actor_id": agent_id,
  "params": node.inputs,
}

signals = {"schema_version": "0.1", "values": {...}}

record = forgegate.evaluate(intent_spec, proposed_action, signals, budget_snapshot)
if record.decision in {"ALLOW", "ALLOW_WITH_MODS"}:
    apply_mods_if_any(record)
    run_node()
else:
    block_and_escalate(record)
```
