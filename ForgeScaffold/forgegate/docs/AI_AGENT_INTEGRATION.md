# ForgeGate AI Agent Integration Guide (v0.4.0)

This file is the single “brain pack” for another AI agent to understand ForgeGate and integrate it into a multi-agent system. ForgeGate is offline-first and framework-agnostic: do not assume any specific orchestrator.

If you are an agent, read this top to bottom before modifying or integrating ForgeGate.

---

## 1) What ForgeGate is (one paragraph)

ForgeGate is a deterministic action-governance gate. Agents propose actions, ForgeGate evaluates them against an IntentSpec plus Signals (and optional BudgetSnapshot), and emits a DecisionRecord: ALLOW / ALLOW_WITH_MODS / ESCALATE / DENY. It is deterministic and replay-safe: identical inputs must yield identical decisions and hashes. It is offline-first: no network required. It is built to sit exactly at the side-effect boundary.

**Core contract**  
`ProposedAction + Signals (+ BudgetSnapshot) -> DecisionRecord`

---

## 2) Mandatory integration point (side-effect boundary)

ForgeGate only “works” if you place it at the tool boundary where side effects occur.

Examples of side effects:
- File writes
- Subprocess execution
- Database writes
- Publishing to indexes
- Any external write or irreversible action

ASCII flow:

```
Agent
  |
  v
Tool Router / Adapter
  |
  | ProposedAction + Signals (+ BudgetSnapshot)
  v
ForgeGate.evaluate
  |
  +--> ALLOW / ALLOW_WITH_MODS -> execute tool
  +--> ESCALATE / DENY         -> block tool
  |
  v
Decision Ledger (JSONL)
```

---

## 3) What you must construct

### ProposedAction (required)
Minimal fields you should set:
- `action_id` (stable action name)
- `params` (action parameters; validate if possible)
- `side_effect` (none/read/write/external_write/irreversible)
- `risk_tier` (low/med/high/critical)
- `actor_id`, `actor_profile`, `autonomy` (who is acting + limits)
- `context_refs` (IDs/spans of evidence, not raw secrets)

Volatile fields (nonce, timestamps) are stripped before hashing.

### Signals (required)
Typed feature map used by policy rules.
- `values` map: key → value
- `provenance` optional (not hashed unless you add it)

Signals should be deterministic for a given state. Avoid system time unless passed as an explicit signal.

### BudgetSnapshot (optional)
Deterministic budget state. This is not derived from “now”; it must be passed in explicitly.

---

## 4) Decision semantics (non-negotiable)

ALLOW  
Execute the tool call as proposed.

ALLOW_WITH_MODS  
Execute, but apply param overrides/caps/required steps from `DecisionRecord.mods`.

ESCALATE  
Do **not** execute. Create a human-review payload from `DecisionRecord.escalation`.

DENY  
Do **not** execute. Record rule IDs that caused the deny.

**Fail-closed default**  
If a rule references a signal that is missing, ForgeGate defaults to ESCALATE (policy conflict / human judgment).

---

## 5) Determinism + replay contract (must preserve)

- `input_hash = sha256(canonical({proposed_action_clean, signals.values, budget_snapshot_clean?}))`
- `decision_id = sha256(intent_version:input_hash)`
- Canonical JSON must be stable (sorted keys, strict JSON, no NaN/Infinity).
- Volatile fields are removed before hashing.
- Decision must be purely deterministic (no clock, no randomness).

If you add inputs to hashing, document them.

---

## 6) Runtime APIs you should use

### Library evaluation
```
from forgegate.core.evaluate import evaluate

decision = evaluate(intent_spec, proposed_action, signals, budget_snapshot)
```

### CLI evaluation
```
forgegate evaluate --intent intent.json --action action.json --signals signals.json --budget budget.json
```

### Tool Router adapter (recommended)
Use `forgegate.adapters.tool_router.ToolRouter` to:
- register tools
- map tool calls to ProposedAction
- evaluate via ForgeGate
- enforce decisions
- append to ledger

---

## 7) IntentBundle + Registry (governance)

IntentBundle is the adoption unit. Minimum structure:
```
IntentBundle/
  catalogs/action_catalog.json
  catalogs/signal_catalog.json
  intent/intent_spec.json
  tests/scenarios/*.json
  meta.yaml
```

Validate:
```
forgegate validate-bundle ./IntentBundle
```

Registry (local, offline):
```
forgegate registry add ./IntentBundle
forgegate registry promote my_intent@1
forgegate registry rollback my_intent@1
```

---

## 8) Integrity (bundle signing)

Optional but strongly recommended for production:

```
pip install -e '.[crypto]'
forgegate sign-bundle ./IntentBundle --key ./keys/ed25519_private.pem
forgegate verify-bundle ./IntentBundle --pubkey ./keys/ed25519_public.pem
forgegate validate-bundle ./IntentBundle --require-signature --pubkey ./keys/ed25519_public.pem
```

Signing excludes `signatures/` and transient files and uses a deterministic manifest.

---

## 9) Drift reporting (operational control)

Ledger: append DecisionRecords to JSONL. Then run:

```
forgegate drift-report --ledger path/to/ledger.jsonl --policy drift_policy.yaml
```

Exit codes:
- 0 = OK
- 2 = WARN threshold exceeded
- 3 = CRITICAL threshold exceeded

Use this in CI or scheduled checks.

---

## 10) Safety hardening you must not bypass

- Missing signals → ESCALATE by default.
- Redaction rules must be applied before writing the DecisionRecord or ledger.
- Payload limits must be enforced deterministically (oversize params/signals should block).

---

## 11) Example integration patterns (generic)

These are examples of *types* of systems, not a specific product:

### A) High-frequency sandbox execution
**Integration point:** tool boundary before file writes / subprocess runs.  
**Typical policy:** deny network-like calls; cap runtime; enforce path allowlists.

### B) Promotion to a stable codebase/index
**Integration point:** promotion boundary before writes to permanent storage.  
**Typical policy:** require verified evidence; escalate on low confidence; enforce provenance stamps.

### C) Ticket/state transitions
**Integration point:** before state changes are committed.  
**Typical policy:** deny closing without required evidence; escalate for high-risk transitions.

Do **not** hard-code for any one application. Map your system’s side effects to ProposedAction and Signals.

---

## 12) Files this agent should read (minimal pack)

- `README.md`
- `docs/runtime_flow.md`
- `docs/intent_bundle.md`
- `docs/integrity.md`
- `docs/tool_router.md`
- `docs/triage_runbook.md`
- `forgegate/core/evaluate.py`
- `forgegate/core/expr.py`
- `forgegate/core/canonicalize.py`
- `forgegate/core/hashing.py`
- `forgegate/adapters/tool_router.py`
- `forgegate/cli/main.py`

---

## 13) Don’ts (common mistakes)

- Don’t call ForgeGate *after* executing the tool.
- Don’t use non-deterministic signals (timestamps) unless you include them explicitly as inputs.
- Don’t log sensitive params before applying redaction.
- Don’t bypass the DecisionRecord when applying ALLOW_WITH_MODS.
- Don’t assume registry promotion is safe without validate-bundle and (optionally) signature verification.
- Don’t put string DSL in `when`; ForgeGate `when` must be JSON AST (use `contains`/`has_substr` for substring checks).
- Don’t use unknown top-level keys like `rules`; use `constraints`, `boundaries`, `budgets`, `tradeoffs`, `shaping`.

---

## 14) Quick integration checklist

1) Identify side-effect boundaries (file, process, DB, publish).  
2) Define action_id list (Action Catalog).  
3) Define signals (Signal Catalog).  
4) Build IntentSpec constraints/boundaries/budgets/tradeoffs.  
5) Write scenarios to lock behavior.  
6) Integrate Tool Router at boundaries.  
7) Enable ledger + drift report.  
8) Optionally sign bundles and require signature in validation/promotion.

---

If you follow this, you will integrate ForgeGate safely and deterministically across any multi-agent system without coupling to a specific orchestrator.
