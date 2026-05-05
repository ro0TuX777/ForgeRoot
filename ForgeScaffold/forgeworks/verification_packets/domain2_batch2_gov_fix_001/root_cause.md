# Root cause analysis — Domain 2 batch 2 governance path

**Finding:** Expected escalation did not occur. Ledger showed only ALLOW decisions.

**Root cause layer:** intent/policy (intent spec missing governance constraints).

**Evidence:**
- Signals include `action.is_destructive=true`, `env=prod`, `blast_radius=high` (see `packs/it_ops_runbook/test_batch_002_gov/signals.jsonl`).
- Oracle expects escalation for OPS-001.
- Intent spec for this batch had no constraints; ForgeGate therefore had no rule to trigger escalation.

**Fix applied:** Added explicit constraint in `intent_bundle/intent/intent_spec.json` to escalate when:
- `signals.action.is_destructive == true` OR
- `signals.env == "prod"` OR
- `signals.blast_radius == "high"`

**Result:** Rerun produces ESCALATE as expected; expected-vs-actual mismatch resolved.
