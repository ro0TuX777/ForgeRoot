# CONCORD v0.5 — Admission Pipeline Specification

**Status:** Normative | **Version:** 0.5.0 | **Date:** April 2026  
**Supersedes:** Implicit pipeline ordering assumptions in v0.3 Core Specification  
**Prerequisite reading:** CONCORD v0.3 Core Specification §§ 3–5, Runtime Contract Schemas  

---

## 1. Purpose

CONCORD v0.3 defines the governance entities — Session, Intent, ActionContract, BudgetProfile, BudgetLedger — and an error catalog. It does **not** define the runtime admission pipeline: the ordered sequence of checks that an Intent passes through before execution is permitted.

This specification normatively defines that pipeline. Every CONCORD-governed system MUST implement this pipeline. No integration agent should need to invent the stage ordering, failure behavior, or enforcement contracts described here.

---

## 2. Pipeline Overview

Every Intent submission — regardless of entry point (direct API, dispatch, batch, webhook, CLI, Slack adapter, or any future channel) — MUST pass through the following ordered stages:

```
  Request
    │
    ▼
┌─────────────────────┐
│ ① SessionResolution │──fail──→ SESSION_EXPIRED | SESSION_NOT_FOUND | SESSION_SUSPENDED
│   (mandatory)       │
└────────┬────────────┘
         │ pass
         ▼
┌─────────────────────┐
│ ② ActionResolution  │──fail──→ ACTION_NOT_FOUND | ACTION_DEPRECATED
│   (mandatory)       │
└────────┬────────────┘
         │ pass
         ▼
┌─────────────────────┐
│ ③ TrustGate         │──fail──→ TRUST_INSUFFICIENT
│   (mandatory)       │
└────────┬────────────┘
         │ pass
         ▼
┌─────────────────────┐
│ ④ BudgetGate        │──fail──→ BUDGET_EXCEEDED | CIRCUIT_OPEN
│   (conditional)     │
└────────┬────────────┘
         │ pass
         ▼
┌─────────────────────┐
│ ⑤ GuardEvaluation   │──fail──→ GUARD_FAILED
│   (conditional)     │
└────────┬────────────┘
         │ pass
         ▼
┌─────────────────────┐
│ ⑥ InputValidation   │──fail──→ INVALID_PARAMETERS
│   (conditional)     │
└────────┬────────────┘
         │ pass
         ▼
┌─────────────────────┐
│ ⑦ IdempotencyCheck  │──fail──→ IDEMPOTENCY_CONFLICT
│   (conditional)     │
└────────┬────────────┘
         │ pass
         ▼
┌─────────────────────┐
│ ⑧ IntentCreation    │         (Intent persisted with status: admitted)
│   (mandatory)       │
└────────┬────────────┘
         │
═════════╪══════════════════════ ADMISSION BOUNDARY ═══════════════════
         │
         ▼
┌─────────────────────┐
│ ⑨ Execution         │──fail──→ EXECUTION_FAILED | domain-specific errors
│   (mandatory)       │
└────────┬────────────┘
         │ complete
         ▼
┌─────────────────────┐
│ ⑩ OutputNorm        │──fail──→ OUTPUT_NORMALIZATION_FAILED (non-fatal)
│   (conditional)     │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ ⑪ ReceiptMinting    │         (Receipt created, ledger updated)
│   (mandatory)       │
└─────────────────────┘
```

---

## 3. Normative Rules

### 3.1 Stage Ordering

Stages MUST be evaluated in the order listed (① through ⑪). An implementation MUST NOT reorder stages. Parallel evaluation of stages is NOT permitted — each stage depends on the success of the previous stage.

### 3.2 Fail-Fast

On failure at any stage, the pipeline MUST:

1. Return the corresponding error response immediately
2. NOT evaluate any subsequent stages
3. NOT invoke the host application's business logic
4. NOT deduct any cost from the budget ledger

The only exception to rule 4 is stage ⑨ (Execution). See §3.4.

### 3.3 The Admission Boundary

Stages ①–⑧ constitute **admission**. During admission:

- No side effects are permitted in the host application
- No cost is deducted from the budget ledger
- No resource state is mutated (beyond persisting the Intent record at stage ⑧)
- If any admission stage fails, the system state is unchanged from the caller's perspective

Stages ⑨–⑪ constitute **execution**. During execution:

- Side effects occur in the host application
- The intent status transitions from `admitted` to `executing` and then to a terminal state
- Cost is deducted at stage ⑪ regardless of whether execution succeeded or failed

### 3.4 Cost Accounting

- **Admission failure (stages ①–⑦):** No cost is deducted. The intent may not even be created (failure before stage ⑧).
- **Execution (stage ⑨ onward):** Cost IS deducted at stage ⑪ regardless of execution outcome. The rationale: the system expended resources (compute, API calls, time) during execution. Failed executions still consumed budget.
- **Exception:** If the executor determines that no work was performed (e.g., immediate connection failure before any processing), it MAY signal `zero_cost: true` on the execution result. ReceiptMinting SHOULD respect this signal and deduct zero cost.

### 3.5 Mandatory vs. Conditional Stages

| Stage | Mandatory? | Skip Condition |
|---|---|---|
| ① SessionResolution | Always mandatory | — |
| ② ActionResolution | Always mandatory | — |
| ③ TrustGate | Always mandatory | — |
| ④ BudgetGate | Conditional | Skip if the session's AgentClass has no BudgetProfile assigned |
| ⑤ GuardEvaluation | Conditional | Skip if the resolved ActionContract declares `guards: []` or `guards` is absent |
| ⑥ InputValidation | Conditional | Skip if the ActionContract declares `input_schema: {}` or `input_schema` is absent |
| ⑦ IdempotencyCheck | Conditional | Skip if the request does not include an `idempotency_key` |
| ⑧ IntentCreation | Always mandatory | — |
| ⑨ Execution | Always mandatory | — |
| ⑩ OutputNormalization | Conditional | Skip if the ActionContract declares `output_schema: {}` or `output_schema` is absent |
| ⑪ ReceiptMinting | Always mandatory | — |

A stage marked "conditional" with its skip condition met is **not evaluated** — the pipeline proceeds directly to the next stage. This is distinct from a stage that evaluates and passes.

### 3.6 Entry Point Invariance

**Every entry point MUST route through the same pipeline.** This is a non-negotiable governance requirement.

Entry points include but are not limited to:
- Direct intent submission (single action)
- Dispatch endpoint (multi-action orchestration)
- Batch submission
- Webhook-triggered execution
- CLI invocation
- Chat/messaging adapters (Slack, Discord, etc.)
- Scheduled/cron execution
- Event-driven triggers

If a dispatch endpoint orchestrates multiple actions, each sub-action MUST be submitted as a separate Intent through the full admission pipeline. The dispatch coordinator MUST NOT call the executor directly.

Convenience endpoints that skip any stage are a **governance violation** and MUST NOT be implemented.

---

## 4. Stage Specifications

### 4.1 Stage ① — SessionResolution

**Purpose:** Resolve the session from the request and verify it is valid for use.

**Input:** `session_id` from the intent request

**Evaluation:**

1. Look up the Session record by `session_id`
2. If not found → return `SESSION_NOT_FOUND`
3. If `status` is `suspended` → return `SESSION_SUSPENDED`
4. If `status` is `terminated` or `expired` → return `SESSION_EXPIRED`
5. If `expires_at` is in the past → update status to `expired`, return `SESSION_EXPIRED`
6. If `status` is `active` and not expired → **pass**

**Output on pass:** Resolved Session object (available to all subsequent stages)

**Datetime safety:** When comparing `expires_at` to current time, implementations MUST normalize both values to UTC-aware timestamps. If the persistence layer strips timezone information (e.g., SQLite), the implementation MUST re-attach UTC before comparison. See §7 (Implementation Notes).

---

### 4.2 Stage ② — ActionResolution

**Purpose:** Resolve the requested action from the ActionContract registry.

**Input:** `action_name` from the intent request

**Evaluation:**

1. Look up the ActionContract by `action_name` in the registry
2. If not found → return `ACTION_NOT_FOUND`
3. If the ActionContract is marked as deprecated → return `ACTION_DEPRECATED` (new error code, severity: warning, agent_should: recheck)
4. If found and active → **pass**

**Output on pass:** Resolved ActionContract object (available to all subsequent stages)

---

### 4.3 Stage ③ — TrustGate

**Purpose:** Verify the agent's trust tier meets the action's minimum requirement.

**Input:** Resolved Session (provides AgentClass and trust tier), resolved ActionContract (provides `minimum_trust_tier`)

**Evaluation:**

1. Retrieve the agent's trust tier from the Session's AgentClass
2. Retrieve the action's `minimum_trust_tier` from the ActionContract
3. If agent tier < action minimum → return `TRUST_INSUFFICIENT`
4. If agent tier >= action minimum → **pass**

**Output on pass:** Trust evaluation result (for audit/telemetry)

---

### 4.4 Stage ④ — BudgetGate

**Purpose:** Verify the session's budget can cover the action's cost and that the circuit breaker is not open.

**Input:** Resolved Session (provides BudgetProfile reference), resolved ActionContract (provides `cost`)

**Evaluation:**

1. If the Session's AgentClass has no BudgetProfile → **skip** (this stage is conditional)
2. Look up the BudgetLedger for the session (or fleet, if fleet-governed)
3. Check the circuit breaker state for the action's `action_family`:
   - If circuit is `open` → return `CIRCUIT_OPEN`
   - If circuit is `half-open` → proceed but flag for monitoring
4. Calculate remaining budget for the action's cost category
5. If remaining budget < action cost → return `BUDGET_EXCEEDED`
6. If budget sufficient and circuit not open → **pass**

**IMPORTANT:** Budget is checked but NOT deducted at this stage. Deduction occurs at stage ⑪ (ReceiptMinting). This prevents double-charging on execution failures that are retried.

---

### 4.5 Stage ⑤ — GuardEvaluation

**Purpose:** Execute all guards declared on the ActionContract and verify all preconditions are met.

**Input:** Intent parameters, resolved Session, resolved ActionContract

**Evaluation:**

1. If the ActionContract declares no guards (`guards: []` or absent) → **skip**
2. For each guard in the ActionContract's `guards` array, **in declared order**:
   a. Look up the guard in the Guard Registry (see §5)
   b. If the guard is not registered → return `GUARD_NOT_REGISTERED` (fatal — this is a configuration error, not a runtime condition)
   c. Execute the guard callable with `(parameters, session, action_contract)`
   d. If the guard returns `passed: false` → return `GUARD_FAILED` with `{ failed_guard, reason, guard_index }`
   e. If the guard returns `passed: true` → proceed to the next guard
3. If all guards pass → **pass**

**Short-circuit behavior:** Guard evaluation is **short-circuit on first failure**. If the second of five guards fails, guards 3–5 are not evaluated. The error response includes only the first failed guard.

**Rationale for short-circuit:** Guards may have dependencies (e.g., guard 2 checks if a service is healthy; guard 3 queries that service). Evaluating subsequent guards after a failure may produce misleading results or cause errors.

---

### 4.6 Stage ⑥ — InputValidation

**Purpose:** Validate the intent's `parameters` against the ActionContract's `input_schema`.

**Input:** Intent parameters, resolved ActionContract

**Schema format:** `input_schema` MUST be expressed as **JSON Schema (draft 2020-12)**. This provides a well-defined, widely-tooled validation contract that both integration agents (writing schemas) and the runtime (validating against them) can rely on.

**Evaluation:**

1. If the ActionContract declares no `input_schema` (absent or `{}`) → **skip**
2. Validate `parameters` against `input_schema`:
   a. Identify missing required fields
   b. Identify fields with incorrect types
   c. Identify fields present in `parameters` but not in `input_schema` (extra fields)
3. If there are missing required fields OR type-invalid fields → return `INVALID_PARAMETERS`
4. If there are only extra fields → emit a warning in telemetry but **proceed** (warn-but-pass policy). Include `extra_fields` in the response metadata for agent awareness.
5. If all required fields present and all types valid → **pass**

**Error response shape for INVALID_PARAMETERS:**

```json
{
  "code": "INVALID_PARAMETERS",
  "severity": "warning",
  "agent_should": "recheck",
  "requires_context_refresh": true,
  "detail": {
    "missing_fields": ["directory", "repo_name"],
    "invalid_fields": [
      {
        "field": "max_depth",
        "expected": "integer",
        "received": "string",
        "constraint": "minimum: 1"
      }
    ],
    "extra_fields": ["unknown_param"]
  }
}
```

**Extra fields policy:** Extra fields (parameters not declared in `input_schema`) are **warned but not rejected**. Rationale: strict rejection breaks forward compatibility when new optional parameters are added to an ActionContract. The `extra_fields` list in the response gives agents visibility without blocking execution.

---

### 4.7 Stage ⑦ — IdempotencyCheck

**Purpose:** Detect duplicate intent submissions using the idempotency key.

**Input:** `idempotency_key` from the intent request

**Evaluation:**

1. If the request does not include an `idempotency_key` → **skip**
2. Look up existing Intents with the same `idempotency_key`
3. If a matching Intent exists:
   a. If the existing Intent is in a terminal state (`completed`, `failed`) → return the existing Receipt (idempotent replay)
   b. If the existing Intent is in a non-terminal state (`admitted`, `executing`) → return `IDEMPOTENCY_CONFLICT` with a reference to the in-progress intent
4. If no matching Intent exists → **pass**

---

### 4.8 Stage ⑧ — IntentCreation

**Purpose:** Persist the admitted Intent.

**Input:** All resolved context from prior stages

**Behavior:**

1. Create the Intent record with status `admitted`
2. Record: session_id, action_name, parameters, trust_tier, budget_cost, guards_passed, idempotency_key, timestamp
3. Return the `intent_id` for subsequent stages

This stage always succeeds unless there is a system-level persistence failure, in which case return `INTENT_CREATION_FAILED` (severity: elevated, agent_should: retry).

---

### 4.9 Stage ⑨ — Execution

**Purpose:** Delegate the admitted Intent to the host application's executor.

**Input:** Admitted Intent, resolved ActionContract, resolved Session

**Behavior:**

1. Transition Intent status from `admitted` to `executing`
2. Invoke the host application's executor with the Intent's parameters
3. The executor is responsible for:
   - Parameter translation (mapping CONCORD field names to legacy function arguments)
   - Exception classification (catching all host exceptions and mapping to CONCORD error codes)
   - Returning a structured result or classified error
4. On executor success → proceed to stage ⑩ with the raw result
5. On executor failure → proceed to stage ⑪ with the classified error

**The executor contract is detailed in the Executor Contract section (§6).**

---

### 4.10 Stage ⑩ — OutputNormalization

**Purpose:** Transform the executor's raw output into the ActionContract's `output_schema` format.

**Input:** Raw executor output, resolved ActionContract

**Schema format:** `output_schema` MUST be expressed as **JSON Schema (draft 2020-12)**, consistent with `input_schema`.

**Evaluation:**

1. If the ActionContract declares no `output_schema` (absent or `{}`) → **skip.** Raw output passes through to ReceiptMinting.
2. Invoke the host application's normalizer for this action with `(raw_output, action_contract)`
3. The normalizer returns a `NormalizationResult`:
   ```
   NormalizationResult:
     normalized:  object     # output conforming to output_schema
     warnings:    array?     # fields that couldn't be mapped (non-fatal)
     raw_ref:     string?    # optional reference to raw output for debugging
   ```
4. If normalization succeeds → proceed to stage ⑪ with the normalized output
5. If normalization fails entirely → proceed to stage ⑪ with:
   - Intent status: `completed_with_normalization_failure`
   - The raw output preserved in a `raw_output` field on the Receipt
   - An `OUTPUT_NORMALIZATION_FAILED` warning attached to the Receipt metadata

**IMPORTANT:** Output normalization failure is **non-fatal**. The action executed successfully — the output simply couldn't be transformed into the declared schema. The Receipt MUST still be minted. The agent receives the raw output with a warning that it is unnormalized.

**Normalizer contract:**

```
Normalizer signature:
  (raw_output: any, action_contract: ActionContract) → NormalizationResult

Owner: Host application (the integration agent writes normalizers)

Rules:
  - One normalizer per ActionContract (or per action_family with overrides)
  - Normalizers MUST handle edge cases: empty results, partial data, 
    timeout indicators, error objects
  - Normalizers MUST NOT throw exceptions — return a failed NormalizationResult 
    with warnings instead
  - The normalized output SHOULD be validated against output_schema before 
    being placed on the Receipt
```

---

### 4.11 Stage ⑪ — ReceiptMinting

**Purpose:** Record the execution outcome, update the budget ledger, and return the receipt to the caller.

**Input:** Execution result (normalized or raw), Intent, Session, ActionContract

**Behavior:**

1. Create the Receipt record:
   - `intent_id`: reference to the admitted Intent
   - `session_id`: owning session
   - `action_name`: executed action
   - `status`: success | failed | completed_with_errors | completed_with_normalization_failure
   - `result_summary`: normalized output (or raw output if normalization was skipped/failed)
   - `cost_deducted`: the actual cost charged to the ledger
   - `executed_at`: timestamp
   - `duration_ms`: execution wall-clock time
   - `environment_id`: (optional, from v0.4) execution environment reference
   - `entry_point_id`: (optional, from v0.4) originating entry point
2. Update the BudgetLedger:
   - Deduct the action's cost from the appropriate budget category
   - Unless `zero_cost: true` was signaled by the executor
3. Update Intent status to terminal state
4. Return the Receipt to the caller

---

## 5. Guard Runtime Contract

### 5.1 Guard Contract

Every guard declared on an ActionContract MUST be backed by an executable function. Guards are precondition checks that evaluate whether the current system state permits the action to proceed.

**Guard function signature:**

```
GuardCallable:
  Input:
    parameters:     dict              # the intent's parameters
    session:        Session           # the resolved session
    action_contract: ActionContract   # the resolved action contract
  
  Output: GuardResult
    passed:         bool              # did the guard pass?
    guard_name:     string            # name of the guard that was evaluated
    reason:         string?           # human+agent readable explanation (required on failure)
    metadata:       object?           # optional structured data (e.g., current value vs. threshold)
```

### 5.2 Guard Registry

The Guard Registry is a mapping of guard names to guard callables. It is **provided by the host application** at integration time — CONCORD defines the contract, not the implementations.

```
Guard Registry:
  Type:    Map<guard_name: string, guard_callable: GuardCallable>
  Owner:   Host application
  Timing:  Must be fully populated before the pipeline accepts requests
```

**Startup validation:** When the CONCORD pipeline initializes, it MUST cross-reference every `guard_name` declared on any ActionContract in the registry against the Guard Registry. If any guard name lacks a registered callable, the pipeline MUST fail to start with a configuration error. This catches missing guard implementations at deploy time, not at runtime when an agent submits a request.

### 5.3 Guard Failure Response

When a guard fails, the pipeline returns:

```json
{
  "code": "GUARD_FAILED",
  "severity": "warning",
  "agent_should": "recheck",
  "requires_context_refresh": true,
  "detail": {
    "failed_guard": "service_healthy",
    "guard_index": 2,
    "reason": "Target service returned HTTP 503 during health check",
    "metadata": {
      "service": "analysis-engine",
      "last_healthy_at": "2026-04-01T12:30:00Z",
      "retry_after_ms": 30000
    }
  }
}
```

### 5.4 Guard Design Guidelines

Guards SHOULD be:

- **Fast:** Guards are evaluated on every intent admission. Long-running checks (network calls, database scans) should be cached with a declared TTL.
- **Idempotent:** Evaluating a guard MUST NOT mutate state. Guards are read-only checks.
- **Specific:** Each guard checks one precondition. Compound checks should be split into separate guards so failure messages are actionable.
- **Documented:** Each guard registered by the host application SHOULD include a description that can be surfaced in OperationContext for agent planning.

---

## 6. Executor Contract

The executor bridges CONCORD intents to host application business logic. It is a **translation layer**, not a passthrough.

### 6.1 Executor Signature

```
ExecutorCallable:
  Input:
    intent:          Intent            # the admitted intent (includes parameters)
    session:         Session           # the resolved session
    action_contract: ActionContract    # the resolved action contract
  
  Output: ExecutionResult
    success:         bool              # did execution succeed?
    raw_output:      any               # the host application's return value
    error:           ConcordError?     # classified error on failure (see §6.3)
    zero_cost:       bool              # if true, ReceiptMinting deducts zero cost
    duration_ms:     integer           # execution wall-clock time
    metadata:        object?           # optional execution metadata for telemetry
```

### 6.2 Executor Responsibilities

The executor has three responsibilities that MUST be fulfilled:

1. **Parameter Translation** — Map the ActionContract's `input_schema` field names to the arguments the host application's function expects. Names may differ. Formats may need conversion (e.g., ISO date strings to datetime objects, comma-separated strings to arrays).

2. **Exception Classification** — Catch **every** exception the host application can throw and map it to a CONCORD error catalog entry. Never let a raw traceback or unclassified exception escape the executor boundary. See §6.3.

3. **Result Packaging** — Return the host application's output as `raw_output` in the `ExecutionResult`. The executor does NOT normalize output — that is stage ⑩'s responsibility. But the executor MUST ensure `raw_output` is serializable.

### 6.3 Exception Mapping

Every executor MUST define an exception mapping table that classifies host application exceptions into CONCORD error responses.

**Exception mapping structure:**

```
ExceptionMapping:
  host_exception_type:    string          # the exception class name
  concord_error_code:     string          # CONCORD error catalog code
  agent_should:           string          # agent behavioral guidance
  severity:               string          # error severity level
  requires_context_refresh: bool          # should the agent refresh OperationContext?
  extract_detail:         function?       # optional function to extract structured 
                                          # detail from the exception
```

**Example mapping table:**

| Host Exception | CONCORD Error Code | agent_should | severity |
|---|---|---|---|
| `ConnectionError` | `EXTERNAL_SERVICE_TIMEOUT` | retry | elevated |
| `PermissionError` | `TRUST_INSUFFICIENT` | escalate | elevated |
| `FileNotFoundError` | `RESOURCE_NOT_FOUND` | recheck | warning |
| `ValueError` | `INVALID_PARAMETERS` | recheck | warning |
| `TimeoutError` | `EXECUTION_TIMEOUT` | retry | elevated |
| *(any unmatched)* | `EXECUTION_FAILED` | report | elevated |

**Default handler:** The mapping table MUST include a catch-all entry for unmatched exceptions. This ensures no raw exception ever reaches the agent. The default mapping SHOULD use `EXECUTION_FAILED` with `agent_should: report`.

**Exception detail preservation:** The host exception's message SHOULD be included in the error response's `detail` object for debugging, but MUST NOT be the primary agent guidance. The agent reads `agent_should`; the human reads `detail.exception_message`.

---

## 7. Implementation Notes

### 7.1 Datetime Safety

All datetime comparisons in the pipeline MUST be timezone-safe.

**The problem:** Some persistence layers (notably SQLite) strip timezone information from stored timestamps. A datetime stored as `2026-04-01T12:00:00+00:00` may be read back as `2026-04-01T12:00:00` (naive). Comparing a naive datetime to `datetime.now(timezone.utc)` produces incorrect results or raises exceptions.

**Required behavior:**

1. When creating timestamps (`expires_at`, `created_at`, etc.), always use UTC-aware timestamps.
2. When reading timestamps from persistence, normalize by re-attaching UTC if the value is naive.
3. All comparisons MUST be between two UTC-aware timestamps.

**This is a silent bug** — it works in tests with in-memory databases and fails in production when datetimes round-trip through storage.

### 7.2 Pipeline as a Separate Entry Surface

The CONCORD admission pipeline MUST be implemented as a **separate entry surface** from the host application's existing routes. It shares the host application's business logic layer, but all routing, authentication, and response formatting are independent.

The host application's existing human-facing routes (web UI, existing API, templates) MUST NOT be modified by the CONCORD integration. The two surfaces share only the business logic functions.

```
┌─────────────────────────────────────────────┐
│               Host Application               │
│                                               │
│  ┌───────────────┐    ┌───────────────────┐  │
│  │ Human Surface  │    │  Agent Surface     │  │
│  │ (existing      │    │  (CONCORD Pipeline)│  │
│  │  routes/UI)    │    │                    │  │
│  └───────┬────────┘    └────────┬──────────┘  │
│          │                      │              │
│          │    ┌─────────────┐   │              │
│          └───→│ Business    │←──┘              │
│               │ Logic Layer │                  │
│               └─────────────┘                  │
└─────────────────────────────────────────────┘
```

### 7.3 Pipeline Testing Strategy

The admission pipeline SHOULD be tested independently from the host application's business logic. Use a mock executor that returns canned results to isolate governance correctness.

**Minimum test coverage for pipeline correctness:**

| Category | Test Cases |
|---|---|
| Session | Valid session, expired session, suspended session, not-found session, timezone-edge expiry |
| Action | Known action, unknown action, deprecated action |
| Trust | Sufficient tier, insufficient tier, boundary tier |
| Budget | Sufficient budget, exhausted budget, circuit breaker open, no budget profile |
| Guards | All pass, first fails, middle fails, unregistered guard |
| Input | Valid params, missing required, wrong type, extra fields |
| Idempotency | New key, duplicate with completed intent, duplicate with in-progress intent |
| Receipt | Success receipt, failure receipt, zero-cost receipt |
| Budget accounting | Cost deducted on success, cost NOT deducted on admission failure |

---

## 8. Error Codes Introduced

This specification introduces or clarifies the following error codes. All codes include the `agent_should` field as REQUIRED.

| Code | Severity | agent_should | Introduced by |
|---|---|---|---|
| `SESSION_NOT_FOUND` | elevated | abort | Stage ① |
| `SESSION_EXPIRED` | warning | recheck | Stage ① |
| `SESSION_SUSPENDED` | elevated | escalate | Stage ① |
| `ACTION_NOT_FOUND` | warning | recheck | Stage ② |
| `ACTION_DEPRECATED` | warning | recheck | Stage ② (new) |
| `TRUST_INSUFFICIENT` | elevated | escalate | Stage ③ |
| `BUDGET_EXCEEDED` | warning | wait | Stage ④ |
| `CIRCUIT_OPEN` | warning | wait | Stage ④ |
| `GUARD_FAILED` | warning | recheck | Stage ⑤ |
| `GUARD_NOT_REGISTERED` | critical | report | Stage ⑤ (new) |
| `INVALID_PARAMETERS` | warning | recheck | Stage ⑥ (new) |
| `IDEMPOTENCY_CONFLICT` | informational | wait | Stage ⑦ |
| `INTENT_CREATION_FAILED` | elevated | retry | Stage ⑧ (new) |
| `EXECUTION_FAILED` | elevated | report | Stage ⑨ |
| `EXECUTION_TIMEOUT` | elevated | retry | Stage ⑨ (new) |
| `OUTPUT_NORMALIZATION_FAILED` | informational | — | Stage ⑩ (new, non-fatal warning) |

---

## 9. Relationship to Existing Spec Sections

| v0.3 Spec Section | Relationship |
|---|---|
| §3 Entity Definitions (Session, Intent, ActionContract) | This spec defines the **runtime evaluation order** for those entities. No entity changes. |
| §4 Trust & Capabilities | TrustGate (stage ③) is the runtime enforcement of the trust model. |
| §5 Budget & Resource Management | BudgetGate (stage ④) and ReceiptMinting (stage ⑪) are the runtime enforcement. |
| Error & Conflict Code Catalog | New codes added (see §8). Existing codes gain `agent_should` as required. |
| Runtime Contract Schemas | Guard Contract, Executor Contract, and Normalizer Contract are new runtime contracts. |

| v0.4 Proposal | Relationship |
|---|---|
| Gap 4: Multi-Entry Admission Surface | §3.6 (Entry Point Invariance) is the pipeline-side requirement that v0.4 EntryPoints must satisfy. |
| Gap 6: ReviewBundle | OutputNormalization (stage ⑩) feeds into ReviewBundle assembly. |
| Gap 5: ContextScope | ContextScopes are evaluated alongside OperationContext, which is a planning-time query — not an admission stage. |

---

## 10. Post-Deploy Readiness Phase

### 10.1 Lifecycle Position

The admission pipeline (stages ①–⑪) defines how intents are processed at runtime. But the pipeline cannot process intents if the host application's infrastructure is not running, reachable, and discoverable.

CONCORD's full processing lifecycle includes four phases. The admission pipeline is Phase 1. Phases 2–3 (SDK generation, documentation) are covered by the Integration Guide. **Phase 4 is new:**

```
CONCORD Processing Lifecycle:

  Phase 1: admission_pipeline   → sessions, actions, guards, budget  (this spec, §2–8)
  Phase 2: sdk_generation       → client, config, errors             (Integration Guide §3.1–3.6)
  Phase 3: documentation        → integration guide, scenarios       (Integration Guide §3.6)
  Phase 4: post_deploy          → port assignment, build, start,     (Integration Guide §3.7–3.12)
                                   health probe, manifest
```

### 10.2 Phase 4 Is Mandatory

Phase 4 is a **normative framework requirement**, not an optional operational procedure. A CONCORD integration is not complete until:

1. The host application's containers are built and running
2. All service health endpoints respond successfully
3. A machine-readable connection manifest has been generated and published
4. The SDK integration guide references the manifest's actual deployed endpoints

Without Phase 4, the framework produces an SDK that agents cannot use — the bridge is built but the other side is not standing.

### 10.3 Deployment Agent

Phase 4 is executed by a **Deployment Agent** — a separate actor from the Integration Agent that built Phases 1–3. The Deployment Agent:

- Consumes CONCORD metadata (ActionContract registry, service definitions, compose files) produced by the Integration Agent
- Operates **outside** the admission pipeline (it is standing up the infrastructure the pipeline runs on)
- Does NOT require a CONCORD session or trust tier — it is a privileged infrastructure actor
- Logs all deployment decisions to `DEPLOYMENT_NOTES.md` for auditability
- Generates the connection manifest that consuming agents use to configure their SDKs

The Deployment Agent MAY be the same entity as the Integration Agent, but the role separation is normative — Phase 4 steps are deployment concerns, not governance concerns.

### 10.4 Phase 4 Steps (Summary)

Phase 4 consists of six steps, fully specified in the Integration Guide (§3.7–3.12):

| Step | Name | Purpose |
|---|---|---|
| 3.7 | Deterministic Port Assignment | Compute application-unique ports from the app name to avoid collisions |
| 3.8 | `.dockerignore` Generation | Prevent bloated build contexts |
| 3.9 | Build Validation | Run `docker compose build` and classify failures |
| 3.10 | Start & Health Probe | Start containers and poll health endpoints |
| 3.11 | Platform-Specific Checks | Detect and remediate Docker Desktop constraints (Windows/macOS) |
| 3.12 | Connection Manifest Generation | Produce `connection_manifest.yaml` and `CONNECTION_MANIFEST.md` |

### 10.5 Post-Deploy Error Codes

Phase 4 introduces five new error codes in the `deploy` category. These are documented in the Error Catalog Amendments (§3.10–3.14). Unlike admission errors (which are returned to agents at runtime), deploy errors are encountered by the Deployment Agent during infrastructure setup and are logged to `DEPLOYMENT_NOTES.md`.

### 10.6 Post-Deploy Readiness Endpoint

After Phase 4 completes, the host application exposes a `/deploy/status` endpoint that agents and operators can query to verify deployment health. This endpoint is documented in the Runtime Endpoint Contracts (§5).

---

*End of Admission Pipeline Specification. This document is normative for all CONCORD v0.5+ implementations.*
