# CONCORD v0.5 — MCP Adapter Profile

**Status:** Optional Companion Document | **Version:** 0.5.0-draft | **Date:** April 2026  
**Audience:** Any team implementing an MCP server surface over a CONCORD-governed application  
**Prerequisite reading:** CONCORD v0.5 Admission Pipeline Specification, Runtime Endpoint Contracts, Error Catalog  
**Protocol dependency:** Model Context Protocol (MCP) — latest spec (2025-03-26+, with `outputSchema`, `annotations`, `structuredContent`)

---

## 1. Purpose

This document defines an **optional adapter profile** for exposing a CONCORD-governed application as an MCP server. It is not a normative core spec change — CONCORD remains protocol-agnostic. Implementations MAY support this profile to enable MCP-aware agents (Claude Desktop, Cursor, custom agents) to consume governed capabilities.

The adapter profile preserves every CONCORD governance guarantee. MCP is a transport layer; the full 11-stage admission pipeline executes for every tool invocation.

---

## 2. Architectural Position

```
MCP Client (Claude Desktop / Cursor / Custom Agent)
        │
        │  JSON-RPC 2.0 (stdio or HTTP+SSE)
        ▼
┌───────────────────────────────────┐
│  MCP Server (Adapter Process)     │
│                                   │
│  ┌─────────────────────────────┐  │
│  │ MCP→CONCORD Admission Bridge│  │
│  │                             │  │
│  │ B1. Connection → Session    │  │
│  │ B2. tools/list → Registry   │  │
│  │ B3. tools/call → Intent     │  │
│  │ B4. Error → isError result  │  │
│  │ B5. Receipt → structured    │  │
│  │ B6. resources → planning    │  │
│  └──────────┬──────────────────┘  │
│             │                     │
└─────────────┼─────────────────────┘
              │  HTTP (internal)
              ▼
┌───────────────────────────────────┐
│  CONCORD Admission Pipeline       │
│  ①→②→③→④→⑤→⑥→⑦→⑧→⑨→⑩→⑪        │
└───────────────────────────────────┘
```

The bridge is a **separate process** that speaks MCP on one side and CONCORD HTTP on the other. It sits alongside the host application, not inside it. It is an EntryPoint adapter (v0.4 EntryPoint contract, channel: `mcp`).

---

## 3. Design Decisions

| # | Decision | Status |
|---|---|---|
| 1 | Trust tier strategy | Token/session-based AgentClass mapping. **Fail closed.** No blanket T1. |
| 2 | Spec position | Optional MCP adapter profile. **Not normative core.** |
| 3 | Priority | After 1–2 hardened integrations. MCP is "just another EntryPoint." |
| 4 | Validation targets | Claude Desktop first, then Cursor. |

---

## 4. Bridge Contracts

### B1. Session Binding — MCP Connection → CONCORD Session (1:1)

Each MCP connection (stdio process or SSE stream) maps to exactly one CONCORD Session. The session is created on MCP `initialize` and terminated on MCP connection close.

#### B1.1 Connection Establishment

```
MCP initialize received
  │
  ├─ Extract auth token:
  │    stdio transport  → environment variable (adapter-declared)
  │    HTTP+SSE         → Authorization header (Bearer token)
  │    initialize params → authToken field (fallback)
  │
  ├─ Token validation:
  │    ├─ Token valid    → AgentClass resolved → trust tier, budget profile, capabilities, fleet_id
  │    ├─ Token invalid  → FAIL CLOSED: reject initialize, generic error, no detail leakage
  │    └─ Token absent   → FAIL CLOSED: reject initialize, "Authentication required"
  │
  ├─ Create CONCORD Session:
  │    session_id:        generated UUID
  │    agent_class_id:    from token → AgentClass mapping
  │    trust_tier:        from AgentClass
  │    budget_profile_id: from AgentClass
  │    fleet_id:          from token subject (stable across connections)
  │    entry_point_id:    "mcp-{transport}" (e.g., "mcp-stdio", "mcp-sse")
  │    expires_at:        now + AgentClass.default_session_ttl
  │    max_lifetime_at:   now + AgentClass.max_session_lifetime
  │    max_extensions:    from AgentClass policy
  │
  └─ Return MCP initialize response with server capabilities
```

#### B1.2 Fail-Closed Semantics

Without a valid token, the bridge rejects the MCP connection entirely. No `tools/list`, no `tools/call`, no error details about why the rejection occurred.

The adapter profile MUST declare the token transport mechanism for each supported MCP transport:

| MCP Transport | Token Location | Example |
|---|---|---|
| stdio | Environment variable | `CONCORD_MCP_TOKEN=<token>` |
| HTTP+SSE | Authorization header | `Authorization: Bearer <token>` |
| Fallback | `initialize` params | `{ authToken: "<token>" }` |

#### B1.3 Anti-Budget-Evasion

Multiple MCP connections using the same token MUST NOT multiply effective budget. The token → AgentClass mapping MUST yield a stable `fleet_id` (derived from the token subject). All sessions sharing a `fleet_id` draw from the same fleet-level budget pool, consistent with v0.5 fleet-level budget reporting.

#### B1.4 Bridge-Owned Session Refresh

MCP does not expose CONCORD session lifecycle to clients. The bridge MUST proactively manage session refresh:

- **When to refresh:** When `session_constraints` indicate `expiring_soon` or `near_max_lifetime`.
- **How to refresh:** Call `/session/refresh` (Admission Pipeline §3.2). This is an auditable event that produces a receipt.
- **Transparency requirement:** Every auto-refresh MUST be disclosed to the agent in the next tool result (see B5). Include `refresh_receipt_id`, `old_expires_at`, `new_expires_at`.
- **Token validity:** Token validity is checked once at connection time. Session refresh does not re-validate the token. Token TTL is independent of session TTL.

#### B1.5 Connection Termination

```
MCP connection closed (client disconnect, process exit, SSE drop)
  │
  ├─ Check for in-flight intents (status: admitted | executing)
  │    ├─ None    → Terminate session cleanly
  │    └─ Active  → Bridge keeps session alive via auto-refresh
  │                  until all in-flight intents reach terminal state
  │                  (within max_lifetime / max_extensions ceiling)
  │
  ├─ Receipt escrow:
  │    For each completed intent after connection drop:
  │      Store receipt in short-lived escrow keyed by {token_subject, intent_id}
  │      Escrow is read-only; does not bypass admission
  │      Agent can retrieve via new connection without violating
  │      "same session" constraint at the CONCORD API layer
  │      (bridge returns escrowed data, not CONCORD /receipt)
  │
  └─ Session status → terminated (after all intents complete)
```

**Grace period:** The bridge MUST NOT wait indefinitely for in-flight intents. If in-flight intents do not complete within the session's `max_lifetime_at`, the bridge terminates the session. The receipt for incomplete intents records `EXECUTION_TIMEOUT`.

---

### B2. Tool Listing — `tools/list` → ActionContract Registry

MCP `tools/list` returns ActionContracts the connected agent is authorized to admit, filtered by the session's AgentClass and CapabilitySet.

#### B2.1 Filtering

```
MCP tools/list received
  │
  ├─ Resolve session from connection binding (B1)
  │
  ├─ Query ActionContract registry:
  │    Filter: action.minimum_trust_tier <= session.trust_tier
  │    Filter: action.action_family ∈ session.capability_set.allowed_families
  │
  └─ Return filtered ActionContracts as MCP ToolDefinition[]
```

#### B2.2 Tool Definition Shape

For each passing ActionContract, the bridge returns:

```json
{
  "name": "scan.static_analysis",
  "description": "Run static security analysis on a target directory. Guards: service_healthy, target_accessible.",
  "inputSchema": { /* ActionContract.input_schema — JSON Schema Draft 2020-12 */ },
  "outputSchema": { /* ActionContract.output_schema — JSON Schema Draft 2020-12 */ },
  "annotations": {
    "title": "Static Analysis Scan",
    "readOnlyHint": true,
    "idempotentHint": true,
    "openWorldHint": false
  }
}
```

**Key points:**

- `inputSchema`: Direct passthrough of ActionContract `input_schema`. Already JSON Schema Draft 2020-12 per v0.5 mandate.
- `outputSchema`: Direct passthrough of ActionContract `output_schema`. MCP now supports this natively.
- `annotations`: Use MCP's standard annotation fields (`title`, `readOnlyHint`, `idempotentHint`, `destructiveHint`, `openWorldHint`). Map from ActionContract properties:

| MCP Annotation | Source |
|---|---|
| `title` | ActionContract display name |
| `readOnlyHint` | `action_family == "read"` |
| `idempotentHint` | ActionContract `idempotent` flag |
| `destructiveHint` | `action_family ∈ {"mutate", "deploy", "compensate"}` |
| `openWorldHint` | `false` (CONCORD governs all actions) |

#### B2.3 Dynamism — `notifications/tools/list_changed`

The bridge MUST emit `notifications/tools/list_changed` only when the **tool registry changes**:

- ActionContract added, removed, or deprecated
- ActionContract `input_schema` or `output_schema` modified
- ActionContract trust tier or action family changed

The bridge MUST NOT emit `list_changed` for:

- Guard state changes (guard failures are runtime, not discovery-time)
- Budget exhaustion or circuit breaker trips (use OperationContext and budget endpoints)
- Session refresh events

**Rationale:** v0.5 makes OperationContext a "planning oracle" specifically to avoid guesswork. Guard/budget state is exposed through planning endpoints, not tool discovery.

---

### B3. Tool Invocation — `tools/call` → Full Admission Pipeline

Every MCP `tools/call` creates a CONCORD Intent request and submits it through the full 11-stage admission pipeline. No stages are skipped.

#### B3.1 Intent Construction

```
MCP tools/call received
  │  { name: "scan.static_analysis", arguments: { target_directory: "/src", max_depth: 5 } }
  │
  ├─ Resolve session from connection binding (B1)
  │
  ├─ Construct CONCORD intent request:
  │    session_id:      from connection binding
  │    action_name:     from tools/call name
  │    parameters:      from tools/call arguments
  │    idempotency_key: bridge-generated (see B3.2)
  │    entry_point_id:  "mcp-{transport}"
  │
  └─ Submit to admission pipeline (all 11 stages)
```

**v0.5 compliance:** EntryPoint invariance (Admission Pipeline §3.6) — every `tools/call` routes through the same pipeline as native CONCORD intents. No governance bypass.

#### B3.2 Idempotency Key Generation

The bridge MUST NOT use MCP JSON-RPC request IDs as idempotency keys. MCP request IDs are correlation IDs, unique within a session but not retry tokens. A retry with a new JSON-RPC ID would bypass idempotency.

**Bridge idempotency rules:**

| ActionContract Idempotency | Bridge Behavior |
|---|---|
| `idempotency: required` | Bridge MUST generate: `idempotency_key = "mcp:{token_subject}:{tool_name}:{sha256(canonical_json(args))}"` |
| `idempotency: optional` or `idempotent: true` | Bridge MAY omit the key. Stage ⑦ is conditional and skips when no key is provided. |

**Intentional re-execution:** If the agent needs to run the same action with the same arguments again (intentionally, not a retry), the agent MUST include an explicit `run_nonce` in the arguments. The nonce changes the arguments hash, forcing a unique idempotency key.

```json
// First run
{ "target_directory": "/src", "max_depth": 5 }
// → key: mcp:agent123:scan.static_analysis:sha256({target_directory:/src,max_depth:5})

// Intentional re-run
{ "target_directory": "/src", "max_depth": 5, "run_nonce": "re-run-2026-04-17" }
// → key: mcp:agent123:scan.static_analysis:sha256({...run_nonce:re-run-2026-04-17})
```

---

### B4. Error Handling — CONCORD Failures → MCP Tool Execution Errors

**Critical protocol rule:** MCP draws a hard line between protocol errors and tool execution errors:

- **JSON-RPC errors** (`error` object in response): Malformed requests, unknown methods, transport failures. The client handles these.
- **Tool execution errors** (`isError: true` in `tools/call` result): Actionable failures the LLM should reason about. The client SHOULD provide these to the language model.

CONCORD admission rejections (trust, budget, guard, idempotency) are **actionable failures the LLM should reason about**. They MUST be returned as tool execution errors, not JSON-RPC errors.

#### B4.1 Error Mapping

| CONCORD Error | MCP Response Type | Rationale |
|---|---|---|
| Malformed JSON-RPC request | JSON-RPC error (-32700) | Protocol error |
| Unknown tool name (before ActionResolution) | JSON-RPC error (-32601 Method not found) | Protocol error |
| `SESSION_NOT_FOUND` | `isError: true` tool result | Actionable — agent should re-authenticate |
| `SESSION_EXPIRED` | `isError: true` tool result | Actionable — agent should re-connect |
| `SESSION_SUSPENDED` | `isError: true` tool result | Actionable — agent should escalate |
| `ACTION_NOT_FOUND` | JSON-RPC error (-32601) | Protocol error — tool not in registry |
| `ACTION_DEPRECATED` | `isError: true` tool result | Actionable — agent should use replacement |
| `TRUST_INSUFFICIENT` | `isError: true` tool result | Actionable — agent should escalate |
| `BUDGET_EXCEEDED` | `isError: true` tool result | Actionable — agent should wait |
| `CIRCUIT_OPEN` | `isError: true` tool result | Actionable — agent should wait |
| `GUARD_FAILED` | `isError: true` tool result | Actionable — agent should recheck |
| `INVALID_PARAMETERS` | `isError: true` tool result | Actionable — agent should fix params |
| `IDEMPOTENCY_CONFLICT` | `isError: true` tool result | Actionable — agent should wait |
| `EXECUTION_FAILED` | `isError: true` tool result | Actionable — agent should report |
| `EXECUTION_TIMEOUT` | `isError: true` tool result | Actionable — agent should retry |

#### B4.2 Tool Execution Error Shape

All CONCORD admission and execution failures returned as `isError: true` MUST include the canonical CONCORD error object in `structuredContent`:

```json
{
  "content": [
    {
      "type": "text",
      "text": "GUARD_FAILED: Analysis service returned HTTP 503. Retry after 30 seconds."
    }
  ],
  "structuredContent": {
    "concord_error": {
      "code": "GUARD_FAILED",
      "severity": "warning",
      "agent_should": "recheck",
      "requires_context_refresh": true,
      "detail": {
        "failed_guard": "service_healthy",
        "guard_index": 2,
        "reason": "Analysis service returned HTTP 503 during health check",
        "metadata": {
          "service": "analysis-engine",
          "last_healthy_at": "2026-04-17T05:30:00Z",
          "retry_after_ms": 30000
        }
      }
    }
  },
  "isError": true
}
```

**Why `structuredContent`:** MCP explicitly states tool execution errors SHOULD be provided to language models for self-correction. The `structuredContent` carries the full CONCORD error with `agent_should` guidance, enabling the LLM to reason about recovery. The `text` content block provides a human-readable summary as fallback.

---

### B5. Successful Results — Receipt in `structuredContent`

Successful `tools/call` results use MCP's `structuredContent` for the normalized business output and receipt metadata, validated against the tool's `outputSchema`.

#### B5.1 Output Schema Definition

The MCP `outputSchema` published in `tools/list` includes the receipt envelope:

```json
{
  "type": "object",
  "properties": {
    "result": { /* ActionContract.output_schema */ },
    "receipt": {
      "type": "object",
      "properties": {
        "receipt_id": { "type": "string" },
        "intent_id": { "type": "string" },
        "cost_deducted": { "type": "integer" },
        "validation_passed": { "type": "boolean" },
        "validation_errors": { "type": "array", "items": { "type": "string" } },
        "executed_at": { "type": "string", "format": "date-time" },
        "duration_ms": { "type": "integer" }
      }
    },
    "session": {
      "type": "object",
      "properties": {
        "refreshed": { "type": "boolean" },
        "refresh_receipt_id": { "type": "string" },
        "old_expires_at": { "type": "string", "format": "date-time" },
        "new_expires_at": { "type": "string", "format": "date-time" }
      }
    }
  },
  "required": ["result", "receipt"]
}
```

#### B5.2 Successful Result Shape

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"result\":{\"violation_count\":42,\"severity_distribution\":{\"low\":10,\"medium\":22,\"high\":10},\"passed\":false},\"receipt\":{\"receipt_id\":\"rcpt-a1b2c3\",\"intent_id\":\"int-x9y8z7\",\"cost_deducted\":100,\"validation_passed\":true,\"validation_errors\":[],\"executed_at\":\"2026-04-17T05:30:00Z\",\"duration_ms\":2341}}"
    }
  ],
  "structuredContent": {
    "result": {
      "violation_count": 42,
      "severity_distribution": { "low": 10, "medium": 22, "high": 10 },
      "passed": false
    },
    "receipt": {
      "receipt_id": "rcpt-a1b2c3",
      "intent_id": "int-x9y8z7",
      "cost_deducted": 100,
      "validation_passed": true,
      "validation_errors": [],
      "executed_at": "2026-04-17T05:30:00Z",
      "duration_ms": 2341
    },
    "session": {
      "refreshed": true,
      "refresh_receipt_id": "rcpt-refresh-d4e5f6",
      "old_expires_at": "2026-04-17T06:00:00Z",
      "new_expires_at": "2026-04-17T08:00:00Z"
    }
  }
}
```

**Rules:**

- `structuredContent` contains the canonical structured response, validated against `outputSchema`.
- `content[0].text` contains serialized JSON of the same payload for backwards compatibility (MCP recommends this for structured results).
- `session` block is included only when a session refresh occurred since the last tool result. This satisfies the refresh transparency requirement (B1.4).
- The bridge MUST NOT auto-call `/budget/status` after every tool invocation. Budget status and budget estimate are dedicated planning endpoints, exposed as separate MCP resources (see B6).

---

### B6. Resources — Planning/Infrastructure Metadata (Free Surfaces)

MCP Resources expose **planning and infrastructure metadata** that does not flow through the admission pipeline. This is consistent with v0.5's treatment of planning endpoints (`/budget/status`, `/budget/estimate`, `/operation-context`) as governance-safe queries that bypass admission.

#### B6.1 Resource Definitions

| Resource URI | Source | Description |
|---|---|---|
| `concord://actions` | ActionContract registry | Full registry snapshot with schemas |
| `concord://actions/{action_name}/context` | `/operation-context/{action_name}` | Planning oracle for a specific action (trust constraints, budget snapshot, guard pre-evaluation) |
| `concord://budget/status` | `/budget/status` | Remaining budget by category, circuit breaker state |
| `concord://budget/estimate/{action_name}` | `/budget/estimate` | Feasibility check for a planned action |
| `concord://deploy/status` | `/deploy/status` | Deployment health, service status |

#### B6.2 Rules

- Resources are **free**. No BudgetGate, no admission pipeline, no cost deduction.
- Resources are **read-only**. They do not create Intents or Receipts.
- Resources are **session-scoped**. They require a valid session (from B1) but do not consume budget.
- All **domain data reads** (business logic queries that return application data) MUST remain tools with explicit cost and normal admission. Resources are for planning metadata only.
- The `concord://` URI scheme is used for all bridge-provided resources. Host-application resources (if any) use the host's own URI scheme.

#### B6.3 Resource vs. Tool Decision Rule

```
Is it planning/infrastructure metadata?
  ├─ Yes → MCP Resource (free, no pipeline)
  │    Examples: budget status, operation context, action schemas, deploy health
  │
  └─ No → MCP Tool (governed, full pipeline)
       Examples: scan a directory, export a report, query business data
```

---

### B7. Deploy Readiness Gate

The bridge MUST verify deployment readiness at startup:

```
Bridge process starts
  │
  ├─ Call /deploy/status on the host application
  │
  ├─ If 200 OK + all services healthy:
  │    → Accept MCP connections
  │
  ├─ If 503 Service Unavailable (Phase 4 not complete):
  │    → Refuse MCP connections
  │    → Log: "CONCORD deployment Phase 4 not complete. MCP bridge cannot start."
  │
  └─ If any service unhealthy:
       → Refuse MCP connections
       → Log: "Host application services unhealthy. MCP bridge cannot start."
```

This prevents MCP clients from connecting to a partially deployed or unhealthy application.

---

### B8. No MCP Sampling Support

The bridge DOES NOT implement MCP's `sampling/createMessage` capability. The server will not request LLM completions from the client.

**Rationale:** MCP sampling allows the server to ask the client's LLM to generate text. This inverts CONCORD's execution model — CONCORD governs what the agent *does*, not what the agent *thinks*. Sampling requests from the server would create an ungoverned reasoning channel.

**Future consideration:** If server-initiated sampling is ever added, it requires its own budget/accounting surface (it's "server asks client LLM to think") and is outside v0.5's current governance model.

---

## 5. v0.5 Compliance Matrix

| v0.5 Requirement | Spec Reference | Bridge Status | Satisfied By |
|---|---|---|---|
| Entry Point Invariance | Admission Pipeline §3.6 | ✅ Satisfied | B3 — every `tools/call` → full pipeline |
| Stage ordering ①→⑪ | Admission Pipeline §3.1 | ✅ Satisfied | B3 — bridge delegates, doesn't reorder |
| Fail-fast on first failure | Admission Pipeline §3.2 | ✅ Satisfied | B4 — pipeline failure → `isError` result |
| Admission boundary (①–⑧ side-effect-free) | Admission Pipeline §3.3 | ✅ Satisfied | B3 — bridge adds no side effects |
| Cost at ⑪, not at ④ | Admission Pipeline §3.4 | ✅ Satisfied | B3 — bridge doesn't touch budget |
| Session entity fields | Core Spec §3 | ✅ Satisfied | B1 — all v0.5 fields populated |
| Session refresh auditable | Runtime Endpoints §3.2 | ✅ Satisfied | B1.4 — `/session/refresh`, receipt disclosed in B5 |
| Error codes include `agent_should` | Error Catalog | ✅ Satisfied | B4.2 — embedded in `structuredContent` |
| `agent_should` reaches the LLM | Error Catalog | ✅ Satisfied | B4 — MCP routes `isError` results to LLM |
| Input validation via JSON Schema 2020-12 | Admission Pipeline §4.6 | ✅ Satisfied | B2.2 — `inputSchema` is JSON Schema passthrough |
| Output normalization | Admission Pipeline §4.10 | ✅ Satisfied | B5 — normalized output in `structuredContent` |
| Receipt for every execution | Admission Pipeline §4.11 | ✅ Satisfied | B5 — receipt in `structuredContent` |
| Guard evaluation | Admission Pipeline §4.5 | ✅ Satisfied | B3 — pipeline handles; bridge doesn't interfere |
| Idempotency | Admission Pipeline §4.7 | ✅ Satisfied | B3.2 — bridge-generated deterministic keys |
| EntryPoint audit | v0.4 EntryPoint | ✅ Satisfied | B1 — `entry_point_id: "mcp-{transport}"` |
| No governance bypass | Admission Pipeline §3.6 | ✅ Satisfied | B6 — resources are free planning; domain reads are tools |
| Post-deploy readiness | Runtime Endpoints §5.2 | ✅ Satisfied | B7 — bridge checks `/deploy/status` at startup |
| Fleet-level budget | Runtime Endpoints §2.3 | ✅ Satisfied | B1.3 — stable `fleet_id` from token subject |

---

## 6. Implementation Sequence

This adapter profile is prioritized **after 1–2 hardened CONCORD integrations** prove the admission pipeline. The bridge is straightforward to build once the pipeline is solid.

### Phase 1: Reference Implementation

- Target: A CONCORD test-application with representative ActionContracts
- MCP transport: stdio (simplest for Claude Desktop)
- Validate: B1–B7 contracts with Claude Desktop as client
- Deliverable: Working bridge + integration test suite

### Phase 2: Production Application Surface

- Apply bridge to a production CONCORD-governed application's ActionContracts
- Configure AgentClass and token policies for MCP consumers
- MCP transport: HTTP+SSE (production-grade)
- Validate: Claude Desktop + Cursor

### Phase 3: Adapter Hardening

- Connection drop recovery (B1.5 receipt escrow)
- Multi-connection budget governance (B1.3 fleet budget)
- Progress notifications for long-running actions (future v0.6 consideration)

---

## 7. Relationship to CONCORD Core Spec

This adapter profile does NOT modify the CONCORD core spec. It consumes existing contracts:

| Core Contract | Consumed By |
|---|---|
| ActionContract registry | B2 (tool listing) |
| Admission Pipeline (①→⑪) | B3 (tool invocation) |
| Error Catalog + `agent_should` | B4 (error handling) |
| Receipt entity | B5 (result structure) |
| `/session/refresh` | B1.4 (session management) |
| `/budget/status`, `/budget/estimate` | B6 (MCP resources) |
| `/operation-context` | B6 (MCP resources) |
| `/deploy/status` | B7 (startup gate) |
| EntryPoint contract (v0.4) | B1 (session binding) |
| Fleet-level budget (v0.5) | B1.3 (anti-budget-evasion) |

---

---

## 8. MCP Readiness Tiers

CONCORD does not assume that all integrations start at full production readiness. This section defines three formal tiers that teams use to declare the maturity of their MCP bridge implementation. The tiers exist so consuming agents and integration partners can calibrate expectations without inspecting source code.

### 8.1 Tier Definitions

| Tier | Declaration | Meaning |
|---|---|---|
| **Experimental** | `"mcp_readiness": "experimental"` | A bridge exists and basic tool invocation works. Governance is enforced but the implementation is not hardened. Treat as unstable. Not for production agent workloads. |
| **Beta** | `"mcp_readiness": "beta"` | Governance-complete. All bridge contracts implemented. Not yet validated for production load, fleet-level budget, or connection drop recovery. Suitable for integration testing and staging. |
| **Production** | `"mcp_readiness": "production"` | Full profile implemented and validated. All 22 conformance tests pass. Fleet-safe. Connection drop recovery implemented. Suitable for unattended agent workloads. |

### 8.2 Required Contracts Per Tier

#### Experimental (Minimum Viable Bridge)

The Experimental tier establishes a governance-enforced floor. A bridge MUST NOT call itself Experimental if it bypasses any of these contracts.

| Contract | Requirement |
|---|---|
| **B1 — Session Binding** | Connection → Session mapping on `initialize`. Fail-closed on missing or invalid token. |
| **B2 — Tool Listing** | `tools/list` returns ActionContracts filtered by trust tier. `inputSchema` and `outputSchema` are passthrough from ActionContract. |
| **B3 — Tool Invocation** | Every `tools/call` routes through the full 11-stage admission pipeline. No stages skipped. |
| **B4 — Error Handling** | All CONCORD admission failures returned as `isError: true` tool results with `agent_should` in `structuredContent`. No CONCORD errors returned as JSON-RPC errors. |

Conformance tests required (from Appendix A): 8 of 22

```
test_bridge_fails_closed_on_invalid_token
test_tools_list_filtered_by_agent_class
test_tools_list_includes_output_schema_and_annotations
test_tools_call_happy_path_returns_receipt_in_structured_content
test_idempotency_key_generated_from_args_hash
test_guard_failed_returns_is_error_with_agent_should
test_guard_failed_does_not_deduct_budget
test_guard_failed_does_not_create_intent
```

#### Beta (Governance-Complete Bridge)

The Beta tier adds receipt transport, planning resources, and deploy readiness. A Beta bridge is safe for multi-team integration testing.

All Experimental requirements, plus:

| Contract | Requirement |
|---|---|
| **B5 — Receipt Transport** | Successful `tools/call` results include normalized output and receipt in `structuredContent`, validated against `outputSchema`. Session refresh disclosed when it occurs. |
| **B6 — Planning Resources** | `concord://` resources implemented for at minimum: `concord://actions`, `concord://actions/{action_name}/context`, `concord://budget/status`. Resources are free (no pipeline, no budget deduction). |
| **B7 — Deploy Readiness Gate** | Bridge checks `/deploy/status` at startup and refuses MCP connections if the host application is not fully healthy. |
| **B1.4 — Session Refresh** | Bridge proactively refreshes sessions on `expiring_soon`. Refresh receipt disclosed in next tool result. |

Conformance tests required: 18 of 22 (all except the 4 cross-app Scenario 3 tests)

#### Production (Full Profile)

The Production tier adds fleet safety, connection drop recovery, and full conformance validation. A Production bridge is safe for unattended agent workloads.

All Beta requirements, plus:

| Contract | Requirement |
|---|---|
| **B1.3 — Anti-Budget-Evasion** | Multiple connections sharing a token subject draw from the same fleet-level budget pool. `fleet_id` derived from token subject and enforced at BudgetGate. |
| **B1.5 — Connection Drop Recovery** | In-flight intents are protected on connection drop. Receipt escrow implemented. Bridge does not terminate session until in-flight intents reach terminal state (within `max_lifetime_at`). |
| **B2.3 — list_changed** | `notifications/tools/list_changed` emitted only on registry changes (ActionContract additions, removals, schema changes). NOT emitted for guard state or budget changes. |
| **B8 — No Sampling** | Bridge does not advertise or implement `sampling/createMessage`. |

Conformance tests required: 22 of 22 (all Appendix A tests)

### 8.3 Capability Advertisement Governance

**A bridge MUST NOT advertise MCP capabilities it has not implemented.** Advertising an unimplemented capability is a conformance failure at every tier.

This rule applies to the MCP `initialize` response `capabilities` object. The following table maps each advertised capability to the contracts it requires:

| Advertised Capability | Required Contracts | Minimum Tier |
|---|---|---|
| `tools` (tools/list + tools/call) | B1, B2, B3, B4 | Experimental |
| `tools.listChanged` | B2.3 | Production |
| `resources` | B6 | Beta |
| `resources.subscribe` | Subscription implementation (not specified in current profile) | Not yet defined — do not advertise |
| `resources.listChanged` | Registry change notification for resources | Not yet defined — do not advertise |
| `prompts` | (not part of CONCORD profile) | Not yet defined — do not advertise |
| `logging` | (not part of CONCORD profile) | Not yet defined — do not advertise |

**Safe `initialize` response capabilities by tier:**

```json
// Experimental
{
  "capabilities": {
    "tools": {}
  }
}

// Beta
{
  "capabilities": {
    "tools": {},
    "resources": {}
  }
}

// Production
{
  "capabilities": {
    "tools": { "listChanged": true },
    "resources": {}
  }
}
```

Any capability not listed above MUST NOT appear in the `initialize` response unless it is backed by a corresponding CONCORD profile extension (future v0.6+).

### 8.4 Tier Declaration

Declare the readiness tier in `connection_manifest.yaml` under the `sdk` block:

```yaml
sdk:
  base_url: "http://localhost:14854"
  mcp:
    enabled: true
    readiness: "beta"                     # experimental | beta | production
    transport: ["stdio"]                  # stdio | sse — declare only what is implemented
    conformance_tests_passing: 18         # self-reported count
    conformance_tested_at: "2026-04-17"
    profile_version: "0.5.0-draft"
```

**Rules:**
- `transport` MUST list only transports the bridge has actually implemented and tested. Do not list `sse` if only stdio works.
- `conformance_tests_passing` is self-reported. Consuming agents may choose to run the Appendix A test suite independently to verify.
- Downgrade freely, never upgrade prematurely. A bridge operating under production load at Beta tier is acceptable. A bridge declared Production that fails conformance tests is a contract violation.

### 8.5 What Each Tier Licenses You to Say

| Tier | Honest Statement |
|---|---|
| **Experimental** | "AIPAM includes an experimental MCP bridge for CONCORD-governed tool access." |
| **Beta** | "AIPAM provides governance-complete MCP tool access. Recommended for integration testing and staging environments." |
| **Production** | "AIPAM provides MCP-based agent tool access to its CONCORD-governed capability surface. Any MCP-capable agent can discover and invoke AIPAM tools. CONCORD remains the policy, trust, budget, validation, and receipt layer." |

**Production-tier full claim:**
> *"AIPAM provides MCP-based agent tool access to its CONCORD-governed capability surface. MCP is the interoperability layer; CONCORD remains the policy, trust, budget, validation, and receipt layer. Any MCP-capable agent can discover and invoke AIPAM tools without custom AIPAM-specific glue."*

Do not use the Production statement until all 22 Appendix A conformance tests pass.

---

## Appendix A — Scenario Conformance

This appendix defines three integration scenarios that validate the bridge contracts (B1–B8) against real-world agent interaction patterns. Each scenario specifies the expected bridge behavior at every step, including failure branches. Phase 1 implementations MUST pass the conformance tests derived from these scenarios.

---

### Scenario 1: Claude Desktop — "Scan this repo"

**Actors:** Claude Desktop (MCP client), MCP→CONCORD Bridge, CONCORD-governed host application  
**Stresses:** B7 (deploy gate), B1 (session binding), B6 (planning resources), B3 (tool invocation), B4 (error recovery), B5 (receipt transport)

#### Step 0 — Bridge Preflight

```
Bridge startup
  │
  ├─ Call /deploy/status on the host application (B7)
  │    ├─ 200 OK + all services healthy → accept MCP connections
  │    ├─ 503 → refuse connections, log "Phase 4 not complete"
  │    └─ Any service unhealthy → refuse connections
  │
  ├─ Claude Desktop connects via stdio
  │
  ├─ MCP initialize received with auth token
  │    ├─ Token valid → create CONCORD Session (B1.1)
  │    │    session_id:     uuid
  │    │    agent_class_id: from token mapping
  │    │    trust_tier:     from AgentClass
  │    │    fleet_id:       from token subject
  │    │    entry_point_id: "mcp-stdio"
  │    │
  │    └─ Token invalid → FAIL CLOSED (B1.2), generic error, no detail
  │
  └─ Return MCP initialize response with server capabilities
```

**Conformance test:** `test_bridge_refuses_connection_without_deploy_readiness`  
**Conformance test:** `test_bridge_fails_closed_on_invalid_token`

#### Step 1 — Tool Discovery

```
Claude calls tools/list (B2)
  │
  ├─ Bridge queries ActionContract registry
  │    Filter by session trust tier + CapabilitySet
  │
  └─ Returns the host application's ActionContracts as MCP ToolDefinitions
       (name, description, inputSchema, outputSchema, annotations)
```

**"Go blind" vs. "plan first":** Both are permitted. The correct path is **plan first**, because v0.5 explicitly adds planning endpoints so agents avoid discovering failures by trial.

**Conformance test:** `test_tools_list_filtered_by_agent_class`  
**Conformance test:** `test_tools_list_includes_output_schema_and_annotations`

#### Step 2 — Planning (Recommended)

```
Claude reads MCP resource: concord://actions/scan.repo/context (B6)
  │
  ├─ Bridge calls /operation-context/scan.repo
  │
  └─ Returns v0.5 dynamic OperationContext:
       budget_snapshot:      { can_afford: true, remaining: 900 }
       guard_pre_eval:       [
         { guard: "service_healthy", passed: true },
         { guard: "repo_accessible", passed: null, reason: "parameters unavailable" }
       ]
       session_constraints:  { expiring_soon: false, near_max_lifetime: false }
```

**Key points:**
- Guard pre-evaluation is explicitly advisory — may differ at admission time (stateful guards).
- `passed: null` for parameter-dependent guards (repo_accessible) is correct per Integration Guide §4.1.1.
- No budget consumed, no Intent created, no pipeline stages executed (this is a Resource, not a Tool — B6.2).

**Conformance test:** `test_operation_context_resource_returns_guard_preevals`  
**Conformance test:** `test_resource_read_does_not_consume_budget`

#### Step 3 — Execute (Happy Path)

```
Claude calls tools/call scan.repo { repo_url: "https://github.com/org/repo" } (B3)
  │
  ├─ Bridge constructs Intent:
  │    session_id:      from connection binding
  │    action_name:     "scan.repo"
  │    parameters:      { repo_url: "https://github.com/org/repo" }
  │    idempotency_key: "mcp:agent123:scan.repo:sha256({repo_url:...})" (B3.2)
  │    entry_point_id:  "mcp-stdio"
  │
  ├─ Submit to admission pipeline (all 11 stages):
  │    ① SessionResolution   → session active, not expired ✓
  │    ② ActionResolution    → scan.repo found ✓
  │    ③ TrustGate           → T1 >= minimum required ✓
  │    ④ BudgetGate          → remaining >= cost ✓
  │    ⑤ GuardEvaluation     → service_healthy ✓, repo_accessible ✓
  │    ⑥ InputValidation     → repo_url present, valid URL ✓
  │    ⑦ IdempotencyCheck    → no duplicate found ✓
  │    ⑧ IntentCreation      → Intent persisted, status: admitted
  │    ════ ADMISSION BOUNDARY ════
  │    ⑨ Execution           → delegate to host application business logic
  │    ⑩ OutputNormalization  → raw output → output_schema shape
  │    ⑪ ReceiptMinting      → receipt created, budget deducted
  │
  └─ Bridge returns MCP result (B5):
       structuredContent: { result: { ... }, receipt: { receipt_id, cost_deducted, ... } }
       content[0].text: serialized JSON (backwards compatibility)
```

**Conformance test:** `test_tools_call_happy_path_returns_receipt_in_structured_content`  
**Conformance test:** `test_idempotency_key_generated_from_args_hash`

#### Step 3a — Execute (GUARD_FAILED Branch)

```
Claude calls tools/call scan.repo { repo_url: "https://github.com/org/repo" }
  │
  ├─ Pipeline reaches stage ⑤ GuardEvaluation:
  │    service_healthy → passed: false
  │    reason: "Analysis service returned HTTP 503"
  │    retry_after_ms: 30000
  │
  ├─ Pipeline STOPS (fail-fast, Admission Pipeline §3.2)
  │    No subsequent stages evaluated
  │    No Intent created (failure before stage ⑧)
  │    No cost deducted
  │
  └─ Bridge returns MCP isError tool result (B4):
       {
         "content": [{ "type": "text",
           "text": "GUARD_FAILED: Analysis service returned HTTP 503. Retry after 30 seconds." }],
         "structuredContent": {
           "concord_error": {
             "code": "GUARD_FAILED",
             "severity": "warning",
             "agent_should": "recheck",
             "requires_context_refresh": true,
             "detail": {
               "failed_guard": "service_healthy",
               "reason": "Analysis service returned HTTP 503",
               "retry_after_ms": 30000
             }
           }
         },
         "isError": true
       }
```

**Agent recovery loop (what Claude should do):**

1. Read `agent_should: "recheck"` + `requires_context_refresh: true` from the error.
2. Refresh OperationContext: read `concord://actions/scan.repo/context` (B6).
3. If the failed guard is **time-dependent** (`service_healthy`, `quota_available`): wait `retry_after_ms`, then retry `tools/call`.
4. If the failed guard indicates a **structural condition** (`repo_accessible: false`): ask the user for a fix (correct repo URL, provide credentials).

**Conformance test:** `test_guard_failed_returns_is_error_with_agent_should`  
**Conformance test:** `test_guard_failed_does_not_deduct_budget`  
**Conformance test:** `test_guard_failed_does_not_create_intent`

---

### Scenario 2: Cursor — Long-Lived Connection, Bursts, and Idle

**Actors:** Cursor IDE (MCP client), MCP→CONCORD Bridge, CONCORD-governed application  
**Stresses:** B1.4 (session refresh), B1.3 (fleet budget), B3.2 (idempotency under burst), B4 (error recovery under load)

#### Burst Case — 20 `tools/call` in One Minute

This stresses BudgetGate (stage ④) and circuit breakers.

```
Cursor fires 20 sequential tools/call in 60 seconds
  │
  ├─ Calls 1–15: succeed
  │    Budget deducted at ReceiptMinting (⑪) for each
  │    Budget: 1000 → 850 → 700 → ... → 250
  │
  ├─ Call 16: BUDGET_EXCEEDED (stage ④)
  │    remaining (250) < action cost (100) → fail
  │    Bridge returns isError: true
  │    agent_should: "wait"
  │    No cost deducted (admission failure, §3.4)
  │
  ├─ Call 17 (same action, same args as call 3): IDEMPOTENCY_CONFLICT
  │    Bridge-generated idempotency key matches call 3's completed Intent
  │    Pipeline returns existing Receipt (idempotent replay, §4.7)
  │    No new execution, no new cost
  │
  └─ Call 18 (same action, same args as call 3 + run_nonce): succeeds
       run_nonce changes args hash → unique idempotency key → new Intent
```

**Planning-first alternative:** Before the burst, the agent should call:

- `concord://budget/status` — see remaining budget (B6)
- `concord://budget/estimate/scan.repo` — check if planned action is affordable (B6)

These planning surfaces exist specifically so agents don't discover budget exhaustion by trial.

**Expected failure modes under burst:**

| Failure | Error Code | `agent_should` | Cost Deducted? |
|---|---|---|---|
| Budget exhausted | `BUDGET_EXCEEDED` | `wait` | No |
| Circuit breaker tripped | `CIRCUIT_OPEN` | `wait` | No |
| Duplicate in-flight | `IDEMPOTENCY_CONFLICT` | `wait` | No |
| Duplicate completed | (Replay existing receipt) | — | No (original cost already deducted) |
| Transient DB failure | `INTENT_CREATION_FAILED` | `retry` | No |

**Conformance test:** `test_burst_budget_exhaustion_returns_wait`  
**Conformance test:** `test_burst_idempotency_replays_existing_receipt`  
**Conformance test:** `test_burst_with_run_nonce_creates_new_intent`

#### Idle Case — 2 Hours of Silence

This stresses session expiration and bridge-owned refresh.

```
Connection established at T+0
Session TTL: 1 hour
  │
  ├─ T+0 to T+50min: normal tool usage
  │
  ├─ T+50min: bridge detects session_constraints.expiring_soon = true
  │    via OperationContext check during last tool result
  │
  ├─ T+55min: bridge proactively calls /session/refresh (B1.4)
  │    Refresh receipt minted (auditable event)
  │    Session extended: new expires_at = T+1h55min
  │
  ├─ T+55min to T+2h: silence (no tools/call)
  │
  ├─ T+1h50min: session approaching expiry again
  │    No tool invocation to trigger refresh check
  │    Bridge SHOULD poll session health on idle interval
  │    (recommended idle check: every session_ttl/4)
  │
  ├─ Bridge refreshes again if within max_extensions
  │    OR
  │    Session reaches max_lifetime_at → bridge cannot refresh
  │
  ├─ T+2h: Cursor sends tools/call
  │    ├─ If session still active → proceed normally
  │    │    Include session.refreshed: true + refresh details in result (B5)
  │    │
  │    └─ If session expired (max_lifetime_at reached):
  │         Pipeline returns SESSION_EXPIRED
  │         Bridge returns isError: true, agent_should: "recheck"
  │         (agent must reconnect → new session)
  │
  └─ If near_max_lifetime and no extensions remaining:
       Bridge returns SESSION_MAX_LIFETIME_REACHED
       agent_should: "escalate"
       (agent cannot self-recover; needs operator intervention or reconnection)
```

**Refresh strategy (tight, practical):**

- Bridge refreshes proactively when `session_constraints.expiring_soon = true`.
- Bridge discloses every refresh in the next tool result (`refresh_receipt_id`, `old_expires_at`, `new_expires_at`).
- Bridge stops auto-refreshing when `near_max_lifetime` is true and returns `SESSION_MAX_LIFETIME_REACHED` (`agent_should: escalate`).
- This avoids both "silent session death" and "silent infinite refresh loop."
- On idle connections: bridge polls session health at `session_ttl / 4` interval.

**Conformance test:** `test_idle_session_auto_refreshed_before_expiry`  
**Conformance test:** `test_refresh_disclosed_in_next_tool_result`  
**Conformance test:** `test_max_lifetime_reached_returns_escalate`  
**Conformance test:** `test_idle_poll_interval_is_session_ttl_divided_by_four`

---

### Scenario 3: Enterprise Orchestrator — Cross-App Tool Chaining

**Actors:** Enterprise orchestration agent (MCP client), two MCP→CONCORD Bridges (App A, App B), two CONCORD-governed applications  
**Stresses:** B1.3 (fleet budget across apps), B6 (resource-vs-tool boundary), B7 (deploy readiness per app)

#### Architecture

```
Enterprise Orchestrator (MCP client)
  │
  ├─── MCP Connection A ──→ Bridge A ──→ App A (CONCORD runtime)
  │     session_A                          session + intents + receipts + leases
  │
  └─── MCP Connection B ──→ Bridge B ──→ App B (CONCORD runtime)
        session_B                          session + intents + receipts + leases
```

**The clean default:** Each governed app gets its own MCP connection and its own CONCORD Session. Sessions are app-runtime state — intents, receipts, and leases live there. Cross-session sharing would violate isolation.

#### Step 0 — Per-App Deploy Verification

```
Orchestrator connects to both bridges
  │
  ├─ Bridge A: /deploy/status → 200 OK, all healthy (B7)
  ├─ Bridge B: /deploy/status → 200 OK, all healthy (B7)
  │
  ├─ Both bridges create CONCORD Sessions:
  │    Session A: fleet_id = "enterprise-orch-token-subject" (from token)
  │    Session B: fleet_id = "enterprise-orch-token-subject" (same token subject)
  │
  └─ Both sessions share the SAME fleet_id
       → fleet-level budget governance is possible
```

#### Step 1 — Plan Across Both Apps

```
Orchestrator reads planning resources from both apps (B6):
  │
  ├─ App A: concord://budget/status
  │    Returns: { categories: [{ category: "compute", remaining: 500 }], fleet_id: "..." }
  │
  ├─ App B: concord://budget/status
  │    Returns: { categories: [{ category: "compute", remaining: 300 }], fleet_id: "..." }
  │
  ├─ App A: concord://budget/estimate/scan.repo
  │    Returns: { cost: 100, budget_sufficient: true, can_execute: true }
  │
  └─ App B: concord://budget/estimate/report.generate
       Returns: { cost: 200, budget_sufficient: true, can_execute: true }
```

The orchestrator now knows the total cost (100 + 200 = 300) fits within both apps' budgets. This is pure planning — no Intent created, no budget consumed, no pipeline stages executed.

#### Step 2 — Execute Across Both Apps

```
Orchestrator calls:
  │
  ├─ App A: tools/call scan.repo { repo_url: "..." }
  │    → Full 11-stage pipeline in App A
  │    → Receipt: { cost_deducted: 100 }
  │    → App A fleet budget: 500 → 400
  │
  └─ App B: tools/call report.generate { scan_id: "from-app-a-receipt" }
       → Full 11-stage pipeline in App B
       → Receipt: { cost_deducted: 200 }
       → App B fleet budget: 300 → 100
```

Each app governs its own admission independently. The orchestrator chains results by passing data from App A's receipt into App B's tool arguments.

#### Shared Budget Governance (Optional)

v0.5 already anticipates fleet-governed budgets via `fleet_id`. Cross-app governance coherence works without shared sessions:

| Concern | Mechanism | Isolation Preserved? |
|---|---|---|
| Separate sessions | Each app has its own session, intents, receipts, leases | ✅ Yes |
| Shared budget | `fleet_id` from token subject, enforced per-app at fleet level | ✅ Yes — each app's BudgetLedger checks fleet ceiling |
| Shared identity | Same token subject → same AgentClass across apps | ✅ Yes — identity is in the token, not the session |
| Cross-app receipts | Orchestrator carries receipt data between apps explicitly | ✅ Yes — no cross-session receipt access needed |

**Conformance test:** `test_cross_app_sessions_share_fleet_id_from_token_subject`  
**Conformance test:** `test_cross_app_planning_resources_return_fleet_budget`  
**Conformance test:** `test_cross_app_execution_deducts_from_per_app_budget`  
**Conformance test:** `test_cross_app_result_chaining_via_tool_arguments`

---

### Stress Points Validated

| Bridge Contract | Validated By | Scenario |
|---|---|---|
| **B1 — Session lifetime** | Session refresh under idle, max_lifetime cap, idle poll interval | Scenario 2 |
| **B1.3 — Fleet budget** | Same fleet_id across apps, anti-budget-evasion | Scenario 3 |
| **B3 — Pipeline integrity** | Full 11-stage execution, fail-fast on guard failure | Scenario 1 |
| **B3.2 — Idempotency** | Burst dedup, run_nonce for intentional re-execution | Scenario 2 |
| **B4 — Error recovery** | GUARD_FAILED → recheck → OperationContext refresh → retry | Scenario 1 |
| **B4 — Error under load** | BUDGET_EXCEEDED, CIRCUIT_OPEN, IDEMPOTENCY_CONFLICT under burst | Scenario 2 |
| **B5 — Receipt transport** | structuredContent with receipt + session refresh disclosure | Scenarios 1, 2 |
| **B6 — Resource boundary** | Planning resources free; domain reads governed as tools | Scenarios 1, 3 |
| **B7 — Deploy gate** | Per-app deploy verification before accepting connections | Scenarios 1, 3 |

---

### Conformance Test Summary

Phase 1 implementations MUST pass all conformance tests listed in this appendix. Tests are grouped by scenario:

**Scenario 1 — Claude Desktop (10 tests):**

| Test ID | Description |
|---|---|
| `test_bridge_refuses_connection_without_deploy_readiness` | B7 startup gate |
| `test_bridge_fails_closed_on_invalid_token` | B1.2 fail-closed |
| `test_tools_list_filtered_by_agent_class` | B2.1 filtering |
| `test_tools_list_includes_output_schema_and_annotations` | B2.2 tool shape |
| `test_operation_context_resource_returns_guard_preevals` | B6 planning |
| `test_resource_read_does_not_consume_budget` | B6.2 free surface |
| `test_tools_call_happy_path_returns_receipt_in_structured_content` | B5 receipt |
| `test_idempotency_key_generated_from_args_hash` | B3.2 idempotency |
| `test_guard_failed_returns_is_error_with_agent_should` | B4 error handling |
| `test_guard_failed_does_not_deduct_budget` | B4 + §3.4 cost |

**Scenario 2 — Cursor (8 tests):**

| Test ID | Description |
|---|---|
| `test_burst_budget_exhaustion_returns_wait` | B4 budget error |
| `test_burst_idempotency_replays_existing_receipt` | B3.2 dedup |
| `test_burst_with_run_nonce_creates_new_intent` | B3.2 nonce |
| `test_idle_session_auto_refreshed_before_expiry` | B1.4 refresh |
| `test_refresh_disclosed_in_next_tool_result` | B1.4 + B5 transparency |
| `test_max_lifetime_reached_returns_escalate` | B1.4 ceiling |
| `test_idle_poll_interval_is_session_ttl_divided_by_four` | B1.4 idle |
| `test_guard_failed_does_not_create_intent` | B4 + §3.2 fail-fast |

**Scenario 3 — Enterprise Orchestrator (4 tests):**

| Test ID | Description |
|---|---|
| `test_cross_app_sessions_share_fleet_id_from_token_subject` | B1.3 fleet |
| `test_cross_app_planning_resources_return_fleet_budget` | B6 + fleet |
| `test_cross_app_execution_deducts_from_per_app_budget` | B3 + B1.3 |
| `test_cross_app_result_chaining_via_tool_arguments` | B3 cross-app |

**Total:** 22 conformance tests.

---

*End of Appendix A. These scenarios are normative for Phase 1 implementations of the MCP Adapter Profile.*

---

*End of MCP Adapter Profile. This document is an optional companion to the CONCORD v0.5 spec pack. Implementations that do not expose an MCP surface are fully compliant without it.*
