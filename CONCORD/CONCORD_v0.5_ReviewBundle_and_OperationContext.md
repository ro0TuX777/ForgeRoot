# CONCORD v0.5 — ReviewBundle Lifecycle & Dynamic OperationContext

**Status:** Normative | **Version:** 0.5.0 | **Date:** April 2026  
**Extends:** CONCORD v0.4 Gap Analysis — Gap 5 (ContextScope) and Gap 6 (ReviewBundle)  

---

## 1. Purpose

The v0.4 Gap Analysis proposed the ReviewBundle entity (Gap 6) and ContextScope-enriched OperationContext (Gap 5). The first real-world integration exposed two gaps that these proposals did not fully address:

1. **ReviewBundle lacks a lifecycle contract.** The entity was defined but the agent-facing workflow — how to poll for review, what happens on approval vs. rejection, retry semantics — was left implicit.
2. **OperationContext is static.** It returns schema metadata but not live system state. Agents cannot ask "can I do this right now?" — only "does this action exist?"

This specification adds the lifecycle contract and the dynamic enrichment.

---

## 2. ReviewBundle Lifecycle Contract

### 2.1 Lifecycle States

The ReviewBundle transitions through the following states:

```
                                  ┌──────────────┐
                                  │   assembling  │
                                  └──────┬───────┘
                                         │ assembly complete
                                         ▼
                                  ┌──────────────┐
                          ┌───────│pending_review │───────┐
                          │       └──────┬───────┘        │
                          │              │                │
                 approved │    revision  │                │ rejected
                          │   requested  │                │
                          ▼              ▼                ▼
                   ┌──────────┐  ┌─────────────┐  ┌──────────┐
                   │ approved │  │  revision_   │  │ rejected │
                   │          │  │  requested   │  │          │
                   └──────────┘  └──────┬──────┘  └────┬─────┘
                                        │              │
                                        │ agent revises│ if retry_allowed
                                        │ and resubmits│
                                        ▼              ▼
                                  ┌──────────────┐
                                  │pending_review │ (new bundle, linked via parent_bundle_id)
                                  └──────────────┘
```

**Terminal states:** `approved`, `rejected` (when `retry_allowed = false`)

**Recyclable states:** `rejected` (when `retry_allowed = true`), `revision_requested` — the agent may create a new ReviewBundle linked to the previous one.

### 2.2 Agent-Facing Contract

#### Polling for Review Status

```
Endpoint:    /review/{bundle_id}/status
Method:      GET
Auth:        Session-authenticated (must be the session that created the bundle, or a reviewer)

Output (200 OK):
  bundle_id:          string
  bundle_status:      enum        # assembling | pending_review | approved | 
                                  # rejected | revision_requested
  reviewer_session_id: string?    # assigned reviewer (null if not yet assigned)
  review_notes:       string?     # reviewer comments (null if not yet reviewed)
  requested_changes:  array?      # structured change requests (for revision_requested)
  retry_allowed:      bool        # can the agent resubmit after rejection?
  retry_count:        integer     # number of resubmissions so far
  max_retries:        integer     # maximum allowed resubmissions
  parent_bundle_id:   string?     # previous bundle in retry chain (null if first submission)
  created_at:         timestamp
  reviewed_at:        timestamp?  # when review decision was made

Error responses:
  REVIEW_BUNDLE_NOT_FOUND (404)
  SESSION_EXPIRED (401)
```

### 2.3 Dynamic OperationContext Enrichment

The OperationContext endpoint now includes live session state and guard evaluations:

```
Endpoint:    /operation-context/{action_name}
Method:      GET
Auth:        Session-authenticated

Input:
  session_id:         string     # REQUIRED
  action_name:        string     # path parameter

Output (200 OK):
  session_id:         string
  action_name:        string
  action_family:      string
  minimum_trust_tier: integer
  cost:               integer
  input_schema:       object     # JSON Schema
  output_schema:      object     # JSON Schema
  guards:             array      # guard names
  trust_sufficient:   bool       # session.trust_tier >= action.minimum_trust_tier
  budget_remaining:   integer    # session.remaining_budget
  guard_evaluations:  array      # live guard results
    [
      {
        guard_name:    string
        passed:        bool
        reason:        string?   # if failed
      }
    ]
  can_execute:        bool       # overall feasibility
  session_expires_at: timestamp

Error responses:
  SESSION_NOT_FOUND (404)
  ACTION_NOT_FOUND (404)
```

**Key improvements in v0.5:**
- Live session state (trust, budget, expiration)
- Guard pre-evaluation with parameter-independent checks
- Overall feasibility assessment (`can_execute`)
- JSON Schema Draft 2020-12 compliance
    "reviewer_notes": "The output contains incorrect formatting in the summary section",
    "retry_allowed": true,
    "attempt_number": 1,
    "max_retries": 3
  }
}
```

If `retry_allowed = true`, the agent MAY:
1. Address the issues described in `reviewer_notes`
2. Re-execute the relevant actions
3. Create a new ReviewBundle with `parent_bundle_id` referencing the rejected bundle
4. The new bundle enters `pending_review`

If `retry_allowed = false`, the agent MUST escalate. No further resubmission is permitted.

**On `revision_requested`:**

The pipeline returns `REVISION_REQUESTED`:

```json
{
  "code": "REVISION_REQUESTED",
  "severity": "informational",
  "agent_should": "recheck",
  "requires_context_refresh": true,
  "detail": {
    "bundle_id": "rb_abc123",
    "requested_changes": [
      { "area": "summary", "change": "Include error count breakdown" },
      { "area": "risk_assessment", "change": "Recalculate with updated thresholds" }
    ],
    "reviewer_notes": "Good work overall, but the summary needs more detail"
  }
}
```

The agent SHOULD address the `requested_changes` and create a new ReviewBundle.

### 2.3 ReviewBundle as a Guard Predicate

ReviewBundle approval can be wired as a guard on downstream actions. This is the primary mechanism for human-in-the-loop governance:

```
ActionContract: deploy.change_request
  guards:
    - "review_approved"
    - "staging_test_passed"
  ...

Guard Registry:
  "review_approved":
    (parameters, session, action_contract) →
      Look up ReviewBundle for the current workflow/dispatch
      If bundle_status == "approved" → passed: true
      If bundle_status != "approved" → passed: false, reason: "ReviewBundle {id} has status {status}"
```

This creates a governed gate: the agent cannot deploy until a human has reviewed and approved the work.

### 2.4 Webhook Notification (Optional)

Instead of polling, implementations MAY support push notification of review decisions:

```
Endpoint:    /review/{bundle_id}/subscribe
Method:      POST

Input:
  callback_url:    string    # URL to POST the review decision to
  events:          array     # which events to subscribe to: ["approved", "rejected", "revision_requested"]

Behavior:
  When the reviewer makes a decision, POST to callback_url with:
  {
    bundle_id:       string
    event:           string     # "approved" | "rejected" | "revision_requested"
    review_notes:    string?
    requested_changes: array?
    reviewed_at:     timestamp
  }
```

---

## 3. Dynamic OperationContext

### 3.1 Problem Statement

OperationContext (v0.3) returns the ActionContract metadata for a given action and resource. It tells the agent what the action's schema, guards, trust requirements, and cost look like. But it is **static** — it returns the same information regardless of the current session's budget state, guard evaluation results, or session health.

This means OperationContext is a "read the docs" endpoint, not a "can I do this right now?" endpoint. An agent that queries OperationContext and sees `allowed: true` may still get rejected at admission because its budget is exhausted, a guard fails, or its session is about to expire.

### 3.2 Extended OperationContext Response

OperationContext responses gain three new fields alongside the existing response body:

```
OperationContext Response (v0.5 extended):

  # === Existing v0.3 fields (unchanged) ===
  action_contract:     ActionContract     # full action metadata
  allowed:             bool               # is this action available to this agent class?
  blocked_reasons:     array              # why the action is blocked (if blocked)
  trust_constraints:   object             # trust tier requirements

  # === v0.4 addition (unchanged) ===
  active_scopes:       array              # ContextScope matches from v0.4 Gap 5

  # === v0.5 additions (NEW) ===
  budget_snapshot:     BudgetSnapshot     # live budget assessment for this action
  guard_pre_eval:      array              # dry-run guard evaluation
  session_constraints: SessionConstraints # session health and lifetime info
```

### 3.3 BudgetSnapshot

```
BudgetSnapshot:
  can_afford:            bool       # does the session have sufficient budget for this action?
  estimated_cost:        number     # the action's declared cost
  cost_category:         string     # which budget category this cost draws from
  remaining_in_category: number     # how much remains in that category
  circuit_breaker_state: enum       # closed | open | half_open — for this action's family
  warning:               string?    # advisory (e.g., "budget is >80% consumed for this category")
```

### 3.4 Guard Pre-Evaluation

```
GuardPreEvaluation:
  results:               array
    [
      {
        guard_name:      string     # name of the guard
        would_pass:      bool       # dry-run evaluation result
        reason:          string?    # explanation (especially useful on would-fail)
        staleness_warning: bool     # true if this guard is stateful and result may 
                                    # differ at actual admission time
      }
    ]
  all_would_pass:        bool       # convenience roll-up: true if all guards would pass
  evaluated_at:          timestamp  # when the pre-evaluation was performed
  note:                  string     # always: "This is a point-in-time evaluation. 
                                    # Results may differ at actual admission time."
```

**IMPORTANT:** Guard pre-evaluation is a **dry run**. It evaluates the guards against current system state **without creating an Intent**. Some guards may be stateful (e.g., checking if a service is healthy — it could go down between pre-eval and actual admission). The response MUST include the `note` field reminding agents that pre-eval is advisory.

Guards that are known to be stateful (e.g., they query external services, check real-time resource availability) SHOULD set `staleness_warning: true`. Guards that check static conditions (e.g., trust tier comparison, capability membership) SHOULD set `staleness_warning: false`.

### 3.5 SessionConstraints

```
SessionConstraints:
  expires_in_ms:               integer     # ms until session expires
  extensions_remaining:        integer     # how many more refreshes are available
  max_lifetime_remaining_ms:   integer     # ms until absolute max lifetime
  session_status:              enum        # active | expiring_soon | near_max_lifetime
  recommendation:              string?     # advisory: e.g., "Consider refreshing session 
                                           # before submitting long-running actions"
```

The `session_status` field uses these thresholds:
- `active`: > 20% of TTL remaining
- `expiring_soon`: 5–20% of TTL remaining
- `near_max_lifetime`: < 5% of max lifetime remaining

### 3.6 Composite Planning Assessment

The dynamic OperationContext now enables a **composite readiness assessment**. An agent can check all three dimensions in one call:

```
Can I do action X on resource Y right now?

  ✓ allowed:             true       (trust and capability check)
  ✓ budget_snapshot:     can_afford: true
  ✓ guard_pre_eval:      all_would_pass: true
  ✓ session_constraints: session_status: active
  
  → YES: high confidence that admission will succeed
```

```
Can I do action X on resource Y right now?

  ✓ allowed:             true
  ✗ budget_snapshot:     can_afford: false (remaining: 12, cost: 25)
  ✓ guard_pre_eval:      all_would_pass: true
  ⚠ session_constraints: session_status: expiring_soon
  
  → NO: budget insufficient. agent_should: wait for budget replenishment.
       Also: session is expiring — consider refreshing.
```

This turns OperationContext from a documentation query into a **planning oracle**.

### 3.7 Performance Considerations

The dynamic fields add computational cost to OperationContext responses:

- **BudgetSnapshot**: Requires a ledger read. Implementations SHOULD cache ledger state per-request (not cross-request) to avoid repeated database hits when querying multiple actions.
- **GuardPreEvaluation**: Requires executing all guard callables. For guards that make external calls, this may be slow. Implementations SHOULD:
  - Offer a `skip_guard_pre_eval=true` query parameter to skip this field
  - Cache guard results with a declared TTL for guards that explicitly opt in
  - Set a timeout for guard pre-evaluation (recommended: 5 seconds aggregate)
- **SessionConstraints**: Trivial — reads from session metadata. No caching concerns.

Implementations MAY offer `fields` query parameter to select which dynamic fields to include:

```
GET /context?action=scan.static_analysis&resource=repo_123&fields=budget_snapshot,session_constraints
```

This lets agents that only need budget information skip the cost of guard pre-evaluation.

---

## 4. Relationship to v0.4 Proposals

| v0.4 Proposal | This Specification |
|---|---|
| **Gap 5: ContextScope** | Unchanged. `active_scopes` field on OperationContext is preserved. The new v0.5 fields are **additional** — they appear alongside `active_scopes`, not instead of it. |
| **Gap 6: ReviewBundle** | The entity definition is preserved. This spec adds the **lifecycle contract** (§2) that v0.4 left implicit. The entity fields from v0.4 are canonical; this spec adds the behavioral rules and agent-facing endpoints. |

---

*End of ReviewBundle Lifecycle & Dynamic OperationContext. This document is normative for all CONCORD v0.5+ implementations.*
