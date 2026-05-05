# ForgeGate v0.4 (Phase 4)

ForgeGate is a deterministic action-governance gate for multi-agent systems. Agents propose actions; ForgeGate decides (ALLOW / ALLOW_WITH_MODS / ESCALATE / DENY) using machine-readable signals and emits an auditable, replayable DecisionRecord.

## Quickstart (CLI)

```bash
# install optional crypto support for signing/verification
pip install -e '.[crypto]'

# evaluate a proposed action
forgegate evaluate --intent intent.json --action action.json --signals signals.json --budget budget.json

# validate an IntentBundle
forgegate validate-bundle ./IntentBundle
forgegate validate-bundle ./IntentBundle --strict
forgegate lint-intent ./IntentBundle --strict

# drift report from a decision ledger
forgegate drift-report --ledger path/to/ledger.jsonl --policy drift_policy.json

# replay / diff
forgegate replay --ledger path/to/ledger.jsonl --intent ./IntentBundle/intent/intent_spec.json
forgegate replay --ledger path/to/ledger.jsonl --intent-old old.json --intent-new new.json

# sign / verify
forgegate sign-bundle ./IntentBundle --key ./keys/ed25519_private.pem
forgegate verify-bundle ./IntentBundle --pubkey ./keys/ed25519_public.pem
forgegate sign-ledger ./ledger.jsonl --key ./keys/ed25519_private.pem --checkpoints ./checkpoints --every-n 100
forgegate verify-ledger ./ledger.jsonl --pubkey ./keys/ed25519_public.pem --checkpoints ./checkpoints

# registry management
forgegate registry add ./IntentBundle
forgegate registry list
forgegate registry promote my_intent@1
forgegate registry rollback my_intent@1
forgegate registry approve my_intent@1 --by \"Name\" --reason \"...\"
forgegate registry promote my_intent@2 --simulate-against ./ledger.jsonl --max-flips 0.01
```

Exit codes:
- 0 = ALLOW / ALLOW_WITH_MODS
- 10 = ESCALATE
- 20 = DENY

## Tests

```bash
cd forgegate
pip install -e '.[dev]'
pip install -e '.[crypto]'
python3 -m pytest -q

# or run the scenario harness directly
python3 tests/scenario_runner.py
```

## Integration guidance
- Intercept tool calls / actions before execution.
- Build a ProposedAction JSON from the agent’s intent.
- Build Signals from runtime telemetry (latency, cost, scope, risk, etc.).
- Run `forgegate evaluate` and enforce the DecisionRecord.

## Determinism contract
- Same `intent_version` + same canonical inputs => identical `decision`, `decision_id`, `input_hash`.
- Volatile fields (nonce, timestamps, run IDs) are stripped from ProposedAction before hashing.
- Evaluation is deterministic and non-LLM.

## Schemas
- `forgegate/schemas/proposed_action.v0_1.json`
- `forgegate/schemas/signals.v0_1.json`
- `forgegate/schemas/decision_record.v0_1.json`

## Docs
- `docs/runtime_flow.md`
- `docs/intent_bundle.md`
- `docs/integrity.md`
- `docs/tool_router.md`
- `docs/langgraph_adapter.md`
- `docs/triage_runbook.md`
