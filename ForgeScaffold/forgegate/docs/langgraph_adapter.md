# LangGraph Adapter (optional)

This guide shows how to wrap LangGraph tool nodes with ForgeGate.

## Pattern
- Before executing a tool node, construct ProposedAction.
- Populate Signals.values from runtime context.
- Call ForgeGate.evaluate and enforce the decision.

## Pseudocode
```
proposed_action = {
  "schema_version": "0.1",
  "action_id": node.name,
  "actor_id": actor_id,
  "params": node.inputs,
}

signals = {"schema_version": "0.1", "values": {...}}
record = evaluate(intent_spec, proposed_action, signals, budget_snapshot)
if record.decision in {"ALLOW", "ALLOW_WITH_MODS"}:
    apply_mods(record)
    run_node()
else:
    block_and_escalate(record)
```
