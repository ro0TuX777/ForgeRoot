What ForgeGate is

ForgeGate is a deterministic action-governance gate for multi-agent systems.

Agents can be brilliant at proposing actions, but organizations need a universal enforcement point that answers:

Given an action proposal + current signals, is this allowed, allowed with modifications, escalated, or denied — and why?

ForgeGate standardizes that as a portable interface:

ProposedAction + Signals (+ optional BudgetSnapshot) → DecisionRecord

Why we’re building it

Enterprise agents fail most dangerously when they succeed at the wrong measurable proxy (speed/cost/closure) and degrade what matters (trust/retention/risk posture). ForgeGate is the missing intent enforcement layer.

What ForgeGate is NOT (Phase 1)

Not a full agent orchestrator

Not a retrieval/context stack

Not a business-domain product (support/procurement/etc.)

Not an LLM “policy decider” (LLM proposes; gate decides deterministically)

Key artifacts in scope

Schemas: ProposedAction v0.1, Signals v0.1, DecisionRecord v0.1

Canonical hashing: stable input_hash + decision_id (replay safety)

Reference gate: constraint/boundary/budget/tradeoff evaluation order

Scenario tests: intent unit tests + determinism tests

Docs: how to adopt in any orchestrator/tool stack

Do we need to reference DAWN?

Not as a dependency. ForgeGate should be deployable standalone.

But DAWN is a great optional execution substrate because it already provides:

Link contracts (link.yaml + run.py) and a standard way to package units of work. 

DEVELOPER_GUIDE

A required run.py signature that matches “pure work-in / artifact-out” patterns. 

DEVELOPER_GUIDE

An append-only JSONL ledger suitable for recording DecisionRecords and gate events. 

DEVELOPER_GUIDE

A defined ledger location + event schema you can reuse or mirror. 

DEVELOPER_GUIDE

Runtime policy/budget/security profiles (including an isolation mode restricting writes) that align with safe agentic execution. 

DEVELOPER_GUIDE

Deterministic orchestration mechanics (input signatures → skip/idempotency) that pair well with decision replay. 

DEVELOPER_GUIDE

Recommendation:

Phase 1: Build ForgeGate as a standalone library + CLI.

Optional adapter: Provide a DAWN Link wrapper later (forgegate.evaluate) that reads ProposedAction/Signals artifacts and emits DecisionRecord + logs to DAWN ledger.

This preserves agnosticism while letting you plug into DAWN if/when you want.

Phase 1 — ForgeGate v0.1 (Gate Interface + Reference Implementation)
Phase 1 Goal

Ship a stable, testable, replayable Gate Interface v0.1 with a minimal reference gate that produces deterministic DecisionRecords and can be adopted by any multi-agent team.

Deliverables

Schemas (locked)

schemas/proposed_action.v0_1.json

schemas/signals.v0_1.json

schemas/decision_record.v0_1.json

Canonicalization + hashing

Canonical JSON serialization rules (sorted keys, stripped volatile fields like nonce)

input_hash = sha256(canonical(ProposedAction, Signals.values, BudgetSnapshot?))

decision_id = sha256(intent_version + input_hash)

Gate runtime (reference)

evaluate(intent_spec, proposed_action, signals, budget_snapshot?) -> decision_record

Deterministic evaluation order:

Constraints (deny/escalate)

Boundaries (autonomy caps → escalate)

Budgets (exceeded → escalate/deny)

Tradeoffs (choose active branch; record it)

Shaping (ALLOW_WITH_MODS)

Emit DecisionRecord (with triggered rule IDs)

Scenario test harness

JSON scenario format with expected.decision + must_include fields

Baseline test suite:

constraint invariants

boundary enforcement

budget enforcement

tradeoff branch coverage

determinism replay (same input → same output)

Developer UX

Minimal CLI:

forgegate evaluate --intent intent.json --action action.json --signals signals.json

Outputs DecisionRecord JSON to stdout

README: “how to integrate into orchestrators/tool routers”

Done looks like (acceptance criteria)

✅ Schemas validate all test fixtures

✅ Determinism: identical inputs produce identical decision, input_hash, decision_id

✅ DecisionRecord always contains triggered_rules[] (even if empty) and intent versioning

✅ At least 10 baseline scenarios pass in CI

✅ CLI works end-to-end (evaluate + emit DecisionRecord)

Phase 1 tasking mapped to your agent team roles
Researcher

Define generic action taxonomy examples (read/write/external_write/irreversible)

Define a starter signal set (risk_score, compliance_risk, requires_approval, etc.)

Produce 10–15 realistic scenarios for testing

Thinker (Dev Lead)

Lock the schema fields and determinism rules

Define the reference evaluation order + required DecisionRecord explanation contract

Define minimal IntentSpec subset needed for Phase 1 gate execution (constraints/boundaries/budgets/tradeoffs IDs)

Coder

Implement schema validation, canonicalization, hashing, evaluate()

Implement expression evaluation for when clauses (keep it deterministic)

Implement CLI + packaging

Tester

Build scenario runner

Add determinism test (replay snapshot test)

Add negative tests (invalid schema, missing signals, unknown action_id)

Documentation

Write the “Adoption Guide”:

where to intercept tool calls

how to populate ProposedAction + Signals

how to interpret DecisionRecord + escalation payload