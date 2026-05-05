# CONCORD v0.4 Gap Analysis & Proposals

**Stripe Minion Architecture → CONCORD Gap Map**

Status: Proposal draft | Date: March 2026 | Basis: CONCORD v0.3 spec pack + Stripe minion blog analysis

---

## Executive Summary

CONCORD v0.3 is strong where Stripe is strong — the pipeline/blueprint pattern and validation feedback loops have direct equivalents in the ForgeWorks pipeline and planner loop. CONCORD's trust tiers, budget enforcement, saga/compensation, consistency profiles, and conflict resolution are areas where CONCORD is **ahead** of what Stripe has described publicly.

The gaps cluster in five areas that Stripe's architecture addresses and CONCORD v0.3 does not:

| Gap | Stripe component | CONCORD v0.3 status | Priority |
|-----|-----------------|---------------------|----------|
| Execution environments | Warm devbox pool | No entity | P0 |
| Parallel dispatch & fleet coordination | Multi-minion orchestration | Partial (Session/Lease) | P0 |
| Tool discovery & selection | Tool shed (meta-MCP) | Static action catalog only | P1 |
| Multi-entry admission surface | CLI / Web / Slack | No entry-point abstraction | P1 |
| Conditional context scoping | Glob-scoped rule files | No context-scope entity | P2 |
| Review artifact bundle | PR template + CI output | Receipts exist, no bundle | P2 |

This document proposes specific additions to the CONCORD spec pack to close each gap while preserving CONCORD's existing strengths.

---

## Part 1 — What CONCORD Already Covers (Stripe Overlap)

Before addressing gaps, it's worth recognizing where CONCORD v0.3 already meets or exceeds the Stripe architecture. These are **not** areas requiring change.

### 1.1 Blueprint Engine ↔ ForgeWorks Pipeline + Planner Loop

Stripe's blueprint engine interleaves deterministic code steps with non-deterministic agent reasoning. CONCORD's ActionContract (with action_family distinguishing read/plan/mutate/approve/deploy/compensate) combined with StateContract (explicit state machines with guarded transitions) provides a more rigorous version of this pattern. The ForgeWorks planner loop with DONE/REPLAN/STOP_FAILED control flow and loop_policy (max_iterations, target_score, max_no_progress_iters) is more sophisticated feedback control than Stripe's hard 2-round CI limit.

**No changes needed.** This is a strength.

### 1.2 Validation Layer ↔ ForgeWorks Scoring + Error Taxonomy

Stripe runs selective tests from a 3M+ test suite and feeds CI results back to agents. CONCORD's four-class error taxonomy (retryable, user_fixable, dev_action_required, pipeline_error) with structured agent-action guidance (retry, recheck, queue, wait, escalate, abort, compensate) is more granular than anything Stripe described. The error catalog's metadata fields (severity, retryable, retry_delay_hint_ms, agent_should, blocks_other_actions, requires_context_refresh) give agents precise behavioral instructions that Stripe's CI-pass/CI-fail binary lacks.

**No changes needed.** This is a strength.

### 1.3 Trust & Authority ↔ No Stripe Equivalent

Stripe doesn't publicly describe graduated trust tiers, capability composition, or restrict-by-default override semantics. CONCORD's AgentClass with T0–T4 trust tiers, CapabilitySet composition, and the rule that override_rules may narrow but never expand rights is a governance layer Stripe either hasn't built or hasn't disclosed.

**No changes needed.** This is an advantage CONCORD should preserve.

### 1.4 Budget Enforcement ↔ Stripe Cost Constraint (Primitive)

Stripe mentions cost as the reason they limit minions to 2 CI rounds. CONCORD's BudgetProfile with risk-weighted cost units, per-action-family limits, circuit breakers, and cooldown policies is a full-fidelity version of what Stripe handles with a hard-coded constant.

**No changes needed.** This is an advantage.

### 1.5 Saga/Compensation ↔ No Stripe Equivalent

Stripe doesn't discuss rollback or compensation for failed agent runs beyond "try again." CONCORD's saga model with timeout policies, compensation strategies, poison handling, and max_compensation_attempts addresses a failure class that Stripe's architecture appears to handle manually.

**No changes needed.**

### 1.6 Scan & Readiness ↔ No Stripe Equivalent

CONCORD's Scan Output Schemas (readiness report, danger map, resource dependency graph, patch plan) provide an adoption wedge and ongoing safety assessment that Stripe's architecture doesn't include. This is particularly valuable for onboarding new domains into the agent system.

**No changes needed.**

---

## Part 2 — Gap Proposals

### Gap 1: Execution Environment (P0)

**What Stripe has:** Pre-warmed EC2 instances ("devboxes") with source code and services preloaded. Each agent gets an isolated environment mirroring what human engineers have. Spin-up in ~10 seconds from a warm pool. Engineers run half a dozen concurrently.

**What CONCORD v0.3 has:** Session entity tracks agent identity, task, mode, and expiration. But Session has no concept of *where* the agent executes. There's no isolation guarantee, no environment lifecycle, no resource provisioning contract.

**Proposed addition: ExecutionEnvironment entity (Core Spec §3, new subsection)**

```
Entity: ExecutionEnvironment

Field                    Type        Rule
environment_id           string      Unique identifier
environment_class        enum        ephemeral, persistent, shared_pool
provisioning_status      enum        cold, warming, ready, assigned, 
                                     draining, terminated
assigned_session_id      string?     Session currently bound (null if pooled/unassigned)
resource_spec            object      CPU, memory, storage, network constraints
preload_manifest         array       Artifacts, repos, services pre-staged
isolation_level          enum        none, container, vm, dedicated_host
created_at               timestamp   Pool entry time
ready_at                 timestamp?  When provisioning completed
assigned_at              timestamp?  When bound to a session
max_lifetime_ms          integer     Hard ceiling before forced termination
heartbeat_interval_ms    integer     Liveness signal requirement
status                   enum        active, unhealthy, terminated
```

**Normative rules:**

- A Session with `mode = unattended` MUST be bound to an ExecutionEnvironment with `isolation_level >= container`.
- ExecutionEnvironment assignment MUST be recorded on the Session entity and included in all Receipts emitted during that session.
- Environment teardown MUST NOT occur while the bound session has intents in `admitted` or `executing` status. Teardown with active intents triggers saga compensation or escalation.
- Preload manifests SHOULD be versioned and content-addressed so that cache hits can be validated.

**Impact on existing schemas:**

- **Session** gains optional `environment_id` field
- **Receipt** gains optional `environment_id` for traceability
- **BudgetProfile** gains optional `max_parallel_environments` field
- **CoordinationTelemetry** gains `environment_pool_utilization`, `average_provision_time_ms`, `environment_recycle_rate`

---

### Gap 2: Parallel Dispatch & Fleet Coordination (P0)

**What Stripe has:** One engineer spins up multiple minions in parallel, each on its own devbox, each solving a separate problem. The minions run independently but share CI infrastructure and PR output.

**What CONCORD v0.3 has:** Sessions are independent. Leases provide per-resource coordination. BudgetProfile has max_parallel_leases. But there's no concept of a *fleet* — a group of sessions pursuing related or independent goals under shared governance, or a dispatch mechanism that assigns tasks to available agents.

**Proposed addition: TaskFleet and DispatchRequest entities (Core Spec §3, new subsection)**

```
Entity: TaskFleet

Field                    Type        Rule
fleet_id                 string      Unique identifier
owner_session_id         string      Human or orchestrator session that owns the fleet
agent_class_id           string      AgentClass for all fleet members
max_concurrent           integer     Ceiling on simultaneously active member sessions
member_sessions          array       Active session references
fleet_status             enum        assembling, active, draining, completed, aborted
budget_profile_id        string      Shared budget pool for the fleet
isolation_requirement    enum        per_session, shared, mixed
completion_policy        enum        all_must_succeed, best_effort, 
                                     first_success, quorum(n)
created_at               timestamp   Fleet creation time
timeout_at               timestamp   Fleet-level hard deadline
```

```
Entity: DispatchRequest

Field                    Type        Rule
dispatch_id              string      Unique identifier
fleet_id                 string      Owning fleet
task_description         object      Structured task payload (domain-specific)
priority                 enum        low, normal, high, critical
assigned_session_id      string?     Null until dispatched
assigned_environment_id  string?     Null until environment bound
dispatch_status          enum        queued, assigned, active, completed, 
                                     failed, cancelled
max_attempts             integer     Retry ceiling for this dispatch
attempt_count            integer     Current attempt number
result_ref               string?     Reference to completion artifacts
```

**Normative rules:**

- A TaskFleet MUST enforce its `max_concurrent` ceiling. Dispatch requests beyond the ceiling enter `queued` status.
- Fleet budget is shared: all member sessions draw from the fleet's BudgetLedger. Individual session budgets are subordinate.
- When `completion_policy = all_must_succeed`, any member session entering `error` or `aborted` status MUST trigger fleet-level evaluation (continue, retry, or abort).
- Fleet timeout MUST override individual session timeouts. When fleet timeout is reached, all active member sessions receive a termination signal.
- DispatchRequests MUST carry enough structured context for the assigned agent to begin without requiring interactive clarification (this is the outloop contract).

**Impact on existing schemas:**

- **Session** gains optional `fleet_id` field
- **BudgetLedger** gains optional `fleet_id` for fleet-level accounting
- **CoordinationTelemetry** gains `fleet_utilization_rate`, `average_dispatch_wait_ms`, `fleet_completion_rate`

---

### Gap 3: Tool Discovery & Selection (P1)

**What Stripe has:** A centralized "tool shed" — an internal MCP server that lets agents discover and select from ~500 tools without loading all definitions into context. It's a meta-tool: a tool that helps agents find tools.

**What CONCORD v0.3 has:** ActionContract defines individual actions. The Scan Output Schemas include a Generated Action Catalog, but it's a static scan artifact, not a runtime discovery service. CapabilitySets grant access to action families, but there's no mechanism for an agent to query "what tools are available for my current task and context?"

**Proposed addition: ActionDiscovery service contract (Runtime Contract Schemas, new section)**

```
Service: ActionDiscovery

Purpose: Runtime service that resolves available actions for a given 
agent, resource context, and task intent. Prevents token explosion 
from loading full action catalogs into agent context.

Query contract:
  Input:
    session_id           string      Current session (determines AgentClass, capabilities)
    resource_type        string?     Optional filter by resource class
    action_family        enum?       Optional filter (read, mutate, approve, etc.)
    task_context         string?     Natural language or structured task description
    max_results          integer     Ceiling on returned actions (default 10)
    include_schemas      boolean     Whether to include full input/output schemas 
                                     (default false — return refs only)

  Output:
    available_actions    array       ActionContract summaries (name, family, risk, 
                                     description, guard summary)
    filtered_by          object      Applied filters for transparency
    total_available      integer     Full count before truncation
    recommendation       object?     Optional ranked suggestion with rationale
    catalog_version      string      Version of the action catalog used
```

**Normative rules:**

- ActionDiscovery MUST filter results by the requesting session's AgentClass and CapabilitySet. An agent MUST NOT discover actions it cannot admit.
- When `include_schemas = false`, the service returns lightweight summaries to minimize context consumption. Full schemas are fetched on demand.
- ActionDiscovery responses are advisory (consistent with OperationContext semantics). Discovery of an action does not guarantee admission.
- Implementations SHOULD support semantic search over action descriptions when `task_context` is provided, enabling agents to find relevant tools without knowing exact names.
- The service SHOULD cache and version its catalog. Cache invalidation MUST occur when ActionContracts are added, removed, or modified.

**Relationship to existing entities:**

- ActionDiscovery consumes ActionContract definitions and CapabilitySet grants
- It complements OperationContext: OperationContext shows what's allowed *for a specific resource right now*; ActionDiscovery shows what's available *across the system for a task type*
- The Generated Action Catalog from Scan Output Schemas can serve as the seed data for ActionDiscovery

---

### Gap 4: Multi-Entry Admission Surface (P1)

**What Stripe has:** CLI, web UI, and Slack all feed into the same agent system. Engineers trigger minions from wherever they work. The underlying service is unified; only the entry points differ.

**What CONCORD v0.3 has:** OperationContext is the planning surface. Intent is the admission unit. But there's no abstraction for *how* work enters the system — no contract for normalizing a Slack message, a CLI command, and a web form into the same Intent structure.

**Proposed addition: EntryPoint contract (Core Spec, new section or Contract Layer extension)**

```
Entity: EntryPoint

Field                    Type        Rule
entry_point_id           string      Unique identifier
channel                  enum        cli, web_ui, slack, api, webhook, 
                                     cron, event_trigger
display_name             string      Human-readable name
admission_adapter_ref    string      Reference to the adapter that normalizes 
                                     channel input into Intent or DispatchRequest
required_fields          array       Minimum fields the channel must provide
default_agent_class_id   string?     Default AgentClass if not specified by caller
default_fleet_policy     object?     Default fleet/dispatch behavior for this channel
authentication_method    enum        token, oauth, session_cookie, service_account, none
rate_limit_profile_id    string?     Channel-specific rate limiting
audit_channel            boolean     Whether inputs are logged for audit
```

```
Contract: AdmissionAdapter

Purpose: Normalizes channel-specific input into a CONCORD-native 
DispatchRequest or direct Intent.

Input:   Channel-specific payload (Slack message, CLI args, web form, etc.)
Output:  One of:
         - DispatchRequest (for outloop/fleet dispatch)
         - Intent (for direct single-action admission)
         - ValidationError (if required fields missing or input malformed)

Normative rules:
- Adapters MUST validate required_fields before constructing output.
- Adapters MUST attach entry_point_id and channel to the output for traceability.
- Adapters MUST NOT bypass AgentClass or BudgetProfile checks.
- Adapters MAY enrich the output with defaults from the EntryPoint configuration.
```

**Impact on existing schemas:**

- **Intent** gains optional `entry_point_id` and `channel` fields
- **DispatchRequest** gains optional `entry_point_id` and `channel` fields
- **Receipt** gains optional `entry_point_id` for end-to-end traceability

---

### Gap 5: Conditional Context Scoping (P2)

**What Stripe has:** Markdown rule files with front matter specifying glob patterns. Context is conditionally loaded as the agent traverses different parts of the codebase. Rules are scoped to subdirectories. This solves the "can't load the whole codebase into context" problem.

**What CONCORD v0.3 has:** OperationContext provides per-resource context. ActionContracts carry guards and constraints. But there's no mechanism for *domain-scoped rules* that activate based on what part of the system the agent is operating in. The `domain` parameter in the ForgeWorks contract ("ci_change_control" | "it_ops_runbook") is a step in this direction but not generalized.

**Proposed addition: ContextScope entity (Core Spec §4 extension or new section)**

```
Entity: ContextScope

Field                    Type        Rule
scope_id                 string      Unique identifier
scope_type               enum        resource_type, domain, path_glob, 
                                     tag, action_family, composite
match_pattern            string      Pattern that activates this scope 
                                     (glob, regex, or exact match depending on scope_type)
priority                 integer     Resolution order when multiple scopes match
rules                    array       Scoped behavioral rules (see below)
context_additions        array       Additional context fragments to inject 
                                     when scope is active
context_exclusions       array       Context fragments to suppress when scope is active
inherits_from            string?     Parent scope for hierarchical composition
active                   boolean     Whether this scope is currently enabled
```

```
Object: ScopedRule

Field                    Type        Rule
rule_id                  string      Unique identifier
rule_type                enum        convention, constraint, preference, 
                                     warning, escalation_trigger
content                  string      Rule text (human and machine readable)
applies_to               enum        agent, validator, reviewer, all
severity                 enum        advisory, recommended, required
source_ref               string?     Traceability to originating document or decision
```

**Normative rules:**

- When an agent requests OperationContext for a resource, the runtime MUST evaluate active ContextScopes against the resource's type, domain, path, and tags.
- Matching scopes are merged in priority order (higher priority wins on conflicts).
- ContextScope content MUST be included in OperationContext responses when applicable, either in a new `active_scopes` field or by enriching `allowed_actions` / `blocked_actions` / `trust_constraints`.
- Agents SHOULD NOT receive scopes that don't match their current operational context (this prevents context bloat — the core problem Stripe solved).
- ContextScope definitions SHOULD be versionable and auditable.

**Impact on existing schemas:**

- **OperationContext** gains `active_scopes` array field listing matched ContextScope references and their injected rules
- **Receipt** gains optional `scopes_applied` for traceability

---

### Gap 6: Review Artifact Bundle (P2)

**What Stripe has:** Minions produce PR-ready output following Stripe's PR template. The PR includes the branch, CI results, and a formatted diff. A human reviewer sees everything they need in one place.

**What CONCORD v0.3 has:** Receipts capture per-action results. The ForgeWorks contract defines artifact paths (run_summary, decision_ledger, approval_records, score, report). But there's no aggregation point — no single artifact that bundles everything a human reviewer needs to evaluate an agent's completed work.

**Proposed addition: ReviewBundle artifact (Recovery and Observability Layer extension)**

```
Artifact: ReviewBundle

Field                    Type        Rule
bundle_id                string      Unique identifier
session_id               string      Originating session
fleet_id                 string?     Originating fleet if applicable
dispatch_id              string?     Originating dispatch if applicable
created_at               timestamp   Bundle assembly time
bundle_status            enum        pending_review, approved, rejected, 
                                     revision_requested
summary                  object      Human-readable summary of what the agent did
receipts                 array       All Receipts from the session/dispatch
state_changes            array       Business state transitions performed
resources_modified       array       Resource IDs and types touched
validation_results       object      Aggregated validation/scoring output
risk_assessment          object      Highest risk level encountered, 
                                     escalations triggered, budget consumed
artifacts                object      References to all produced artifacts 
                                     (domain-specific)
diff_ref                 string?     Reference to changeset/diff if applicable
reviewer_session_id      string?     Assigned reviewer
review_decision          enum?       approved, rejected, revision_requested
review_notes             string?     Reviewer comments
review_completed_at      timestamp?  When review was finalized
```

**Normative rules:**

- When a Session or DispatchRequest reaches a terminal state, the runtime SHOULD assemble a ReviewBundle if the work involved any mutating actions.
- ReviewBundle assembly MUST NOT require the reviewing human to understand CONCORD internals. The summary field must be written for domain-context readers.
- ReviewBundles MUST include all Receipts so reviewers can trace every action the agent took.
- For fleets with `completion_policy = all_must_succeed`, a fleet-level ReviewBundle SHOULD aggregate member bundles.
- ReviewBundle approval MAY be wired as a guard predicate on downstream actions (e.g., deploy_change_request requires ReviewBundle.bundle_status = approved).

---

## Part 3 — Implementation Sequencing

Given CONCORD's existing spec maturity and the DAWN harness available for development:

### Phase 1 (v0.4-alpha): ExecutionEnvironment + Fleet foundations

- Add ExecutionEnvironment entity to Core Spec §3
- Add TaskFleet and DispatchRequest entities to Core Spec §3
- Extend Session, Receipt, BudgetProfile, BudgetLedger with new fields
- Extend CoordinationTelemetry with environment and fleet metrics
- Update Minimum Implementation Profile to note these as deferrable for single-agent deployments
- **Rationale:** These two gaps are P0 because they unlock parallelization, which is the primary scaling lever Stripe demonstrates. Without them, CONCORD can govern a single agent well but can't orchestrate a fleet.

### Phase 2 (v0.4-beta): ActionDiscovery + EntryPoint

- Add ActionDiscovery service contract to Runtime Contract Schemas
- Add EntryPoint and AdmissionAdapter contracts to Core Spec
- Wire ActionDiscovery to consume existing ActionContract and CapabilitySet data
- **Rationale:** These are P1 because they improve developer experience and tool management. ActionDiscovery becomes critical as the number of actions grows past what fits in agent context. EntryPoint enables the multi-channel trigger model.

### Phase 3 (v0.4-rc): ContextScope + ReviewBundle

- Add ContextScope entity and ScopedRule to Core Spec
- Extend OperationContext with active_scopes
- Add ReviewBundle to Recovery and Observability Layer
- **Rationale:** These are P2 because they're refinements rather than structural gaps. CONCORD can function without them, but they become important as domains and agent autonomy scale.

### Impact on Scan Output Schemas

The Scan documents should be extended to evaluate the new entities:

- **Readiness Report** gains dimension scores for: environment isolation, fleet governance, tool discovery coverage, entry-point diversity, context-scope coverage, review-bundle completeness
- **Danger Map** gains new danger categories: `unattended_agent_without_isolation`, `fleet_without_shared_budget`, `action_catalog_exceeds_context_window`, `missing_review_gate_on_mutating_fleet`
- **Patch Plan** can generate work items for standing up environments, wiring entry points, and defining context scopes

### Impact on Error and Conflict Code Catalog

New codes for the new entities:

| Code | Severity | Agent should | Meaning |
|------|----------|-------------|---------|
| ENVIRONMENT_UNAVAILABLE | elevated | wait | No warm environment in pool |
| ENVIRONMENT_UNHEALTHY | warning | escalate | Assigned environment failed heartbeat |
| FLEET_BUDGET_EXCEEDED | warning | wait | Fleet-level budget exhausted |
| FLEET_CONCURRENCY_LIMIT | warning | queue | Fleet max_concurrent reached |
| FLEET_TIMEOUT | elevated | abort | Fleet hard deadline reached |
| DISPATCH_UNASSIGNABLE | warning | escalate | No available agent/environment for dispatch |
| ACTION_NOT_DISCOVERABLE | informational | escalate | Requested action not in catalog |
| ENTRY_VALIDATION_FAILED | warning | abort | Channel input doesn't meet required_fields |
| SCOPE_CONFLICT | warning | recheck | Multiple matching scopes have conflicting rules |
| REVIEW_REQUIRED | informational | wait | ReviewBundle must be approved before proceeding |
| REVIEW_REJECTED | elevated | recheck | ReviewBundle was rejected by reviewer |

---

## Part 4 — What CONCORD Has That Stripe Doesn't (Preserve These)

For completeness, areas where CONCORD v0.3 is already ahead and the v0.4 work should not regress:

| CONCORD advantage | Stripe gap | Preservation note |
|---|---|---|
| Trust tiers (T0–T4) with graduated authority | No public equivalent | New entities must respect AgentClass constraints |
| Risk-weighted budgets with circuit breakers | Hard-coded 2-round limit | Fleet budgets must compose with existing BudgetProfile model |
| Saga/compensation with poison handling | No rollback model | Fleet abort must trigger saga compensation for active members |
| Consistency profiles (5 levels) | Not addressed | ExecutionEnvironment state must declare consistency profile |
| Conflict resolution strategies (6 types) | Not addressed | Fleet resource contention must use declared strategies |
| Scan readiness & danger analysis | No adoption wedge | New entities must be scannable and scoreable |
| Explicit advisory vs. authoritative separation | Not addressed | ActionDiscovery must be advisory, consistent with OperationContext semantics |
| Idempotency as a first-class contract requirement | Not addressed | DispatchRequest must carry idempotency_key |

---

## Appendix A — Entity Relationship Summary (v0.4 Additions)

```
EntryPoint ──adapts──→ DispatchRequest ──belongs_to──→ TaskFleet
                              │                            │
                              │                            ├── owns ──→ BudgetLedger (fleet-level)
                              │                            │
                              ▼                            ▼
                         Intent ◄──── Session ──bound_to──→ ExecutionEnvironment
                              │           │
                              │           ├── queries ──→ ActionDiscovery
                              │           │
                              │           ├── receives ──→ ContextScope (via OperationContext)
                              │           │
                              ▼           ▼
                         Receipt ──aggregated_into──→ ReviewBundle
```

---

## Appendix B — ForgeWorks Integration Notes

The ForgeWorks ↔ SAM contract (JOINT-001) maps to the proposed entities as follows:

- **ForgeWorks pipeline stages** (ingest→normalize→validate→run→score→report) remain ActionContracts within the existing model. No changes needed.
- **Planner loop** (execute_planner_request with DONE/REPLAN/STOP_FAILED) maps to a single DispatchRequest lifecycle. REPLAN is a retry within the dispatch's max_attempts.
- **ForgeWorks error taxonomy** (retryable, user_fixable, dev_action_required, pipeline_error) aligns with the existing Error Catalog agent_should guidance. The new fleet/environment codes extend but don't replace it.
- **Evaluation gate concept** (shadow run before PENDING_APPROVAL) maps naturally to ReviewBundle: the shadow run produces a ReviewBundle, and the deploy action's guard predicate requires bundle_status = approved.
- **Multi-domain expansion** (benchmark, regression, experiment, security ticket types) would each define their own ContextScopes with domain-specific rules, oracle definitions, and scoring criteria.

---

*End of proposal. Ready for gap analysis review and spec integration planning.*
