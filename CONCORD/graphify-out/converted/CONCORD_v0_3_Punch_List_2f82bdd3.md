<!-- converted from CONCORD_v0_3_Punch_List.docx -->


CONCORD v0.3
Spec Pack Punch List
Consolidated gap list for implementation completion

Scope: This punch list identifies gaps across the four-document CONCORD v0.3 specification pack (Core Specification, Error and Conflict Code Catalog, Scan Output Schemas, Runtime Contract Schemas). Each item specifies the affected document, section, required work, and acceptance criteria. Items are prioritized by implementation impact.

# Priority Legend

# P0 — Required for Implementation
PL-01  —  Complete error code metadata table
Document: Error Catalog    Section: §4
Required work: Expand Section 4 from 5 example rows to full metadata for all 26 codes. Every code must have canonical values for retryable, retry_delay_hint_ms, agent_should, human_likely_needed, blocks_other_actions, and requires_context_refresh. Implementers must not infer these values.
Acceptance criteria:
- All 16 conflict codes have complete metadata rows
- All 10 error codes have complete metadata rows
- No field is left to implementer inference
PL-02  —  Define GuardPredicate schema
Document: Runtime Schemas    Section: §3.1
Required work: ActionContract requires guard_predicates as array<object> but the object shape is undefined. Define a schema with at minimum: name (string, required), guard_type (enum: state_check, field_check, coordination_check, policy_check), parameters (object, optional), evaluation_order (integer, optional). Specify that guards are evaluated in declared order with short-circuit on first failure.
Acceptance criteria:
- GuardPredicate object schema is formalized with types and required/optional markers
- Evaluation semantics (order, short-circuit) are stated
- Reference JSON example updated to show parameterized guard
PL-03  —  Define SideEffect schema
Document: Runtime Schemas    Section: §3.2
Required work: ActionContract includes side_effects as array<object> with no object definition. Define a schema with: effect_type (enum: write, event, job, notification, external_call), target_resource or target_system (string), reversible (boolean), description (string, optional). Side effect declarations are required for danger map generation and saga coverage analysis.
Acceptance criteria:
- SideEffect object schema is formalized
- Scanner can consume side effect declarations for danger map analysis
- Worked example updated to include at least one side effect
PL-04  —  Define CircuitBreakerThresholds schema
Document: Runtime Schemas    Section: §5.1
Required work: BudgetProfile requires circuit_breaker_thresholds as object but fields are undefined. Define: stale_version_failure_rate_threshold (number), compensation_rate_threshold (number), queue_wait_ms_threshold (integer), lease_contention_rate_threshold (number), high_risk_action_rate_threshold (number), evaluation_window_ms (integer), trip_recovery_policy (enum: auto_after_cooldown, manual_reset, gradual_ramp).
Acceptance criteria:
- All threshold fields have types and defaults
- Trip and recovery behavior is specified
- Budget profiles are portable across implementations
PL-05  —  Structure blocked_reasons in OperationContext
Document: Core Spec + Runtime Schemas    Section: §4 / §8.4
Required work: Replace flat string array with structured objects. Each blocked reason should include: action (string), reason_code (string, referencing Error Catalog), unblock_condition (string), estimated_wait_ms (integer, optional). The current flat format is human-readable but not machine-actionable, which undercuts Law 10.
Acceptance criteria:
- blocked_reasons is array<object> with defined fields
- reason_code references the Error Catalog
- Worked example updated with structured blocked_reasons
- Agents can programmatically determine unblock conditions

# P1 — Important for Completeness
PL-06  —  Define custom conflict resolution strategy format
Document: Core Spec    Section: §7
Required work: The conflict_resolution_strategy field supports 'custom' but the format for declaring a custom resolution order is not defined. Add a schema: ordered array of resolution step names (version_check, lease_check, queue_admission, retry_backoff, policy_arbitration, human_escalation, negotiation). Include validation rule that custom strategies must include at least version_check.
Acceptance criteria:
- Custom strategy format is defined as ordered step array
- Minimum required steps are specified
- Example custom strategy is provided
PL-07  —  Add spec versioning and evolution policy
Document: All four documents    Section: New section
Required work: Define how the spec itself evolves. Required: what constitutes a breaking change (new required field, removed field, changed type, changed enum values); minor version policy (new optional fields are additive); deprecation timeline (removed fields deprecated for one minor version before removal); implementation conformance claim format (e.g., 'CONCORD v0.3 Level 2').
Acceptance criteria:
- Versioning rules are documented
- Breaking vs. additive change distinction is clear
- Deprecation lifecycle is defined
- Conformance claim format is specified
PL-08  —  Consolidate minimum implementation profile
Document: Core Spec + Runtime Schemas    Section: §10 / §9
Required work: Both documents define minimum implementation requirements with slightly different framing. Designate one document as authoritative for the minimum profile and have the other reference it by section number. Explicitly state which coordination features are MVP (basic exclusive leases, lease expiry, version checks) versus Phase 3 (queues, fairness policies, configurable conflict strategies, consistency profile handling).
Acceptance criteria:
- Single authoritative minimum profile location
- Cross-reference from the other document
- MVP vs. Phase 3 coordination boundary is explicit
PL-09  —  Add RETRY_RECOMMENDED conflict code
Document: Error Catalog    Section: §2
Required work: The v0.2 amendments proposed RETRY_RECOMMENDED as a conflict code but it does not appear in the Error Catalog. Add with metadata: severity informational, agent_should retry, retryable true, retry_delay_hint_ms as configured, human_likely_needed false, blocks_other_actions false, requires_context_refresh false. This code covers cases where retry is the cleanest path but no specific conflict class applies.
Acceptance criteria:
- Code added to Section 2 with full row
- Full metadata added to Section 4
- Distinction from STALE_VERSION (which requires recheck, not blind retry) is clear

# P2 — Strengthening
PL-10  —  Add rollback_rules and hook object schemas to StateContract
Document: Runtime Schemas    Section: §4.1
Required work: StateContract declares rollback_rules, entry_hooks, and exit_hooks as array<object> but the object schemas are not defined. Provide minimal shapes: rollback rule (from_state, to_state, compensation_ref, requires_approval); hook (hook_name, hook_type: event | validation | notification, trigger_ref, async: boolean).
Acceptance criteria:
- Rollback rule object has defined fields
- Hook object has defined fields
- Worked example includes at least one hook
PL-11  —  Add on_success schema to transition object
Document: Runtime Schemas    Section: §4.2
Required work: The transition object includes on_success as optional but does not define its shape. Specify: receipts (array<string>), events (array<string>), hooks (array<string>). These are reference identifiers, not inline definitions.
Acceptance criteria:
- on_success object shape is defined
- Reference-based rather than inline
- Worked example includes on_success on at least one transition
PL-12  —  Add confidence_level field to scanner danger findings
Document: Scan Schemas    Section: §3 / §6
Required work: Section 6 notes that scanners should emit confidence bands rather than hard assertions when confidence is low, but the danger map schema has no confidence field. Add confidence_level (enum: confirmed, high_confidence, inferred, heuristic) to both single-point and compound danger schemas.
Acceptance criteria:
- confidence_level field added to danger map schema
- confidence_level field added to compound danger schema
- Section 6 guidance and schema are aligned
PL-13  —  Expand Token issuance_rule from free-text to structured
Document: Runtime Schemas    Section: §6.2
Required work: Token.issuance_rule is typed as string, which means every implementation will encode allocation policy differently. Define an enum of issuance strategies (first_come, role_priority, round_robin, manual_grant, policy_ref) with an optional policy_ref string for custom rules. This makes token behavior portable.
Acceptance criteria:
- issuance_rule is enum + optional policy_ref
- Standard strategies are enumerated
- Custom rules reference a policy artifact

# P3 — Nice to Have
PL-14  —  Add second worked example for a different resource profile
Document: Runtime Schemas    Section: §8
Required work: The change_request example is excellent but uses primarily EVENTUAL and STRONG consistency. Add a second reference example that exercises ASYNC_PROJECTION, token-based quorum, and saga compensation — such as a deployment_request or financial_transaction — so implementers can see how the more advanced contracts fit together.
Acceptance criteria:
- Second worked example with different consistency/coordination profile
- Exercises token, saga, and ASYNC_PROJECTION paths
- Includes OperationContext sample response
PL-15  —  Add cross-document reference index
Document: All four documents    Section: New appendix
Required work: Create a reference table mapping each entity, code, and schema to its authoritative document and section. This prevents implementers from hunting across four documents for the canonical definition of a concept. Can be an appendix in the Core Specification or a standalone one-page index.
Acceptance criteria:
- Every entity maps to one authoritative document/section
- Every error/conflict code maps to Error Catalog section
- Every schema maps to Runtime Schemas section
PL-16  —  Add PolicyExpansionGrant artifact schema
Document: Runtime Schemas or Core Spec    Section: New subsection
Required work: CapabilitySet override semantics state that expansion beyond composed capability sets requires a PolicyExpansionGrant artifact, but this artifact has no schema. Define: grant_id, requesting_agent_class, expanded_capabilities, justification, approved_by, expires_at, scope_constraints.
Acceptance criteria:
- PolicyExpansionGrant schema is defined
- Lifecycle (request, approve, expire) is specified
- Audit trail requirements are stated

# Summary Matrix
Complete reference of all punch-list items by priority, target document, and status.

# Implementation Guidance
## Recommended execution order
P0 items should be completed as a single batch before any implementation work begins against the spec pack. They define object shapes that every other contract references. P1 items should be completed before v0.3 is marked stable. P2 and P3 items can be addressed incrementally.
## Dependency chain
PL-02 (GuardPredicate) and PL-03 (SideEffect) should be completed together, as both feed into the ActionContract schema and the worked example. PL-04 (CircuitBreakerThresholds) completes the BudgetProfile schema. PL-05 (blocked_reasons) updates both the Core Specification and the Runtime Schemas worked example. PL-01 (error metadata) is independent and can be completed in parallel with any other item.
## Validation rule
After P0 completion, the worked example in Runtime Schemas Section 8 should be re-validated end to end. Every field referenced in the example must trace to a defined schema. Every schema must have at least one concrete value in the example. If the example cannot be fully instantiated from the schemas alone, there is still a gap.
## Definition of done for the spec pack
The spec pack is implementation-ready when: (1) all P0 and P1 items are resolved, (2) the worked example can be fully instantiated from schema definitions alone, (3) every error/conflict code has complete canonical metadata, (4) a single authoritative location exists for the minimum implementation profile, and (5) an implementer reading only the four documents plus this punch list can build a conformant runtime without making unguided decisions on normative behavior.
| Status | Open |
| --- | --- |
| Version | 0.3 |
| Date | March 2026 |
| Total items | 16 |
| P0 (required for implementation) | 5 |
| P1 (important for completeness) | 4 |
| P2 (strengthening) | 4 |
| P3 (nice to have) | 3 |
| Priority | Label | Meaning | Count |
| --- | --- | --- | --- |
| P0 | Required for implementation | Without these, an implementer must make unguided decisions on normative behavior | 5 |
| P1 | Important for completeness | Gaps that cause cross-implementation drift or governance ambiguity | 4 |
| P2 | Strengthening | Sub-object schemas and alignment fixes that improve portability | 4 |
| P3 | Nice to have | Additional examples, indexes, and secondary schema coverage | 3 |
| ID | Priority | Item | Document | Key deliverable |
| --- | --- | --- | --- | --- |
| PL-01 | P0 | Complete error code metadata table | Error Catalog | All 16 conflict codes have complete metadata rows |
| PL-02 | P0 | Define GuardPredicate schema | Runtime Schemas | GuardPredicate object schema is formalized with types and required/optional markers |
| PL-03 | P0 | Define SideEffect schema | Runtime Schemas | SideEffect object schema is formalized |
| PL-04 | P0 | Define CircuitBreakerThresholds schema | Runtime Schemas | All threshold fields have types and defaults |
| PL-05 | P0 | Structure blocked_reasons in OperationContext | Core Spec + Runtime Schemas | blocked_reasons is array<object> with defined fields |
| PL-06 | P1 | Define custom conflict resolution strategy format | Core Spec | Custom strategy format is defined as ordered step array |
| PL-07 | P1 | Add spec versioning and evolution policy | All four documents | Versioning rules are documented |
| PL-08 | P1 | Consolidate minimum implementation profile | Core Spec + Runtime Schemas | Single authoritative minimum profile location |
| PL-09 | P1 | Add RETRY_RECOMMENDED conflict code | Error Catalog | Code added to Section 2 with full row |
| PL-10 | P2 | Add rollback_rules and hook object schemas to StateContract | Runtime Schemas | Rollback rule object has defined fields |
| PL-11 | P2 | Add on_success schema to transition object | Runtime Schemas | on_success object shape is defined |
| PL-12 | P2 | Add confidence_level field to scanner danger findings | Scan Schemas | confidence_level field added to danger map schema |
| PL-13 | P2 | Expand Token issuance_rule from free-text to structured | Runtime Schemas | issuance_rule is enum + optional policy_ref |
| PL-14 | P3 | Add second worked example for a different resource profile | Runtime Schemas | Second worked example with different consistency/coordination profile |
| PL-15 | P3 | Add cross-document reference index | All four documents | Every entity maps to one authoritative document/section |
| PL-16 | P3 | Add PolicyExpansionGrant artifact schema | Runtime Schemas or Core Spec | PolicyExpansionGrant schema is defined |