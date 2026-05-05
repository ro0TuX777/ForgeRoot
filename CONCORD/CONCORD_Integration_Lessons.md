# CONCORD Integration Lessons — Generalized Guidance

**Source:** First native CONCORD integration into a legacy web application  
**Date:** April 2026  
**Basis:** CONCORD v0.3 spec pack + v0.4 Gap Analysis + real integration experience  

---

## Purpose

This document captures lessons from the first end-to-end integration of CONCORD governance into an existing web application. The findings are generalized into two camps:

- **Camp 1 — What CONCORD must provide:** Wiring, runtime contracts, and pipeline logic that CONCORD itself must define. These are framework-level gaps that apply regardless of the target application.
- **Camp 2 — Instructions for the integration agent:** Guidance that should be provided to any AI agent tasked with wiring a legacy application to accept CONCORD governance.

Both camps are written to be **application-agnostic**. No specifics of the integration target are referenced.

---

# Camp 1 — What CONCORD Must Provide

*Audience: CONCORD spec and framework development team.*

---

## 1.1 The Admission Pipeline Must Be Specified as an Ordered, Mandatory Sequence

CONCORD v0.3 defines Session, Intent, ActionContract, and Budget entities. It defines an error catalog. But it does **not** specify the runtime admission pipeline — the ordered sequence of checks that an Intent passes through before execution. The integration agent had to invent this order and guessed wrong, skipping critical stages.

**CONCORD must normatively define the following ordered stages:**

1. **SessionResolution** — look up session, check status and expiry
2. **ActionResolution** — look up ActionContract from registry
3. **TrustGate** — compare agent's trust tier to action's minimum
4. **BudgetGate** — check ledger against profile limits, check circuit breaker
5. **GuardEvaluation** — execute all guards declared on the ActionContract
6. **InputValidation** — validate parameters against the ActionContract's `input_schema`
7. **IdempotencyCheck** — check for duplicate idempotency keys
8. **IntentCreation** — persist the admitted Intent
9. **Execution** — hand off to the app-specific executor
10. **ReceiptMinting** — record outcome, update ledger

**Additionally specify:**

- Which stages are mandatory vs. optional
- That **every entry point** (direct intent, dispatch, batch, webhook) MUST route through the same pipeline. Convenience endpoints that skip stages create governance bypasses.

---

## 1.2 Guard Evaluation Needs a Runtime Contract

Every ActionContract declares guards as string names. But CONCORD provides no guard registry pattern, no evaluation contract, no failure response shape, and no ordering or short-circuit rules. Without this, guards are decorative metadata. The integration agent declared them on every ActionContract but never executed them. Agent consumers hit raw exceptions instead of governed `GUARD_FAILED` responses.

**CONCORD must provide:**

```
Guard Contract:
  Input:  (parameters: dict, session: Session, action: ActionContract)
  Output: GuardResult { passed: bool, guard_name: str, reason: str? }

Guard Registry:
  Mapping of guard_name → guard_callable
  Provided by the host application at integration time

Pipeline behavior:
  Evaluate guards in declared order
  On first failure: return GUARD_FAILED with { failed_guard, reason }
  Do NOT proceed to InputValidation or Execution
```

---

## 1.3 Input Validation Must Be a Pipeline Stage, Not a Hope

ActionContracts declare `input_schema` with field types and `required` flags. But CONCORD provides no validation runtime. The schema is metadata that nothing reads at admission time. An agent can submit an intent with an empty parameters dict and get raw crashes during execution.

**CONCORD must specify:**

- A dedicated admission stage that validates `parameters` against `input_schema` before intent creation
- A dedicated error code (`INVALID_PARAMETERS`) with field-level detail:

```json
{
  "code": "INVALID_PARAMETERS",
  "missing_fields": ["directory", "repo_name"],
  "invalid_fields": [],
  "agent_should": "recheck",
  "requires_context_refresh": true
}
```

- The schema format: adopt JSON Schema or define a minimal spec so both the integration agent (writing schemas) and the validation runtime (parsing them) share the same contract.

---

## 1.4 Output Normalization Contract

ActionContracts declare `output_schema`. Nothing enforces it. Legacy applications return data shaped for humans — HTML reports, raw log strings. The executor returns whatever the legacy code produces, and the agent receives unpredictable shapes.

**CONCORD must specify:**

- An output normalization stage between executor completion and receipt minting
- Executor output MUST be transformed to match `output_schema` before being stored on the Receipt's `result_summary`
- The host application is responsible for implementing normalizers; CONCORD must state this explicitly

---

## 1.5 Error Catalog Must Include `agent_should` on Every Entry

The error catalog defines error codes with `severity` and `agent_should` fields. This was one of CONCORD's strongest features — it lets agents self-correct without human intervention. However:

- Not all error codes had `agent_should` guidance
- There was no specification for how domain-specific exceptions should map to catalog errors
- The integration agent had to guess which legacy exceptions mapped to which CONCORD errors

**CONCORD must provide:**

- `agent_should` as a required field on every error catalog entry
- A documented **exception mapping pattern**: guidance for the integration agent on how to wrap host-application exceptions in CONCORD error responses

---

## 1.6 Budget Introspection Endpoint

An agent cannot plan its workflow if it can't see its remaining budget. The budget ledger exists but is only decremented — there's no read path. An agent must submit intents blind and discover budget exhaustion only on rejection.

**CONCORD must define:**

- A `/budget/status` endpoint (or equivalent) that returns remaining budget by category
- Optionally: a `/budget/estimate` endpoint that takes a list of planned actions and returns whether the budget can cover them

---

## 1.7 Session Refresh / Extension

Sessions have TTLs. Long-running workflows (multi-step agent tasks) can outlast their session. Currently there is no refresh mechanism — the session expires mid-task and subsequent intents fail.

**CONCORD must define:**

- A session refresh endpoint that extends `expires_at` without creating a new session
- Governance: refreshes should be logged and subject to a maximum lifetime cap
- The extension should be an auditable event, not a silent mutation

---

## 1.8 ReviewBundle Lifecycle

When actions produce outputs requiring human review, CONCORD should define the lifecycle states (`pending_review` → `approved` / `rejected`) and the agent-facing contract:

- How does the agent poll for review completion?
- What does the agent receive when review is approved vs. rejected?
- Can the agent retry after rejection?

Without this, the integration agent invented its own review handling, which may not be consistent across integrations.

---

## 1.9 OperationContext Must Be Dynamic

The `OperationContext` endpoint returns the ActionContract metadata for a given action. Currently it returns static schema information. For agent planning, it should also return:

- Current budget availability for that action
- Guard pre-evaluation (which guards would pass/fail given current state)
- Session-specific constraints

This turns OperationContext from a "read the docs" endpoint into a "can I do this right now?" endpoint.

---

## 1.10 Compensation / Saga Support

When a multi-step workflow fails partway through, there is no rollback mechanism. CONCORD should define:

- A compensation contract: for each action, an optional `compensate` action that reverses its effects
- Saga coordination: when a dispatch (multi-action) fails, which completed steps should be compensated?
- This can be deferred to a later version but should be on the roadmap

---
---

# Camp 2 — Instructions for the Integration Agent

*Audience: Any AI agent tasked with wiring a legacy web application to accept CONCORD governance for agent-driven execution.*

---

## 2.1 Your Job Is to Build an Execution Pipeline, Not Add API Routes

The most critical mental model: you are building a **governed execution pipeline** that sits between the agent consumer and the legacy application's existing logic. You are not "adding CONCORD endpoints to the app." The legacy app's routes, templates, and UI logic are irrelevant — you are building a new entry surface that:

1. Receives structured intent requests from agents
2. Runs them through the CONCORD admission pipeline (see Camp 1, §1.1)
3. Delegates to the legacy app's business logic
4. Normalizes the output into the ActionContract's `output_schema`
5. Returns structured receipts

Do NOT wire CONCORD into existing Flask/Django/Express routes. Build a separate blueprint/router that owns the agent-facing surface. The legacy routes continue serving human users unchanged.

---

## 2.2 Map the Legacy App's Capabilities to ActionContracts First

Before writing any code, audit the legacy application and identify every discrete capability it offers. Each capability becomes an ActionContract. For each:

- **Name** it with `family.verb` convention (e.g., `scan.static_analysis`, `report.export_pdf`)
- **Identify the minimum trust tier** — what level of agent autonomy is appropriate?
- **List the guards** — what preconditions must be true? (token configured, service healthy, target accessible)
- **Define `input_schema`** — what parameters does the capability need? Be explicit about types and required fields.
- **Define `output_schema`** — what structured data should the agent receive? This is NOT what the legacy code returns today. This is what the agent NEEDS. You will build the normalizer to bridge the gap.
- **Estimate cost** — assign a budget cost so the BudgetGate can enforce limits

Get this registry right before writing a single line of pipeline code.

---

## 2.3 The Executor Is a Translation Layer, Not a Passthrough

The executor bridges CONCORD intents to legacy function calls. It is NOT a thin wrapper. It has three responsibilities:

1. **Parameter translation** — map the ActionContract's `input_schema` fields to the arguments the legacy function expects (names may differ, formats may need conversion)
2. **Exception classification** — catch every exception the legacy code can throw and map it to a CONCORD error catalog entry with `agent_should` guidance. Never let a raw traceback reach the agent.
3. **Output normalization** — transform the legacy code's return value (HTML, raw strings, nested dicts, file paths) into the structured shape defined by `output_schema`

The most common mistake is building the executor as `return legacy_function(**params)`. This produces raw, unpredictable output and unclassified exceptions. The executor is where you earn the governance contract.

---

## 2.4 Every Entry Point Must Share the Same Pipeline

If the legacy app has multiple ways to trigger functionality (direct API calls, batch processing, webhook-triggered flows, a dispatch endpoint that chains actions), all of them MUST route through the same admission pipeline. Do NOT create convenience endpoints that skip trust, budget, or guard checks.

In practice: if you build a `/dispatch` endpoint that orchestrates multiple actions, it must submit each sub-action as a governed intent through the same admission path. Do not call the executor directly.

---

## 2.5 Output Normalization Is the Highest-Value Work

The single most valuable thing you do in the integration is **output normalization**. The legacy app was built for humans — its outputs are HTML pages, formatted strings, downloadable files. The agent needs structured, parseable data with consistent field names.

For each ActionContract, build a normalizer function that:

- Extracts structured data from whatever the legacy code returns
- Maps it to the `output_schema` fields
- Handles edge cases (empty results, partial failures, timeout results)
- Includes metadata the agent needs for decision-making (severity counts, confidence scores, pass/fail status)

Without this, the agent receives results it cannot parse, and the entire integration is useless.

---

## 2.6 Implement Guards as Executable Functions

CONCORD declares guard names on ActionContracts. You must implement a **guard registry** — a mapping of each guard name to a function that actually checks the precondition.

Each guard function signature:

```
(parameters: dict, session: Session) → (passed: bool, reason: str | None)
```

Register them in a dict. Evaluate them in the admission pipeline before creating the Intent. Return `GUARD_FAILED` with the guard name and reason if any fail.

If you declare guards but don't implement them, the agent sees guards listed in `OperationContext` and believes they're being enforced. They aren't. The agent will submit invalid requests expecting governed failures and instead get raw crashes.

---

## 2.7 Classify Every Legacy Exception

The legacy app throws exceptions you've never seen. Database errors, network timeouts, malformed input crashes, missing file errors, authentication failures. Each of these MUST be caught in the executor and mapped to a CONCORD error catalog entry.

Build an exception mapping table:

```
LegacyException              → CONCORD Error Code      → agent_should
git.GitCommandError           → SCAN_PATH_NOT_FOUND     → recheck
requests.Timeout              → EXTERNAL_SERVICE_TIMEOUT → retry
PermissionError               → TRUST_INSUFFICIENT      → escalate
json.JSONDecodeError          → INVALID_PARAMETERS      → recheck
subprocess.CalledProcessError → EXECUTION_FAILED        → report
```

Every `except` block in your executor should produce a structured CONCORD error response, never a raw 500.

---

## 2.8 The Legacy App's Existing Routes Are Not Your Concern

Do not modify the legacy app's existing routes, templates, or frontend logic. The human-facing application continues to work exactly as it did. Your CONCORD integration is a **parallel entry surface** — a new blueprint/router that shares the same business logic layer but provides a governed, structured interface for agents.

The only shared code should be the business logic functions themselves (the scan runners, the report generators, the data processors). Everything above that — routing, authentication, response formatting — is separate for human and agent surfaces.

---

## 2.9 Datetime and Database Compatibility

If the host application uses SQLite (or any database that strips timezone information), all datetime comparisons in the CONCORD pipeline must be timezone-safe. Specifically:

- When creating datetimes for `expires_at`, `created_at`, etc., use UTC-aware datetimes
- When reading them back from the database, assume they may have been stripped to naive. Normalize by re-attaching UTC before any comparison with `datetime.now(timezone.utc)`
- This is a silent bug — the code will work in tests with in-memory databases and fail in production when datetimes round-trip through SQLite

---

## 2.10 Test the Governance Layer Independently

Write tests that exercise the CONCORD governance pipeline in isolation from the legacy app's business logic. Test:

- **Admission stages**: session expiry, trust rejection, budget exhaustion, guard failure, input validation failure, idempotency conflict
- **Error responses**: every error code returns the correct shape with `agent_should` guidance
- **Receipt lifecycle**: intents produce receipts with structured `result_summary`
- **Budget accounting**: cost is deducted on success, not deducted on admission failure
- **Edge cases**: expired sessions, unknown actions, malformed parameters

Use a mock executor that returns canned results. This isolates governance correctness from legacy code behavior. Once governance tests pass, then test the executor's translation/normalization logic separately.

