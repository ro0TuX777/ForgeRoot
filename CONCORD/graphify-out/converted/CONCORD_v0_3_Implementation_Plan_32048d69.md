<!-- converted from CONCORD_v0_3_Implementation_Plan.docx -->


CONCORD v0.3
Phased Implementation Plan
A developer handoff brief for building CONCORD from the v0.3 spec pack


# 1. How to use this document
This document translates the four CONCORD v0.3 specification documents into an ordered implementation plan. Each phase specifies what to build, which spec sections to reference, what the deliverables are, how to validate completion, and what dependencies exist on prior phases.
The plan assumes a single AI developer (or small team) working in a modern IDE with access to the spec pack. The recommended stack is TypeScript on Node.js, but the phase structure is language-agnostic. Adjust module boundaries as appropriate for your runtime.
Important: Before starting Phase 0, resolve all P0 items from the CONCORD v0.3 Punch List. Those items define sub-object schemas (GuardPredicate, SideEffect, CircuitBreakerThresholds, structured blocked_reasons) and the complete error code metadata table. Every subsequent phase depends on these being fully specified.
# 2. Recommended stack and project structure
## Stack
- Runtime: TypeScript on Node.js (or Deno). Strong typing aligns with the schema-heavy spec.
- Storage interfaces: Abstract behind repository interfaces. Reference implementation can use PostgreSQL or SQLite. Production implementations will vary.
- API layer: Express, Fastify, or Hono. The framework should be HTTP-framework-agnostic at the core.
- Validation: Zod or AJV for runtime schema validation from the normative type definitions.
- Testing: Vitest or Jest. The worked example in Runtime Schemas §8 becomes the primary integration test fixture.
## Project layout
concord/
src/
types/           # All entity types, enums, error codes
contracts/       # ActionContract, StateContract loaders + validators
resources/       # Resource store interface, version-aware CRUD
identity/        # Session, Intent, AgentClass, CapabilitySet
budget/          # BudgetProfile, BudgetLedger, circuit breakers
coordination/    # Lease manager, Token allocator, conflict resolver
recovery/        # Receipt builder, SagaRun engine, compensation
context/         # OperationContext assembler
observability/   # Telemetry collector, event log
scanner/         # Codebase parser, readiness scorer, danger mapper
api/             # HTTP route layer (discovery, resource, action, coordination)
stores/          # Repository implementations (Postgres, SQLite, in-memory)
test/
fixtures/        # Worked example contracts (change_request)
unit/            # Per-module unit tests
integration/     # End-to-end against worked example
docs/              # Spec pack files for reference
# 3. Phase dependency map
The diagram below shows the critical dependency chain. Each phase builds on the deliverables of its predecessors. Phases 7 and 8 can run in parallel. Phase 9 depends on types from Phase 0 and contracts from Phase 1 but is otherwise independent and can begin early.

Parallel track: Phase 9 (scanner) can begin as soon as Phase 1 is complete. It shares types with the runtime but does not depend on the runtime stores or coordination logic. A team with two developers should run Phase 9 in parallel with Phases 2–8.

# 4. Phase details
# Phase 0
Foundation and Type Definitions
Goal: Establish every entity type, enum, and error code as validated TypeScript types. No runtime behavior in this phase — only the type system that every subsequent module imports.
Spec references: Core Spec §3 (entity definitions), Error Catalog §1–4 (all codes + metadata), Runtime Schemas §2 (normative conventions), §3.1–3.2 (ActionContract fields), §4 (StateContract fields), §5 (Budget fields), §6 (Lease + Token fields), §7 (Telemetry fields).
## Deliverables
- Entity type definitions: Session, Intent, Resource, Lease, Token, Receipt, SagaRun, AgentClass, CapabilitySet, BudgetProfile, BudgetLedger, OperationContext.
- Contract type definitions: ActionContract (including GuardPredicate, SideEffect sub-objects), StateContract (including state object, transition object), CoordinationTelemetry (including hotspot entry).
- Enum definitions: trust tiers (T0–T4 with aliases), action families, consistency profiles, conflict resolution strategies, lease types, token types, saga statuses, circuit states, cooldown policies, retry classes, risk levels, compensation strategies, timeout policies.
- Error and conflict code registry: all 26 codes with full structured metadata (severity, retryable, retry_delay_hint_ms, agent_should, human_likely_needed, blocks_other_actions, requires_context_refresh). This must be a queryable registry, not just type declarations.
- Zod schemas (or equivalent) for runtime validation of every entity and contract.
## Key files
src/types/entities.ts
src/types/contracts.ts
src/types/enums.ts
src/types/errors.ts        # Code registry with metadata
src/types/schemas.ts       # Zod validation schemas
## Validation criteria
- Every field in every spec table maps to exactly one typed property.
- The error registry can be queried by code name and returns complete metadata.
- The Zod schemas can parse the reference JSON shapes from Runtime Schemas §3.4 and §8.4 without error.
- No runtime logic exists in this phase — only types, enums, validators, and the error registry.

# Phase 1
Contract Kernel
Goal: Build the contract loading, parsing, and validation layer. The system can ingest action contracts and state contracts, validate them against the spec rules, and expose a queryable contract registry. This is the formal application interface for agents.
Spec references: Runtime Schemas §3 (ActionContract schema + normative rules), §4 (StateContract schema + normative rules), §8 (worked example for validation).
## Deliverables
- ActionContract loader: reads contract definitions (JSON or YAML), validates against Zod schema, registers in a queryable contract registry.
- ActionContract validator: enforces normative rules from §3.3 (e.g., mutating actions must have idempotency_required = true; saga participants must declare compensation_strategy).
- StateContract loader: reads state machine definitions, validates state and transition objects.
- StateContract validator: enforces §4.3 rules (initial_state must exist in states; transitions must not reference undeclared states; terminal states must not allow workflow-advancing mutation; business state must not encode coordination state).
- State graph exporter: produces a traversable graph from a StateContract for use by the coordination and context layers.
- Contract registry: indexes loaded contracts by resource_type and action_name. Supports queries like "what actions are available for resource type X in state Y?"
## Key files
src/contracts/action-contract.ts       # Loader + validator
src/contracts/state-contract.ts        # Loader + validator + graph
src/contracts/registry.ts              # Queryable index
test/fixtures/change_request.json      # Worked example from spec
## Validation criteria
- The change_request worked example from Runtime Schemas §8 loads, validates, and registers without errors.
- Deliberately invalid contracts (missing idempotency on a mutate action, transition referencing undeclared state, business state encoding lease ownership) are rejected with specific error messages.
- The registry answers: "Given resource_type=change_request and business_state=draft, what actions are available?" correctly.

# Phase 2
Resource and Version Layer
Goal: Implement the resource store with separated business/coordination state, version-aware mutation, idempotency key tracking, and structured error responses. This is the persistence foundation that every coordination and recovery component depends on.
Spec references: Core Spec §3.3 (Resource entity, separated state fields), §5 (consistency profiles + prescribed behaviors), §7 (conflict resolution — version check step). Error Catalog §2 (STALE_VERSION, DUPLICATE_INTENT). Runtime Schemas §3.1 (consistency_profile, idempotency fields).
## Deliverables
- Resource repository interface: abstract interface for CRUD with version-aware writes. Implementations for in-memory (testing) and PostgreSQL (reference).
- Version-aware mutation: compare-and-swap on write. Returns STALE_VERSION with full error metadata on version mismatch.
- Idempotency key store: tracks idempotency keys per scope (session, resource, global). Returns DUPLICATE_INTENT on replay.
- Consistency profile enforcement: implement prescribed behaviors for STRONG and SESSION_MONOTONIC. EVENTUAL and ASYNC_PROJECTION behaviors can be stubbed in this phase but must enforce authoritative recheck flags.
- Structured error responses: every failure returns the JSON shape from Error Catalog §6 with complete metadata from the error registry.
## Key files
src/resources/repository.ts            # Abstract interface
src/resources/version-guard.ts         # Compare-and-swap logic
src/resources/idempotency.ts           # Key tracking
src/resources/consistency.ts           # Profile enforcement
src/stores/memory-store.ts             # In-memory implementation
src/stores/pg-store.ts                 # PostgreSQL implementation
## Validation criteria
- A resource can be created, read, and updated with version tracking.
- A stale-version write returns STALE_VERSION with retryable=true, agent_should=recheck, requires_context_refresh=true.
- A duplicate idempotency key returns DUPLICATE_INTENT and does not mutate state.
- business_state and coordination_state are stored and returned as separate fields.

# Phase 3
Identity, Trust, and Intent
Goal: Build the session lifecycle, intent journal, agent class resolution, and capability checking. This is the layer that answers "who is acting, what are they trying to do, and are they allowed?"
Spec references: Core Spec §3.1 (AgentClass), §3.2 (CapabilitySet with exclusions and override semantics), §3.3 (Session, Intent entities). Error Catalog §3 (NOT_AUTHORIZED_FOR_AGENT_CLASS, OVERRIDE_DENIED).
## Deliverables
- Session manager: create, validate, expire sessions. Track mode (read_only, propose_only, execute, supervised). Enforce session_watermark for SESSION_MONOTONIC consistency.
- Intent journal: append-only log of intents. Track statuses (proposed, admitted, queued, blocked, executing, committed, compensated, failed, expired). Support idempotency key deduplication.
- AgentClass resolver: given an agent_class_id, resolve composed capability sets, compute effective permissions (union of capability set grants minus exclusions minus override restrictions). Reject expansion beyond composed sets unless a PolicyExpansionGrant is present.
- Capability checker: given a session (with agent class) and an action contract, determine whether the action is admissible based on trust tier, allowed action families, restricted resource types, lease permissions, and exclusion rules.
- Trust tier enforcer: actions with required_trust_tier higher than the agent class trust tier are rejected with NOT_AUTHORIZED_FOR_AGENT_CLASS.
## Key files
src/identity/session.ts                # Session lifecycle
src/identity/intent.ts                 # Intent journal
src/identity/agent-class.ts            # Class resolver + capability checker
src/identity/trust.ts                  # Trust tier enforcement
## Validation criteria
- A T1/propose agent cannot execute a T2/bounded action.
- A capability set with an exclusion (e.g., resource_tag: production, unless trust_tier >= T3) correctly denies a T2 agent on production resources and allows a T3 agent.
- Override rules restrict but do not expand permissions.
- An intent submitted with a duplicate idempotency key is collapsed, not duplicated.

# Phase 4
Budget and Policy Enforcement
Goal: Implement two-tier budget enforcement (gateway + intent layer), circuit breakers, and cooldown policies. This is the layer that prevents valid-but-dangerous volume.
Spec references: Core Spec §6 (budget enforcement model, two-tier architecture). Runtime Schemas §5 (BudgetProfile, BudgetLedger schemas). Error Catalog §2 (BUDGET_EXCEEDED, CIRCUIT_OPEN).
## Deliverables
- BudgetProfile store: load and query budget profiles by ID.
- BudgetLedger manager: track live usage (actions consumed, risk-weighted cost units, parallel leases, queue slots). Sliding window calculations for per-minute, per-hour, and per-day limits.
- Gateway enforcer: coarse checks (requests per minute, burst limit, concurrent requests, circuit state). Cheap rejection before any business logic runs.
- Intent-layer enforcer: fine-grained checks (risk-weighted budget, mutating action quotas, per-resource-class limits, per-action-family limits, compensation rate). Authoritative for admission decisions.
- Circuit breaker: implement closed/throttled/open state machine. Threshold evaluation from CircuitBreakerThresholds object. Trip recovery per trip_recovery_policy (auto_after_cooldown, manual_reset, gradual_ramp).
- Cooldown engine: implement all five cooldown policies (fixed_backoff, exponential_backoff, contention_scaled, risk_scaled, manual_resume_required). Return cooldown_until in budget responses.
- Budget failure responses: return BUDGET_EXCEEDED with specific budget dimension exceeded and cooldown guidance. Return CIRCUIT_OPEN when breaker is tripped.
## Key files
src/budget/profile.ts                  # Profile store
src/budget/ledger.ts                   # Ledger manager
src/budget/gateway.ts                  # Gateway-level enforcement
src/budget/intent-admission.ts         # Intent-layer enforcement
src/budget/circuit-breaker.ts          # Breaker state machine
src/budget/cooldown.ts                 # Cooldown policies
## Validation criteria
- A session exceeding max_mutating_actions_per_hour is rejected with BUDGET_EXCEEDED at the intent layer, even if gateway allows the request.
- A budget failure response includes the specific dimension exceeded (e.g., "mutating_actions_per_hour").
- A circuit breaker trips after threshold violations and recovers according to configured policy.
- Contention-scaled cooldown increases backoff under high hotspot conditions.

# Phase 5
Coordination Primitives
Goal: Implement leases, tokens, conflict resolution, and the admission pipeline that combines version checks, lease checks, queue admission, and policy arbitration. This is where multi-agent safety lives.
Spec references: Core Spec §7 (conflict resolution strategies). Runtime Schemas §6 (Lease, Token schemas). Error Catalog §2 (LEASE_HELD, QUEUE_REQUIRED, QUEUE_AVAILABLE, CAPACITY_EXHAUSTED, QUORUM_INCOMPLETE).
## Deliverables
- Lease manager: acquire, release, renew, revoke, expire. Enforce expires_at invariant (leases must expire; dead agents must not deadlock). Track renewal_count. Emit LEASE_HELD when contended.
- Token allocator: issue, return, expire tokens. Support capacity (bounded parallelism), quorum (n-of-m), validation_gate, and deployment_gate types. Enforce issuance_rule per token.
- Conflict resolution engine: given a resource type and its declared conflict_resolution_strategy, execute the resolution steps in declared order. Support all six strategy presets (default, fail_fast, queue_first, lease_first, policy_first, custom).
- Admission pipeline: the full sequence that evaluates an intent against version state, lease state, queue state, budget state, policy, and trust. Returns the first blocking condition as a structured conflict code with agent guidance.
- Queue manager (if not deferred): FIFO queue with optional priority. Track queue position. Emit QUEUE_REQUIRED and QUEUE_AVAILABLE appropriately.
## Key files
src/coordination/lease.ts              # Lease lifecycle
src/coordination/token.ts              # Token allocator
src/coordination/conflict.ts           # Conflict resolution engine
src/coordination/admission.ts          # Full admission pipeline
src/coordination/queue.ts              # Queue manager (deferrable)
## Validation criteria
- Two agents attempting to acquire an exclusive edit lease on the same resource: one succeeds, the other receives LEASE_HELD with retry_delay_hint_ms and agent_should=wait.
- A lease expires after expires_at and becomes acquirable by another session.
- A fail_fast strategy skips queue and returns immediate rejection on version or lease conflict.
- The admission pipeline checks version, then lease, then queue, then budget, then policy — in that order for the default strategy.

# Phase 6
Recovery, Receipts, and Sagas
Goal: Implement the receipt builder, saga lifecycle with timeout policies and poison handling, and compensation chain execution. Every operation emits a machine-verifiable receipt. Multi-step operations are tracked as sagas with bounded recovery.
Spec references: Core Spec §8 (saga and compensation rules), §9 (required observability — receipts with duration_ms). Runtime Schemas §8 (worked example receipts). Error Catalog §3 (SAGA_TIMED_OUT, SAGA_POISONED, COMPENSATION_FAILED).
## Deliverables
- Receipt builder: on every action outcome (success or failure), produce a Receipt with operation_id, intent_id, previous_state, next_state, version_before, version_after, result_status, duration_ms, policy_decision, warnings, errors. Store in receipt store.
- SagaRun engine: create saga from a root intent. Track ordered steps, current step, per-step commit receipts. Implement all four timeout policies (fixed, step_adaptive, heartbeat, external_gated).
- Timeout enforcer: background process that evaluates running sagas against their timeout policy. Transitions to timed_out and triggers compensation when deadline is breached.
- Compensation executor: given a saga in compensating state, execute compensation handlers in reverse order per compensation_order_hint. Track attempt count. Transition to poisoned when max_compensation_attempts is exceeded.
- Poison handler: sagas in poisoned state emit SAGA_POISONED, block automatic retry, and flag human_intervention_required. Explicit reopen action required to resume.
## Key files
src/recovery/receipt.ts                # Receipt builder + store
src/recovery/saga.ts                   # SagaRun engine
src/recovery/timeout.ts                # Timeout policy evaluator
src/recovery/compensation.ts           # Compensation chain executor
## Validation criteria
- Every successful and failed action produces a receipt with all required fields including duration_ms.
- A fixed-timeout saga transitions to timed_out after deadline and begins compensation.
- A saga whose compensation fails 3 times (with max_compensation_attempts = 3) transitions to poisoned.
- A poisoned saga cannot be automatically retried and requires explicit reopen.

# Phase 7
OperationContext and API Surface
Goal: Build the OperationContext assembler (the composite planning surface for agents) and the full HTTP API layer. This is the external interface that agents and control services consume.
Spec references: Core Spec §4 (OperationContext contract, advisory semantics, freshness fields). Runtime Schemas §8.4 (sample OperationContext JSON). Core Spec §10 / Runtime Schemas §9 (minimum implementation profile).
## Deliverables
- OperationContext assembler: composite read from resource store, contract registry, lease manager, token allocator, queue manager, budget ledger, and intent journal. Produce a single response with all fields from Core Spec §4. Include context_assembled_at, context_ttl_ms, freshness_status. Set authoritative_for_mutation = false always.
- Freshness calculator: compute freshness_status based on consistency profile and projection lag. Emit STALE_READ_WARNING when lag exceeds tolerance.
## API categories (from v0.1 §11)
- Discovery APIs: list resource types, list action contracts, get state graph, get policy rules.
- Resource APIs: fetch resource, fetch version, fetch allowed actions, fetch coordination state.
- Action APIs: perform action (full admission pipeline), validate only (dry run), simulate action, explain failure.
- Coordination APIs: request lease, release lease, renew lease, join queue, claim task, view contention.
- Context API: GET /resources/{id}/context — the canonical OperationContext endpoint.
- Recovery APIs: list unresolved intents, resume operation, fetch receipts, compensate action.
## Validation criteria
- GET /resources/cr_2048/context returns a response matching the sample JSON from Runtime Schemas §8.4 (adjusting for live state).
- The context response includes structured blocked_reasons (not flat strings) with reason_code, unblock_condition.
- Performing a mutating action through the API runs the full admission pipeline (version, lease, capability, budget, policy) and returns a receipt.
- validate-only mode returns what would happen without mutating state.

# Phase 8
Observability and Telemetry
Goal: Implement the coordination telemetry collector, event log, and hotspot detection. This makes the runtime governable by operators and debuggable when coordination creates bottlenecks.
Spec references: Core Spec §9 (required observability). Runtime Schemas §7 (CoordinationTelemetry schema, hotspot entry).
## Deliverables
- Telemetry collector: aggregate windowed metrics across lease, queue, version, budget, circuit breaker, compensation, and retry subsystems. Produce CoordinationTelemetry snapshots per the §7 schema.
- Event log: append-only log linking session, intent, resource version change, and action outcome for every mutating path. Queryable by resource, session, or time range.
- Hotspot detector: rank resources by composite contention/failure score. Identify primary cause per hotspot. Emit recommended_action when patterns suggest configuration changes (e.g., shorten lease TTL, increase token capacity).
- Retry distribution tracker: histogram of retries keyed by retry class (safe_retry, recheck_then_retry, queue_then_retry). Feeds into circuit breaker threshold evaluation.
- Telemetry API: expose telemetry as point-in-time JSON and time-series-friendly records per Runtime Schemas §10 guidance.
## Validation criteria
- After a sequence of contended lease requests, lease_contention_rate is calculated correctly for the observation window.
- The hotspot detector identifies a resource with high stale-write rejection rate as a hotspot with the correct primary_cause.
- Every mutating action produces an event log entry linking session, intent, and version change.

# Phase 9
Scanner and Discovery Engine
Goal: Build the CONCORD Scan toolchain: codebase parser, readiness scorer, danger mapper, resource dependency graph builder, and patch planner. This is the adoption wedge — the first thing teams run before committing to any runtime components.
Spec references: Scan Output Schemas §1–6 (all scanner output schemas). Core Spec §5 (discovery and refactor layer description).
Note: This phase can begin in parallel after Phase 1 is complete. It shares types from Phase 0 and contract definitions from Phase 1 but does not depend on the runtime stores, coordination, or recovery layers.
## Deliverables
- Codebase parser: scan a target backend to identify routes, controllers, services, data models, validators, middleware, state-like fields, background jobs, event emitters, and exception handlers. Support Express/Fastify/NestJS patterns initially. Extensible for other frameworks.
- Readiness scorer: evaluate the target across dimensions (action contracts, state explicitness, consistency, idempotency, trust/budget, coordination, recovery, observability). Produce overall_maturity_level (Level 0–6) and per-dimension scores. Distinguish discovered evidence from inferred evidence.
- Danger mapper: produce single-point danger findings with all fields from Scan Schemas §3. Detect compound dangers where two or more single-point risks converge. Score compound dangers above any individual contributing risk. Include confidence_level per finding.
- Resource dependency graph builder: map resources, jobs, projections, and external dependencies as nodes. Map relationships (mutates, reads_before_mutation, projects_to, background_updates, triggers, depends_on_external) as edges. Detect consistency mismatches across edges and saga coverage gaps.
- Patch planner: group remediation steps into ordered work items with priority, affected assets, expected control gain, estimated complexity, and predecessor dependencies. Output format per Scan Schemas §5.
- Action catalog generator: infer potential action contracts from discovered routes and controllers. Output as draft ActionContract objects that an implementer can refine.
## Key files
src/scanner/parser.ts                  # Codebase parser
src/scanner/readiness.ts               # Readiness scorer
src/scanner/danger.ts                  # Danger mapper (single + compound)
src/scanner/dependency-graph.ts        # Resource dependency graph
src/scanner/patch-planner.ts           # Remediation planner
src/scanner/action-inference.ts        # Draft action catalog generator
## Validation criteria
- Run the scanner against a sample Express app with known gaps (unversioned resources, non-idempotent destructive endpoints, background job conflicts). Verify the danger map flags all known issues.
- Compound danger detection: an eventually-consistent read feeding a non-idempotent write on an unversioned resource is flagged as compound with severity above any individual risk.
- The readiness report accurately scores a fully-contracted CONCORD app at Level 3+ and a raw Express CRUD app at Level 0–1.
- The patch plan produces actionable work items in dependency order.

# 5. Integration validation
After all phases are complete, the following end-to-end tests validate that the full system works together against the spec's worked example.
## Test 1: Full change_request lifecycle
- Load the change_request contracts from the worked example.
- Create a session for a T2/bounded agent with the example budget profile.
- Create a change_request resource in draft state.
- Acquire an edit lease. Submit an update. Verify receipt with duration_ms.
- Submit the change request (EVENTUAL consistency — verify authoritative recheck is enforced).
- Request a review token. Approve the change request with a T3/privileged agent session.
- Attempt deploy_change_request — verify human gate enforcement for critical risk.
- Verify OperationContext at each step returns correct allowed/blocked actions.
## Test 2: Multi-agent contention
- Two agent sessions attempt to acquire an edit lease on the same change_request.
- The losing agent receives LEASE_HELD with structured guidance.
- The losing agent rechecks context after lease expiry and successfully acquires.
- Budget ledger correctly tracks actions for both sessions.
## Test 3: Saga compensation
- Create a multi-step operation with a saga.
- Force step 3 to fail.
- Verify compensation runs in reverse order.
- Force compensation failure to exceed max_compensation_attempts.
- Verify saga transitions to poisoned and blocks automatic retry.
## Test 4: Budget and circuit breaker
- Exhaust max_mutating_actions_per_hour for a session.
- Verify next mutation is rejected with BUDGET_EXCEEDED and correct dimension.
- Trigger circuit breaker by exceeding stale_version_failure_rate_threshold.
- Verify CIRCUIT_OPEN is returned and recovery follows configured policy.

# 6. Effort estimates
These are rough sizing estimates for a single experienced developer working with AI assistance in an IDE. Adjust based on team size and familiarity with the domain.

Total estimated range: 37–54 working days for a single developer. With two developers (one on scanner, one on runtime), the critical path shortens to approximately 28–40 days.

# 7. Risk register

# 8. Definition of done
The CONCORD v0.3 implementation is complete when all of the following conditions are met:
- All Phase 0–8 deliverables pass their stated validation criteria.
- All four integration tests (change_request lifecycle, multi-agent contention, saga compensation, budget + circuit breaker) pass end to end.
- The scanner (Phase 9) produces accurate readiness reports and danger maps against at least one real-world sample backend.
- Every error and conflict code returned by the system matches the canonical metadata from the Error Catalog.
- The OperationContext endpoint returns all required fields from Core Spec §4 with correct freshness tracking.
- The worked example from Runtime Schemas §8 can be fully instantiated, executed through a lifecycle, and validated against receipts.
- A developer unfamiliar with CONCORD can read the spec pack, run the scanner against their backend, and get an actionable readiness report and danger map without assistance.
| Status | Implementation planning |
| --- | --- |
| Spec version | 0.3 normative draft |
| Date | March 2026 |
| Total phases | 10 (0 through 9) |
| Estimated scope | Phase 0–6: core framework; Phase 7–8: observability + API; Phase 9: scanner |
| Input documents | Core Spec, Error Catalog, Scan Output Schemas, Runtime Contract Schemas |
| Companion | CONCORD v0.3 Punch List (resolve P0 items before or during Phase 0) |
| Phase | Name | Hard dependencies | Soft dependencies |
| --- | --- | --- | --- |
| 0 | Foundation + types | Punch list P0 items | None |
| 1 | Contract kernel | Phase 0 | None |
| 2 | Resource + version layer | Phase 0, 1 | None |
| 3 | Identity, trust, + intent | Phase 0 | Phase 2 for integration |
| 4 | Budget + policy | Phase 0, 3 | Phase 2 for enforcement |
| 5 | Coordination | Phase 0, 1, 2 | Phase 3, 4 for full admission |
| 6 | Recovery + sagas | Phase 0, 2, 3 | Phase 5 for lease compensation |
| 7 | OperationContext + API | Phase 0–6 | None |
| 8 | Observability + telemetry | Phase 0, 5, 6 | Phase 7 for API exposure |
| 9 | Scanner + discovery | Phase 0, 1 | Can start after Phase 1 |
| Phase | Name | Effort | Complexity | Risk | Parallelizable |
| --- | --- | --- | --- | --- | --- |
| 0 | Foundation + types | 2–3 days | Low | Low | No |
| 1 | Contract kernel | 3–4 days | Medium | Low | No |
| 2 | Resource + version | 3–5 days | Medium | Medium | No |
| 3 | Identity + trust | 3–4 days | Medium | Medium | After Phase 0 |
| 4 | Budget + policy | 3–5 days | High | Medium | After Phase 3 |
| 5 | Coordination | 5–7 days | High | High | After Phase 2 |
| 6 | Recovery + sagas | 4–6 days | High | High | After Phase 3 |
| 7 | Context + API | 4–6 days | Medium | Medium | After Phase 6 |
| 8 | Observability | 3–4 days | Medium | Low | Parallel with 7 |
| 9 | Scanner | 7–10 days | High | High | After Phase 1 |
| Risk | Impact | Mitigation | Phase affected |
| --- | --- | --- | --- |
| Punch list P0 items not resolved before Phase 0 | Every phase builds on undefined sub-object schemas | Block Phase 0 start on P0 completion; treat as hard prerequisite | All phases |
| Admission pipeline complexity in Phase 5 | Ordering of version/lease/queue/budget/policy checks interacts with conflict strategy configuration | Build default strategy first; defer custom strategy support; test exhaustively against worked example | Phase 5, 7 |
| Scanner accuracy for diverse frameworks | Parser may miss patterns in unfamiliar frameworks | Start with Express/Fastify only; design parser as pluggable; accept lower confidence on unknown patterns | Phase 9 |
| Saga timeout edge cases | step_adaptive and heartbeat policies are complex to implement correctly | Implement fixed timeout first; add other policies incrementally; fuzz-test timeout boundaries | Phase 6 |
| Consistency profile enforcement under real storage backends | EVENTUAL and ASYNC_PROJECTION behavior depends on storage topology | Define abstract consistency interface; implement STRONG and SESSION_MONOTONIC first; stub others with authoritative recheck enforcement | Phase 2 |