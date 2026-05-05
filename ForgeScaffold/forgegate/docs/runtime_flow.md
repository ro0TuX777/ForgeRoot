# ForgeGate Runtime Flow

## Interception points
- Agent proposes an action (tool call, API call, deployment, write, etc.).
- Build `ProposedAction` from action intent + parameters.
- Build `Signals` from runtime telemetry and policy context.
- Optional: attach a `BudgetSnapshot`.

## Evaluation
- ForgeGate evaluates deterministically in the following order:
  0) Intent preflight validation (invalid policy spec → ESCALATE)
  1) Constraints (DENY / ESCALATE)
  2) Boundaries (autonomy limits → ESCALATE)
  3) Budgets (exceeded → ESCALATE/DENY)
  4) Tradeoffs (select branch, record `active_tradeoff_id`)
  5) Shaping (ALLOW_WITH_MODS with `mods`)

Preflight catches common integration mistakes:
- unknown top-level keys (for example `rules` instead of `constraints`)
- invalid `when` types (string DSL where AST is required)
- empty policy specs with no active policy sections

## Escalation payload contract
When a decision is ESCALATE, the DecisionRecord includes:
- `escalation.channels[]`
- `escalation.required_payload_fields[]`
- `escalation.sla_minutes` (if provided)

Integrators should attach the DecisionRecord plus required payload fields to the escalation channel.

## Determinism guarantees
- Inputs are canonicalized and hashed deterministically.
- Volatile fields do not affect decisions.
- No network calls or non-deterministic operations are used.

## Input hash definition (v0.1)
- ProposedAction (after stripping volatile fields)
- Signals.values only (never provenance)
- BudgetSnapshot (after stripping volatile fields), if provided
- List ordering preserved except recognized context_refs lists, which are sorted deterministically

## Fail-closed defaults
- Missing referenced signals default to ESCALATE (policy_conflict).
- Optional override: intent_spec.allow_missing_signals.
