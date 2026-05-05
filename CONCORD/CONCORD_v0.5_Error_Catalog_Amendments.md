# CONCORD v0.5 — Error Catalog Amendments

**Status:** Normative | **Version:** 0.5.1 | **Date:** April 2026  
**Amends:** CONCORD v0.3 Error and Conflict Code Catalog  
**Amended by:** SAM integration lessons (v0.5.1) — feature flag state codes  

---

## 1. Purpose

The CONCORD v0.3 Error and Conflict Code Catalog defines error codes with `severity` and `agent_should` fields. The first real-world integration revealed two problems:

1. **Not all error codes have `agent_should` guidance.** Some entries are missing this field, forcing agents to guess how to respond to errors.
2. **No exception mapping pattern exists.** Integration agents must catch host-application exceptions and translate them into CONCORD error responses, but there is no guidance on how to do this systematically.

This amendment makes `agent_should` a required field on all entries and introduces the Exception Mapping Pattern.

---

## 2. Amendment 1: `agent_should` Is Now Required

### Rule

Every entry in the Error and Conflict Code Catalog MUST include the `agent_should` field. This field is **REQUIRED**, not optional.

An error catalog entry without `agent_should` is a specification violation.

### Rationale

`agent_should` is one of CONCORD's strongest features — it gives agents precise behavioral guidance for self-correction without human intervention. When this field is absent, agents receiving the error must either:
- Guess the appropriate response (unreliable)
- Escalate everything to a human (defeats the purpose of agent autonomy)

Neither outcome is acceptable in a governed system.

### Valid `agent_should` Values

The following values are normative. Implementations MUST NOT invent additional values.

| Value | Agent Behavior |
|---|---|
| `retry` | Retry the same action immediately or after `retry_delay_hint_ms`. The error is transient. |
| `recheck` | Refresh OperationContext and re-evaluate whether the action is appropriate. Parameters, preconditions, or context may have changed. |
| `wait` | The blocking condition is expected to resolve over time (budget cooldown, circuit breaker, resource lock). Poll or wait before retrying. |
| `queue` | Submit the action for deferred execution. The system will process it when conditions allow. |
| `escalate` | The agent cannot resolve this error autonomously. Flag for human review. |
| `report` | Log the error and continue with the workflow (skip this action). The error is informational or the action is non-critical. |
| `abort` | Stop the current workflow entirely. The error is unrecoverable without human intervention. |
| `compensate` | Trigger the compensation/rollback flow for actions already completed in this workflow. |

### Audit of Existing Entries

All existing v0.3 error catalog entries that are missing `agent_should` MUST be updated. The following table provides the required additions for v0.3 entries that lacked this field:

| Error Code | Added `agent_should` | Rationale |
|---|---|---|
| `LEASE_CONFLICT` | `wait` | Resource contention — wait for lease to release |
| `CONSISTENCY_VIOLATION` | `recheck` | State has diverged — refresh and re-evaluate |
| `SAGA_COMPENSATION_FAILED` | `escalate` | Compensation failure requires human resolution |
| `INTERNAL_ERROR` | `report` | System-level failure unrelated to agent behavior |

*(If additional v0.3 entries are found missing `agent_should` during implementation, apply the same pattern: choose the value that best represents the agent's optimal response.)*

---

## 3. Amendment 2: New Error Codes

The Admission Pipeline Specification (v0.5) introduces the following new error codes. Each is listed here with its full catalog entry.

### 3.1 `ACTION_DEPRECATED`

```yaml
code: ACTION_DEPRECATED
category: admission
severity: warning
retryable: false
agent_should: recheck
requires_context_refresh: true
blocks_other_actions: false
description: >
  The requested action exists in the ActionContract registry but has been 
  marked as deprecated. The agent should query ActionDiscovery or 
  OperationContext for the replacement action.
detail_schema:
  deprecated_action: string    # the action that was requested
  replacement_action: string?  # the recommended replacement, if known
  deprecated_since: timestamp  # when the action was deprecated
  removal_date: timestamp?     # when the action will be removed, if known
```

### 3.2 `GUARD_NOT_REGISTERED`

```yaml
code: GUARD_NOT_REGISTERED
category: configuration
severity: critical
retryable: false
agent_should: report
requires_context_refresh: false
blocks_other_actions: true
description: >
  A guard declared on the ActionContract has no corresponding entry in the 
  Guard Registry. This is a configuration error in the host application's 
  CONCORD integration, not a runtime condition. The agent cannot resolve 
  this — it must be reported.
detail_schema:
  missing_guard: string        # the guard name that lacks registration
  action_name: string          # the ActionContract that declares the guard
```

### 3.3 `INVALID_PARAMETERS`

```yaml
code: INVALID_PARAMETERS
category: admission
severity: warning
retryable: false
agent_should: recheck
requires_context_refresh: true
blocks_other_actions: false
description: >
  The intent's parameters do not satisfy the ActionContract's input_schema. 
  Missing required fields, type mismatches, or constraint violations were 
  detected. The agent should review the ActionContract's input_schema 
  (via OperationContext) and correct its parameters.
detail_schema:
  missing_fields: array        # field names that are required but absent
  invalid_fields: array        # objects: { field, expected, received, constraint? }
  extra_fields: array          # field names present but not in schema (warning only)
```

### 3.4 `INTENT_CREATION_FAILED`

```yaml
code: INTENT_CREATION_FAILED
category: system
severity: elevated
retryable: true
retry_delay_hint_ms: 1000
agent_should: retry
requires_context_refresh: false
blocks_other_actions: false
description: >
  The system failed to persist the Intent record. This is a transient 
  infrastructure error (database unavailable, write timeout). The intent 
  passed all admission checks — retrying should succeed.
```

### 3.5 `EXECUTION_TIMEOUT`

```yaml
code: EXECUTION_TIMEOUT
category: execution
severity: elevated
retryable: true
retry_delay_hint_ms: 5000
agent_should: retry
requires_context_refresh: false
blocks_other_actions: false
description: >
  The executor exceeded the action's maximum execution time. The host 
  application's operation timed out. The agent may retry, but should 
  consider whether the operation is inherently long-running and adjust 
  expectations accordingly.
detail_schema:
  timeout_ms: integer          # the configured timeout
  elapsed_ms: integer          # how long execution ran before timeout
```

### 3.6 `OUTPUT_NORMALIZATION_FAILED`

```yaml
code: OUTPUT_NORMALIZATION_FAILED
category: system
severity: informational
retryable: false
agent_should: report
requires_context_refresh: false
blocks_other_actions: false
description: >
  The action executed successfully, but the executor's raw output could 
  not be normalized to match the ActionContract's output_schema. The 
  Receipt contains the raw, unnormalized output. This is a non-fatal 
  warning — the agent received data, but it may not match the expected 
  schema shape.
detail_schema:
  normalization_errors: array  # what went wrong during normalization
  raw_output_type: string      # the type/shape of the raw output
```

### 3.7 `SESSION_MAX_LIFETIME_REACHED`

```yaml
code: SESSION_MAX_LIFETIME_REACHED
category: session
severity: warning
retryable: false
agent_should: escalate
requires_context_refresh: false
blocks_other_actions: true
description: >
  The session has reached its maximum lifetime cap. No further extensions 
  are possible. The agent must request a new session or escalate to a 
  human operator for workflow continuation.
detail_schema:
  session_id: string
  max_lifetime_ms: integer
  total_elapsed_ms: integer
  extensions_count: integer
```

### 3.8 `REVIEW_REJECTED`

```yaml
code: REVIEW_REJECTED
category: review
severity: elevated
retryable: false
agent_should: recheck
requires_context_refresh: true
blocks_other_actions: true
description: >
  A ReviewBundle submitted for human review was rejected. The agent 
  should read the reviewer's notes and determine whether the work can 
  be revised and resubmitted.
detail_schema:
  bundle_id: string
  reviewer_notes: string
  retry_allowed: bool
  max_retries: integer?
  attempt_number: integer
```

### 3.9 `REVISION_REQUESTED`

```yaml
code: REVISION_REQUESTED
category: review
severity: informational
retryable: false
agent_should: recheck
requires_context_refresh: true
blocks_other_actions: false
description: >
  A human reviewer has requested specific changes to the agent's work 
  before approving the ReviewBundle. The agent should address the 
  requested changes and resubmit.
detail_schema:
  bundle_id: string
  requested_changes: array     # structured list of requested modifications
  reviewer_notes: string?
```

### 3.10 `DEPLOY_PORT_CONFLICT`

```yaml
code: DEPLOY_PORT_CONFLICT
category: deploy
severity: warning
retryable: false
agent_should: recheck
requires_context_refresh: false
blocks_other_actions: false
description: >
  A port computed by the deterministic port assignment algorithm is 
  already occupied on the host. The Deployment Agent applied the 
  collision fallback (increment by 100) and assigned an alternative port.
  The connection manifest reflects the actual assigned port.
detail_schema:
  application_name: string     # the CONCORD registration name
  computed_port: integer        # the port the algorithm produced
  occupied_by: string?          # process or container using the port, if detectable
  fallback_port: integer        # the alternative port assigned
  service_name: string          # which service was remapped
```

### 3.11 `DEPLOY_BUILD_FAILED`

```yaml
code: DEPLOY_BUILD_FAILED
category: deploy
severity: elevated
retryable: false
agent_should: report
requires_context_refresh: false
blocks_other_actions: true
description: >
  The `docker compose build` command failed. The Deployment Agent 
  classified the failure but could not auto-resolve it. The build 
  error must be fixed before the application can be deployed.
detail_schema:
  failure_class: string         # dependency_resolution | network_error | 
                                # dockerfile_syntax | base_image_unavailable
  service_name: string          # which service's build failed
  error_output: string          # last 50 lines of build output
  attempted_fixes: array?       # any auto-fix attempts and their results
```

### 3.12 `DEPLOY_HEALTH_TIMEOUT`

```yaml
code: DEPLOY_HEALTH_TIMEOUT
category: deploy
severity: elevated
retryable: true
retry_delay_hint_ms: 10000
agent_should: retry
requires_context_refresh: false
blocks_other_actions: true
description: >
  A service failed to pass its health probe within the configured 
  timeout after `docker compose up`. The container may be crash-looping, 
  stuck on startup, or misconfigured. Container logs are attached.
detail_schema:
  service_name: string          # which service failed health check
  container_name: string        # docker container name
  health_endpoint: string       # the endpoint that was probed
  timeout_ms: integer           # how long the probe waited
  container_logs: string        # last 50 lines of container logs
  container_status: string      # docker container status (running, exited, restarting)
```

### 3.13 `DEPLOY_PLATFORM_INCOMPATIBLE`

```yaml
code: DEPLOY_PLATFORM_INCOMPATIBLE
category: deploy
severity: warning
retryable: false
agent_should: recheck
requires_context_refresh: false
blocks_other_actions: false
description: >
  A platform-specific incompatibility was detected in the Docker 
  configuration. The Deployment Agent applied a remediation (e.g., 
  switching network_mode from host to bridge on Docker Desktop).
  The deployment may proceed but the configuration was modified.
detail_schema:
  platform: string              # windows | darwin | linux
  docker_desktop: bool          # whether Docker Desktop is in use
  incompatibility: string       # what was detected
  remediation_applied: string   # what the Deployment Agent changed
  compose_file_modified: bool   # whether docker-compose.yml was edited
```

### 3.14 `DEPLOY_MANIFEST_STALE`

```yaml
code: DEPLOY_MANIFEST_STALE
category: deploy
severity: informational
retryable: false
agent_should: recheck
requires_context_refresh: false
blocks_other_actions: false
description: >
  A connection manifest exists but its contents do not match the 
  current deployment state. Services may have been added, removed, 
  or restarted since the manifest was generated. The Deployment Agent 
  should regenerate the manifest.
detail_schema:
  manifest_generated_at: timestamp  # when the existing manifest was created
  stale_services: array             # services whose status has changed
  action: string                    # regenerate | warn
```

### 3.15 `ACTION_DISABLED` (v0.5.1)

```yaml
code: ACTION_DISABLED
category: operational_state
severity: informational
retryable: false
agent_should: report
requires_context_refresh: false
blocks_other_actions: false
description: >
  The action exists in the ActionContract registry and the agent has 
  sufficient trust, but it is currently disabled via feature flag or 
  administrative control. This is an intentional operational decision, 
  not a failure or availability event. The agent should report this 
  to the operator and continue with alternative actions if available.
  This code is DISTINCT from ACTION_UNAVAILABLE — disabled means 
  intentionally turned off; unavailable means unable to run.
detail_schema:
  action_name:          string      # the disabled action
  disabled_by:          enum        # feature_flag | admin_override | maintenance
  disabled_since:       timestamp?  # when the action was disabled
  expected_reenabled:   timestamp?  # when re-enablement is expected, if known
  alternative_action:   string?     # suggested alternative, if any
```

### 3.16 `ACTION_UNAVAILABLE` (v0.5.1)

```yaml
code: ACTION_UNAVAILABLE
category: operational_state
severity: warning
retryable: true
retry_delay_hint_ms: 10000
agent_should: wait
requires_context_refresh: true
blocks_other_actions: false
description: >
  The action exists, is enabled (not feature-flagged off), and the 
  agent has sufficient trust, but the underlying service or resource 
  is currently not available. This is a transient operational condition, 
  not an intentional decision. The agent should wait and retry.
  This code is DISTINCT from ACTION_DISABLED — unavailable means 
  unable to run right now; disabled means intentionally turned off.
detail_schema:
  action_name:          string      # the unavailable action
  unavailable_reason:   string      # why the action can't run
  retry_after_ms:       integer?    # suggested retry interval
  dependency:           string?     # which dependency is unavailable
```

---

## 4. Amendment 3: Exception Mapping Pattern

### 4.1 The Problem

When integrating a host application with CONCORD, the executor catches exceptions thrown by the host application's business logic. These exceptions are domain-specific (database errors, network timeouts, file system errors, authentication failures, business rule violations) and have no inherent mapping to CONCORD error codes.

Without guidance, integration agents handle this inconsistently:
- Some let raw tracebacks escape to the agent consumer
- Some map every exception to `EXECUTION_FAILED` (losing diagnostic specificity)
- Some invent ad-hoc error codes not in the catalog

### 4.2 The Exception Mapping Contract

Every executor implementation MUST provide an **exception mapping table** as part of its integration configuration.

**Structure:**

```
ExceptionMapping:
  host_exception_type:       string     # the exception class name or class hierarchy
  concord_error_code:        string     # CONCORD error catalog code
  agent_should:              string     # agent behavioral guidance
  severity:                  string     # error severity level
  requires_context_refresh:  bool       # should the agent refresh context?
  extract_detail:            callable?  # optional: extract structured detail from 
                                        # the exception instance
```

### 4.3 Normative Rules

1. **No raw exceptions may escape the executor boundary.** Every exception thrown by host application code MUST be caught by the executor and translated to a CONCORD error response.

2. **Default handler required.** The mapping table MUST include a catch-all entry for unmatched exceptions. The default mapping SHOULD use:
   - `concord_error_code: EXECUTION_FAILED`
   - `agent_should: report`
   - `severity: elevated`

3. **Host exception messages are diagnostic, not guidance.** The original exception message SHOULD be included in the error response's `detail` object under a `host_exception_message` key for debugging and telemetry. But it MUST NOT be the primary agent guidance — agents read `agent_should` and `code`, not exception messages.

4. **The mapping table SHOULD be declared alongside the ActionContract registry.** This makes exception handling auditable and reviewable. The mapping table is part of the integration's governance surface, not hidden in catch blocks.

5. **Exception class hierarchies SHOULD be respected.** If the host application throws `ConnectionTimeoutError` which inherits from `ConnectionError`, and the mapping table has an entry for `ConnectionError` but not `ConnectionTimeoutError`, the `ConnectionError` mapping SHOULD be used. More specific matches take precedence over less specific ones.

### 4.4 Example Mapping Table

```
┌─────────────────────────┬──────────────────────────┬───────────┬──────────┐
│ Host Exception          │ CONCORD Error Code       │ agent_    │ context_ │
│                         │                          │ should    │ refresh? │
├─────────────────────────┼──────────────────────────┼───────────┼──────────┤
│ ConnectionError         │ EXTERNAL_SERVICE_TIMEOUT  │ retry     │ false    │
│ TimeoutError            │ EXECUTION_TIMEOUT         │ retry     │ false    │
│ PermissionError         │ TRUST_INSUFFICIENT        │ escalate  │ false    │
│ FileNotFoundError       │ RESOURCE_NOT_FOUND        │ recheck   │ true     │
│ ValueError              │ INVALID_PARAMETERS        │ recheck   │ true     │
│ IntegrityError (DB)     │ IDEMPOTENCY_CONFLICT      │ wait      │ false    │
│ AuthenticationError     │ SESSION_EXPIRED           │ recheck   │ true     │
│ RateLimitError          │ BUDGET_EXCEEDED           │ wait      │ false    │
│ BusinessRuleViolation   │ GUARD_FAILED              │ recheck   │ true     │
│ *(any unmatched)*       │ EXECUTION_FAILED          │ report    │ false    │
└─────────────────────────┴──────────────────────────┴───────────┴──────────┘
```

### 4.5 Error Response Shape

Every error response produced by the executor through exception mapping MUST conform to this shape:

```json
{
  "code": "EXTERNAL_SERVICE_TIMEOUT",
  "severity": "elevated",
  "agent_should": "retry",
  "retryable": true,
  "retry_delay_hint_ms": 5000,
  "requires_context_refresh": false,
  "blocks_other_actions": false,
  "detail": {
    "host_exception_type": "ConnectionError",
    "host_exception_message": "Connection to analysis-engine:8080 timed out after 30s",
    "action_name": "scan.static_analysis",
    "mapped_by": "exception_mapping_table"
  }
}
```

---

## 5. Complete Error Catalog (v0.5)

For reference, the complete catalog after all v0.5 amendments is listed below. All entries include the now-required `agent_should` field.

### Admission Errors

| Code | Severity | agent_should | Stage |
|---|---|---|---|
| `SESSION_NOT_FOUND` | elevated | abort | ① |
| `SESSION_EXPIRED` | warning | recheck | ① |
| `SESSION_SUSPENDED` | elevated | escalate | ① |
| `SESSION_MAX_LIFETIME_REACHED` | warning | escalate | Session refresh |
| `ACTION_NOT_FOUND` | warning | recheck | ② |
| `ACTION_DEPRECATED` | warning | recheck | ② |
| `TRUST_INSUFFICIENT` | elevated | escalate | ③ |
| `BUDGET_EXCEEDED` | warning | wait | ④ |
| `CIRCUIT_OPEN` | warning | wait | ④ |
| `GUARD_FAILED` | warning | recheck | ⑤ |
| `GUARD_NOT_REGISTERED` | critical | report | ⑤ |
| `INVALID_PARAMETERS` | warning | recheck | ⑥ |
| `IDEMPOTENCY_CONFLICT` | informational | wait | ⑦ |
| `INTENT_CREATION_FAILED` | elevated | retry | ⑧ |

### Execution Errors

| Code | Severity | agent_should | Stage |
|---|---|---|---|
| `EXECUTION_FAILED` | elevated | report | ⑨ |
| `EXECUTION_TIMEOUT` | elevated | retry | ⑨ |
| `EXTERNAL_SERVICE_TIMEOUT` | elevated | retry | ⑨ |
| `RESOURCE_NOT_FOUND` | warning | recheck | ⑨ |
| `OUTPUT_NORMALIZATION_FAILED` | informational | report | ⑩ |

### Review Errors

| Code | Severity | agent_should | Stage |
|---|---|---|---|
| `REVIEW_REJECTED` | elevated | recheck | ReviewBundle |
| `REVISION_REQUESTED` | informational | recheck | ReviewBundle |

### Deploy Errors

| Code | Severity | agent_should | Phase |
|---|---|---|---|
| `DEPLOY_PORT_CONFLICT` | warning | recheck | Phase 4: Port Assignment |
| `DEPLOY_BUILD_FAILED` | elevated | report | Phase 4: Build Validation |
| `DEPLOY_HEALTH_TIMEOUT` | elevated | retry | Phase 4: Health Probe |
| `DEPLOY_PLATFORM_INCOMPATIBLE` | warning | recheck | Phase 4: Platform Checks |
| `DEPLOY_MANIFEST_STALE` | informational | recheck | Phase 4: Manifest |

### Operational State Codes (v0.5.1)

| Code | Severity | agent_should | Trigger |
|---|---|---|---|
| `ACTION_DISABLED` | informational | report | Feature flag off / admin override |
| `ACTION_UNAVAILABLE` | warning | wait | Transient dependency unavailability |

### Existing v0.3 Errors (updated with required `agent_should`)

| Code | Severity | agent_should | Notes |
|---|---|---|---|
| `LEASE_CONFLICT` | warning | wait | Resource lock contention |
| `CONSISTENCY_VIOLATION` | elevated | recheck | State divergence |
| `SAGA_COMPENSATION_FAILED` | critical | escalate | Rollback failure |
| `INTERNAL_ERROR` | critical | report | System-level failure |

---

*End of Error Catalog Amendments. This document is normative for all CONCORD v0.5+ implementations.*
