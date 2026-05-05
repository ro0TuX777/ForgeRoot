# CONCORD v0.5 — Runtime Endpoint Contracts

**Status:** Normative | **Version:** 0.5.1 | **Date:** April 2026  
**Extends:** CONCORD v0.3 Runtime Contract Schemas  
**Amended by:** SAM integration lessons (v0.5.1) — SDK Client Contract, deployment readiness hardening  

---

## 1. Purpose

CONCORD v0.3 defines runtime contracts for OperationContext (planning surface) and Intent (admission unit). It does not define runtime endpoints for:

- **Budget introspection** — agents cannot see their remaining budget, forcing blind intent submission
- **Session lifecycle management** — sessions expire with no refresh mechanism, breaking long-running workflows

This specification adds these endpoints to the Runtime Contract Schemas.

---

## 2. Budget Introspection

### 2.1 Problem Statement

The BudgetLedger is a write-path entity — costs are deducted on receipt minting, and circuit breakers are tripped on threshold violations. But there is no read-path endpoint. An agent cannot query its remaining budget before planning a workflow. It must submit intents and discover budget exhaustion only when the BudgetGate (Admission Pipeline stage ④) rejects the request.

This makes intelligent workflow planning impossible. An agent planning a 5-step workflow cannot determine whether it has budget for all 5 steps without attempting them.

### 2.2 Endpoint: Budget Status

```
Endpoint:    /budget/status
Method:      GET
Auth:        Session-authenticated (session_id in header or query)

Input:
  session_id:         string     # REQUIRED — the session to query

Output (200 OK):
  budget_profile_id:  string     # which BudgetProfile governs this session
  fleet_id:           string?    # if fleet-governed, the fleet drawing from shared budget
  categories:         array      # per-category budget breakdown
    [
      {
        category:       string   # budget category (e.g., "compute", "api_calls", "mutations")
        total:          number   # total budget for this category
        consumed:       number   # amount consumed so far
        remaining:      number   # total - consumed
        unit:           string   # cost unit label (e.g., "risk_weighted_units", "api_calls")
      }
    ]
  circuit_breakers:   array      # per-action-family circuit breaker state
    [
      {
        action_family:  string   # e.g., "mutate", "deploy"
        state:          enum     # closed | open | half_open
        trips_count:    integer  # number of times tripped this session
        last_tripped:   timestamp? # when the breaker last opened
        cooldown_remaining_ms: integer? # ms until breaker resets (if open)
      }
    ]
  active_leases:      integer    # count of currently held resource leases
  session_id:         string     # echo back for confirmation

Error responses:
  SESSION_NOT_FOUND (404) — session_id does not resolve
  SESSION_EXPIRED (401)   — session has expired
```

### 2.3 Endpoint: Budget Estimate

This endpoint is **REQUIRED** for full agent planning capability. It allows agents to check feasibility of planned workflows without submitting intents.

```
Endpoint:    /budget/estimate
Method:      GET
Auth:        Session-authenticated (session_id in query)

Input:
  session_id:         string     # REQUIRED — the session to query
  action_name:        string     # REQUIRED — the action to estimate

Output (200 OK):
  session_id:         string     # echo back
  action_name:        string     # echo back
  cost:               integer    # estimated cost of one execution
  trust_sufficient:   bool       # session trust tier meets action minimum
  budget_sufficient:  bool       # remaining budget >= cost
  remaining_budget:   integer    # current remaining budget
  guard_evaluations:  array      # guard check results (may be incomplete without parameters)
    [
      {
        guard_name:    string
        passed:        bool?     # null if parameters unavailable for check
        reason:        string?   # failure reason
      }
    ]
  can_execute:        bool       # overall feasibility (trust + budget + guards)

Error responses:
  SESSION_NOT_FOUND (404)
  ACTION_NOT_FOUND (404)
  SESSION_EXPIRED (401)
```

### 2.4 Endpoint: Receipt Retrieval

```
Endpoint:    /receipt/{receipt_id}
Method:      GET
Auth:        Session-authenticated (must be the session that generated the receipt)

Input:
  receipt_id:         string     # path parameter

Output (200 OK):
  receipt_id:         string
  session_id:         string
  intent_id:          string
  action_name:        string
  status:             string     # "completed"
  result_summary:     object?    # normalized output
  validation_passed:  bool
  validation_errors:  array      # any schema validation errors
  idempotency_key:    string?
  cost_deducted:      integer
  created_at:         timestamp

### 2.4 Endpoint: Receipt Retrieval

```
Endpoint:    /receipt/{receipt_id}
Method:      GET
Auth:        Session-authenticated (must be the session that generated the receipt)

Input:
  receipt_id:         string     # path parameter

Output (200 OK):
  receipt_id:         string
  session_id:         string
  intent_id:          string
  action_name:        string
  status:             string     # "completed"
  result_summary:     object?    # normalized output
  validation_passed:  bool
  validation_errors:  array      # any schema validation errors
  idempotency_key:    string?
  cost_deducted:      integer
  created_at:         timestamp

Error responses:
  RECEIPT_NOT_FOUND (404)
  SESSION_EXPIRED (401)
```

---

## 3. Implementation Notes

### 3.1 Planning Endpoint Semantics

Planning endpoints (`/operation-context`, `/budget/estimate`) evaluate guards with `passed: null` when parameters are unavailable. This indicates the guard cannot be fully assessed without runtime data.

### 3.2 Receipt Validation

Receipts validate output against ActionContract `output_schema` using JSON Schema Draft 2020-12. Validation failures are recorded but do not prevent operation success — agents receive results with warnings.

### 3.3 Session Isolation in Testing

For reliable testing, create fresh sessions with descriptive IDs (e.g., `"session-test-scenario"`) to avoid state pollution between test cases.
```
  blocked_by_circuit: array?     # actions whose action_family has an open circuit breaker
    [
      {
        action_name:    string
        action_family:  string
        breaker_state:  enum
      }
    ]
  warnings:           array?     # advisory messages (e.g., "budget is >80% consumed")

Error responses:
  SESSION_NOT_FOUND (404)
  SESSION_EXPIRED (401)
  ACTION_NOT_FOUND (400) — one or more planned_actions references an unknown ActionContract
```

### 2.4 Normative Rules

1. **Budget status MUST reflect real-time ledger state.** The response MUST NOT be cached beyond the current request. Outstanding intents in `executing` status that have not yet minted receipts SHOULD be noted (their cost is pending but not yet deducted).

2. **Budget estimate is advisory.** The estimate is calculated at query time. Between the estimate response and actual intent submission, the budget may change (other intents may complete and deduct cost, circuit breakers may trip). The agent MUST NOT treat a feasible estimate as a guarantee.

3. **Fleet-level budget.** If the session is part of a TaskFleet (v0.4), the budget status MUST report the fleet-level budget, not the individual session budget. Individual session budgets are subordinate to fleet budgets.

---

## 3. Session Refresh

### 3.1 Problem Statement

Sessions have TTLs (`expires_at`). Long-running agent workflows — multi-step, multi-hour task sequences — can outlast their session. Currently, when a session expires mid-task, all subsequent intents fail with `SESSION_EXPIRED`. The agent has no way to extend the session and must escalate for a new session, losing workflow context.

### 3.2 Endpoint: Session Refresh

```
Endpoint:    /session/refresh
Method:      POST
Auth:        Session-authenticated (the session refreshing itself, or a higher-trust session)

Input:
  session_id:              string    # REQUIRED — the session to refresh
  requested_extension_ms:  integer   # REQUIRED — how many ms to extend expires_at by

Output (200 OK):
  session_id:              string    # echo back for confirmation
  old_expires_at:          timestamp # previous expiry time
  new_expires_at:          timestamp # updated expiry time
  extensions_count:        integer   # total number of extensions this session has received
  max_extensions:          integer   # maximum allowed extensions (from policy)
  max_lifetime_at:         timestamp # absolute hard ceiling — no extensions beyond this
  remaining_extensions:    integer   # max_extensions - extensions_count
  refresh_receipt_id:      string    # Receipt ID for audit trail

Error responses:
  SESSION_NOT_FOUND (404)          — session_id does not resolve
  SESSION_EXPIRED (401)            — session has already expired (cannot refresh expired sessions)
  SESSION_MAX_LIFETIME_REACHED (403) — refresh would exceed the max_lifetime cap
  TRUST_INSUFFICIENT (403)         — requester does not have authority to refresh this session
```

### 3.3 Normative Rules

1. **Refresh MUST NOT create a new session.** The `session_id` is unchanged. All existing intent history, budget accounting, and lease assignments remain bound to the same session.

2. **Refresh is an auditable event.** Every refresh MUST produce a Receipt with:
   - `action_name: "session.refresh"` (this is a system action, not a host-application action)
   - `result_summary: { old_expires_at, new_expires_at, extensions_count }`
   - The receipt is stored in the session's receipt history

3. **Maximum lifetime cap.** Every Session MUST have a `max_lifetime_at` timestamp (set at session creation). **No** refresh request may extend `expires_at` beyond `max_lifetime_at`. If the requested extension would exceed max lifetime, the endpoint MUST:
   - Shorten the extension to `max_lifetime_at` (if the session is not already at max lifetime)
   - Or return `SESSION_MAX_LIFETIME_REACHED` (if the session is already at max lifetime)

4. **Maximum extension count.** Sessions SHOULD have a `max_extensions` policy limit. This prevents indefinite session extension by runaway workflows. The default SHOULD be configurable per AgentClass.

5. **Only the session owner or a higher-trust session may refresh.** A T1 agent cannot refresh a T3 session. Self-refresh (the session refreshing itself) is always permitted for active sessions.

6. **Expired sessions cannot be refreshed.** If the session has already reached `expired` status, the refresh endpoint returns `SESSION_EXPIRED`. The agent must request a new session. This prevents resurrection of sessions that may have had their resources released.

### 3.4 Session Policy Extension

The Session entity (v0.3 Core Spec §3) gains these new fields:

```
Additional Session fields (v0.5):
  max_lifetime_at:       timestamp   # absolute hard ceiling for this session
  max_extensions:        integer     # maximum number of refresh operations
  extensions_count:      integer     # current count of completed refreshes
  last_refreshed_at:     timestamp?  # timestamp of most recent refresh
```

These fields are set at session creation based on the AgentClass policy and are immutable (except `extensions_count` and `last_refreshed_at`, which are updated on each refresh).

---

## 4. Relationship to Admission Pipeline

Both endpoints defined here are **planning-time** endpoints, not admission pipeline stages. They exist alongside OperationContext as agent planning surfaces:

```
Planning Surface (pre-admission):
  OperationContext  — "What can I do with this resource?"
  Budget Status     — "How much budget do I have left?"
  Budget Estimate   — "Can I afford this plan?"
  Session Refresh   — "Keep my session alive for more work"

Admission Pipeline (intent processing):
  ① Session → ② Action → ③ Trust → ④ Budget → ⑤ Guard → ⑥ Input → ⑦ Idempotency
  → ⑧ Intent → ⑨ Execute → ⑩ Normalize → ⑪ Receipt
```

Budget Status and Budget Estimate are **read-only** operations that do not create Intents and do not pass through the admission pipeline. They are governance-safe queries.

Session Refresh is a **system action** that does produce an audit Receipt, but it does not flow through the full admission pipeline (it is a self-referential session operation, not a host-application action).

---

## 5. Deployment Readiness

### 5.1 Problem Statement

After Phase 4 (Post-Deploy Readiness) completes, the connection manifest is a static file. But deployment state changes at runtime — containers restart, ports get released, health degrades. Consuming agents need a **live query** to verify deployment health before configuring their SDKs.

### 5.2 Endpoint: Deploy Status

```
Endpoint:    /deploy/status
Method:      GET
Auth:        Deployment token (not session auth, not fully open — see §5.3 rule 3)

Output (200 OK):
  application_name:    string     # CONCORD registration name
  concord_version:     string     # CONCORD spec version
  status:              enum       # ready | degraded | not_ready
  base_port:           integer    # computed base port from name-derived algorithm
  manifest_generated:  bool       # whether a connection manifest exists
  manifest_path:       string     # relative path to connection_manifest.yaml
  manifest_generated_at: timestamp  # when the manifest was last generated
  
  required_configuration:  array  # all env/config this service depends on (v0.5.1)
    [
      {
        key:           string     # e.g., "GOVERNED_SERVICE_URL"
        required:      bool
        configured:    bool       # is this currently set?
        default:       string?    # default value if any
        description:   string     # what this config controls
      }
    ]
  
  storage:               object?  # file handling configuration (v0.5.1)
    {
      ingest_root:       string?  # filesystem root for file ingestion
      ingest_configured: bool     # is ingest root configured and accessible?
      managed_storage:   bool     # does service use managed storage?
      storage_model:     enum     # managed | external_ingest | hybrid
    }
  
  services:            array      # per-service health status
    [
      {
        name:              string   # human-readable service name
        status:            enum     # healthy | unhealthy | degraded | not_started
        url:               string   # service URL (from manifest)
        health_endpoint:   string   # health probe URL
        health_checked_at: timestamp  # when health was last verified
        container_name:    string   # docker container name
        external_port:     integer  # host port
      }
    ]
  
  guard_registry_complete: bool   # all declared guards have callables (v0.5.1)
  registered_actions:      integer # count of registered ActionContracts (v0.5.1)
  
  platform:
    os:                string     # windows | darwin | linux
    docker_desktop:    bool      # whether Docker Desktop is in use
    warnings:          array     # active platform-specific warnings
      [string]
  deployment_notes:
    port_remaps:           integer  # count of collision fallbacks applied
    platform_workarounds:  integer  # count of OS-specific fixes applied
    dependency_fixes:      integer  # count of build-time fixes applied
  
  degraded_reasons:      array?   # if status = degraded, why (v0.5.1)
    [
      {
        component:    string       # what is degraded
        reason:       string       # why
        impact:       string       # which actions are affected
      }
    ]

Error responses:
  503 Service Unavailable — Phase 4 has not been executed yet (no manifest exists)
```

### 5.3 Normative Rules

1. **Live health check.** The `/deploy/status` endpoint SHOULD perform a fresh health probe of all services when called, not return cached results from the manifest. If fresh probing is too expensive, the implementation MAY cache with a maximum TTL of 30 seconds.

2. **Pre-manifest state.** If Phase 4 has not been executed (no `connection_manifest.yaml` exists), the endpoint MUST return `503 Service Unavailable` with a body indicating that the Deployment Agent has not yet run.

3. **Deployment token authentication (v0.5.1).** The `/deploy/status` endpoint requires a deployment token — a lightweight credential separate from CONCORD session tokens. This prevents unauthenticated exposure of configuration state and registered action counts while still allowing infrastructure probes before session auth is configured.

4. **Consuming agent workflow.** The expected agent workflow is:
   ```
   1. Query /deploy/status
   2. If services are all healthy → parse connection_manifest.yaml for SDK configuration
   3. If any service is unhealthy → wait and retry, or report to operator
   4. Configure SDK with manifest's base_url and required_env
   5. Call client.health() to verify end-to-end connectivity
   ```

5. **Ingest root is a governance boundary (v0.5.1).** If file-accepting actions are registered but no ingest root is configured, `status` MUST be `degraded` with a clear diagnostic in `degraded_reasons`. The ingest root is not an implementation detail — agents operating under CONCORD need to know where they may and may not direct files.

6. **Guard registry completeness (v0.5.1).** If any declared guard lacks a registry entry, `guard_registry_complete` MUST be `false` and `status` MUST be `degraded`.

7. **Required configuration completeness (v0.5.1).** `required_configuration` MUST list ALL environment variables the service depends on, with their current configuration state (`configured: true/false`). This allows the consuming agent to perform a configuration completeness check before submitting any intents, rather than discovering missing configuration through runtime failures.

8. **Service URLs MUST use mesh-resolvable names (v0.5.1).** In containerized deployments, `services[].url` MUST default to a service-mesh-resolvable hostname (e.g., `http://governed-service:8080`), NEVER `localhost`. `localhost` inside a container resolves to the container itself, not the governed service. Container environment definitions for consuming services MUST explicitly set the governed service URL using the mesh-resolvable hostname.

---

## 6. Relationship to Admission Pipeline

All endpoints defined here are **planning-time** or **infrastructure-time** endpoints, not admission pipeline stages. They exist alongside the admission pipeline as support surfaces:

```
Infrastructure Surface (Phase 4):
  Deploy Status     — "Is the application running and reachable?"

Planning Surface (pre-admission):
  OperationContext  — "What can I do with this resource?"
  Budget Status     — "How much budget do I have left?"
  Budget Estimate   — "Can I afford this plan?"
  Session Refresh   — "Keep my session alive for more work"

Admission Pipeline (intent processing):
  ① Session → ② Action → ③ Trust → ④ Budget → ⑤ Guard → ⑥ Input → ⑦ Idempotency
  → ⑧ Intent → ⑨ Execute → ⑩ Normalize → ⑪ Receipt
```

Budget Status and Budget Estimate are **read-only** operations that do not create Intents and do not pass through the admission pipeline. They are governance-safe queries.

Deploy Status is an **infrastructure query** that does not require a CONCORD session. It verifies the prerequisites for the admission pipeline to function.

Session Refresh is a **system action** that does produce an audit Receipt, but it does not flow through the full admission pipeline (it is a self-referential session operation, not a host-application action).

---

## 7. SDK Client Contract (v0.5.1)

### 7.1 Problem Statement

CONCORD defines the server-side pipeline (admission stages, receipts, error catalog) but says nothing about what a **client SDK or adapter** should look like. Real-world integrations have produced client libraries where:

- Typed convenience wrappers (e.g., `client.analyze_pcap(...)`) silently discarded `receipt_id`, making audit trail correlation impossible without bypassing the SDK
- Health checks caught SDK import failures and reported them as "service unreachable" — a misclassification that sent debugging down the wrong path
- SDK paths injected across OS/container boundaries (Windows host → Linux container) failed silently because path validation didn't happen at initialization

This section defines the minimum contract for any client library, SDK, or adapter that wraps CONCORD intent submission.

### 7.2 Typed Wrapper Return Shape

Every typed action wrapper (convenience methods like `client.do_thing(...)`) MUST return the full CONCORD response envelope. Typed wrappers are convenience layers — they MUST NOT silently discard governance artifacts.

**Minimum return shape:**

```
TypedActionResult:
  success:        bool          # did the action complete successfully?
  receipt_id:     string        # ALWAYS present, even on failure
  intent_id:      string        # the admitted intent's ID
  result:         object        # normalized output (from output_schema)
  cost_deducted:  number        # budget cost charged
  error:          ConcordError? # classified error on failure (null on success)
```

**Rules:**

1. `receipt_id` MUST be present on every return, including failures. If the pipeline produced a receipt (stages ⑧–⑪ executed), the receipt_id from ReceiptMinting is used. If admission failed before IntentCreation (stages ①–⑦), the SDK MUST generate a client-side trace ID in the same field with a distinguishing prefix (e.g., `client_trace_...`) so the caller always has a correlation identifier.

2. `error` MUST use the CONCORD error catalog shape — `code`, `severity`, `agent_should`, `detail`. The raw HTTP status code or exception message MUST NOT be the primary error interface.

3. Typed wrappers MAY add convenience fields (e.g., domain-specific parsed results), but they MUST NOT remove or obscure the governance fields listed above.

### 7.3 Adapter Initialization Contract

SDK or adapter initialization MUST validate its prerequisites eagerly at construction time. Errors discovered during initialization MUST be surfaced as structured init errors, not deferred to runtime health checks.

**Initialization validation sequence:**

```
1. SDK availability:   Can the client library be imported?
                       If not → AdapterInitError(code: SDK_NOT_FOUND)

2. SDK path validity:  If an external SDK path was injected (e.g., via 
                       GOVERNED_SDK_PATH env var), does the path exist in 
                       the current runtime environment?
                       If not → AdapterInitError(code: SDK_PATH_NOT_FOUND)

3. URL resolvability:  Can the governed service URL be resolved via DNS?
                       (DNS check only, not a full health probe)
                       If not → AdapterInitError(code: SERVICE_URL_UNRESOLVABLE)

4. Config completeness: Are all required config values present?
                       If not → AdapterInitError(code: CONFIG_MISSING)
```

**AdapterInitializationError shape:**

```
AdapterInitializationError:
  code:     enum      # SDK_NOT_FOUND | SDK_PATH_NOT_FOUND | 
                      # SERVICE_URL_UNRESOLVABLE | CONFIG_MISSING
  detail:   string    # human-readable explanation
  path:     string?   # the path that failed validation (if applicable)
  url:      string?   # the URL that failed resolution (if applicable)
  missing:  array?    # list of missing config keys (if applicable)
```

**Critical rule:** Init errors MUST NOT be surfaced as connectivity errors. An import failure (`SDK_NOT_FOUND`) is a different failure class from a network timeout (`SERVICE_URL_UNRESOLVABLE`). Conflating them sends debugging down the wrong path. This distinction was the root cause of a full debugging session in a real integration.

**Cross-environment path validation:** SDK path injection across OS or container boundaries (e.g., Windows host path injected into a Linux container via env var) is a known fragile pattern. The initialization sequence MUST validate path existence using the runtime's filesystem, not the config source's filesystem. If the path doesn't exist in the runtime environment, `SDK_PATH_NOT_FOUND` MUST be raised at init time with the injected path value in the error detail.

### 7.4 Health Check Contract

The client-side `is_healthy()` or `health()` method MUST distinguish between failure classes. A single boolean is insufficient — it conflates SDK problems, network problems, and pipeline problems into one opaque signal.

**Health check return shape:**

```
HealthCheckResult:
  healthy:        bool          # overall health verdict
  failure_class:  enum?         # null if healthy; one of the classes below if not
  detail:         string?       # human+agent readable explanation
  checked_at:     timestamp     # when the check was performed
```

**Failure classes:**

| Class | Meaning | Typical Cause |
|---|---|---|
| `sdk_unavailable` | Client library not importable in current runtime | SDK not installed, wrong Python path, missing native dependency |
| `service_unreachable` | Network/connection failure to the governed service | Container not running, DNS failure, firewall, wrong URL |
| `pipeline_not_ready` | Service reachable but pipeline not in ready state | Missing config, degraded dependencies, startup in progress |

**Rules:**

1. `is_healthy()` MUST check all three layers in order: SDK availability → network connectivity → pipeline readiness.
2. On first failure, `is_healthy()` MUST return with the specific `failure_class` — it MUST NOT attempt deeper checks (e.g., don't check pipeline readiness if the network is down).
3. The `detail` field SHOULD include enough information for an agent to decide its next action without log inspection.
4. Agent adapters MUST surface the `failure_class` in their structured error output so that agent consumers can route on failure class, not parse error messages.

---

*End of Runtime Endpoint Contracts. This document is normative for all CONCORD v0.5+ implementations.*
