# Graph Report - F:\ForgedRoot\CONCORD  (2026-05-04)

## Corpus Check
- 39 files · ~66,866 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 368 nodes · 474 edges · 52 communities detected
- Extraction: 57% EXTRACTED · 43% INFERRED · 0% AMBIGUOUS · INFERRED: 206 edges (avg confidence: 0.84)
- Token cost: 36,304 input · 12,492 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]

## God Nodes (most connected - your core abstractions)
1. `AdmissionPipeline` - 22 edges
2. `Session` - 13 edges
3. `AdmissionPipeline.process_intent` - 13 edges
4. `ExecutionResult` - 11 edges
5. `InMemorySessionStore` - 11 edges
6. `InMemoryReceiptStore` - 11 edges
7. `InMemoryIntentStore` - 10 edges
8. `_fresh_session()` - 9 edges
9. `Camp 1 what CONCORD must provide` - 8 edges
10. `Camp 2 integration agent instructions` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Phase 9 scanner and readiness toolchain` --semantically_similar_to--> `Capability audit before pipeline code`  [INFERRED] [semantically similar]
  graphify-out/converted/CONCORD_v0_3_Implementation_Plan_32048d69.md → integration-templates/CONCORD_INTEGRATION_GUIDE_v0.5.1.md
- `Admission boundary stages 1-8 no host side effects` --semantically_similar_to--> `Sequential fail-fast governance philosophy`  [INFERRED] [semantically similar]
  CONCORD_v0.5_Admission_Pipeline_Specification.md → CONCORDwhitepaper.md
- `BudgetSnapshot in OperationContext` --semantically_similar_to--> `GET /budget/status introspection`  [INFERRED] [semantically similar]
  CONCORD_v0.5_ReviewBundle_and_OperationContext.md → CONCORD_v0.5_Runtime_Endpoint_Contracts.md
- `Dynamic OperationContext planning oracle` --semantically_similar_to--> `Planning surface pre-admission endpoints`  [INFERRED] [semantically similar]
  CONCORD_v0.5_ReviewBundle_and_OperationContext.md → CONCORD_v0.5_Runtime_Endpoint_Contracts.md
- `Health: sdk_unavailable vs unreachable vs not ready` --semantically_similar_to--> `OperationContext planning endpoint`  [INFERRED] [semantically similar]
  CONCORD_SAM_Integration_Lessons.md → CONCORD_Integration_Lessons.md

## Hyperedges (group relationships)
- **Admission phase zero host side-effects** — concord_v0_5_admission_pipeline_specification_session_resolution, concord_v0_5_admission_pipeline_specification_action_resolution, concord_v0_5_admission_pipeline_specification_trust_gate, concord_v0_5_admission_pipeline_specification_budget_gate, concord_v0_5_admission_pipeline_specification_guard_evaluation, concord_v0_5_admission_pipeline_specification_input_validation, concord_v0_5_admission_pipeline_specification_idempotency_check, concord_v0_5_admission_pipeline_specification_intent_creation, concord_v0_5_admission_pipeline_specification_admission_boundary [INFERRED 0.88]
- **Execution normalization and settlement** — concord_v0_5_admission_pipeline_specification_execution, concord_v0_5_admission_pipeline_specification_output_normalization, concord_v0_5_admission_pipeline_specification_receipt_minting, concordwhitepaper_receipt [INFERRED 0.87]
- **Planning-time queries bypass admission pipeline** — concord_v0_5_runtime_endpoint_contracts_planning_surface, concord_v0_5_runtime_endpoint_contracts_budget_status, concord_v0_5_runtime_endpoint_contracts_budget_estimate, concord_v0_5_reviewbundle_and_operationcontext_dynamic_operationcontext, concord_v0_5_mcp_adapter_profile_planning_resources [INFERRED 0.84]
- **Post-deploy readiness and manifest** — concord_v0_5_admission_pipeline_specification_phase_four_lifecycle, concord_v0_5_admission_pipeline_specification_deployment_agent, concord_v0_5_integration_guide_connection_manifest, concord_v0_5_integration_guide_deploy_health_and_build, concord_v0_5_runtime_endpoint_contracts_deploy_status, concord_v0_5_error_catalog_amendments_deploy_codes [INFERRED 0.82]
- **Governed execution spans session intent pipeline receipt** — session_entity, intent_entity, admission_pipeline_mandatory, executor_layer, normalizer_layer, receipt_entity [EXTRACTED 0.95]
- **JSON Schema validates inputs at admission and outputs at minting** — json_schema_202012, input_validation_stage, receipt_minting_stage, invalid_parameters_error, output_normalization_failed_error [EXTRACTED 0.95]
- **Proposed v0.4 entities addressing Stripe-style gaps** — execution_environment_proposal, task_fleet_dispatch_proposal, action_discovery_proposal, entry_point_adapter_proposal, context_scope_proposal, review_bundle_lifecycle [EXTRACTED 0.90]
- **Ordered admission checks through receipt minting** — pipeline_stage_session_resolution, pipeline_stage_action_resolution, pipeline_stage_trust_gate, pipeline_stage_budget_gate, pipeline_stage_input_validation, pipeline_stage_guard_evaluation, pipeline_stage_idempotency_check, pipeline_stage_intent_creation, pipeline_stage_receipt_minting [INFERRED 0.91]
- **execute_process_chain internal executor sequence** — executors_execute_scan_pdf, executors_execute_extract_text, executors_execute_convert_format, executors_execute_validate_schema [INFERRED 0.96]
- **normalize_process_chain delegates to step normalizers** — normalizers_normalize_scan_pdf, normalizers_normalize_extract_text, normalizers_normalize_convert_format, normalizers_normalize_validate_schema [INFERRED 0.96]
- **Per-action guard, executor, normalizer wiring** — registry_guard_registry, registry_executor_registry, registry_normalizer_registry, registry_action_registry [INFERRED 0.87]
- **Guards vs executors vs normalizers responsibilities** — guards_service_healthy, guards_file_accessible, executors_execute_validate_schema, normalizers_normalize_validate_schema [INFERRED 0.84]
- **minimum_runtime_core_contracts** — n_action_contract, n_state_contract, n_session, n_intent, n_resource, n_lease, n_operation_context, n_receipt, n_budget_profile, n_budget_ledger [INFERRED 0.80]
- **consistency_profile_family** — n_consistency_strong, n_consistency_session_monotonic, n_consistency_ryw, n_consistency_eventual, n_consistency_async_proj, n_action_contract [INFERRED 0.80]
- **saga_timeout_poison_compensation_chain** — n_saga_run, n_err_saga_timed_out, n_err_saga_poisoned, n_err_compensation_failed [INFERRED 0.80]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (46): ActionContract registry, Mandatory admission pipeline (no bypass), agent_should on every catalog entry, /admin/backend/coverage audit proposal, Budget introspection /budget/status, Camp 1 what CONCORD must provide, Camp 2 integration agent instructions, Capability audit before pipeline code (+38 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (46): document.convert_format contract, document.extract_text contract, document.process_chain contract, document.scan_pdf contract, document.validate_schema contract, register_actions, execute_convert_format, execute_extract_text (+38 more)

### Community 2 - "Community 2"
Cohesion: 0.12
Nodes (9): Intent, IntentRequest, Receipt, AdmissionPipeline, _format_validation_error(), InMemoryIntentStore, InMemoryReceiptStore, InMemorySessionStore (+1 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (13): Session, _fresh_session(), test_budget_exhaustion_blocks_further_intents(), test_chain_action_budget_deduction(), test_chain_action_with_invalid_file_fails_gracefully(), test_intent_submit_with_executor_failure_returns_error(), test_intent_submit_with_insufficient_trust_returns_error(), test_intent_submit_with_missing_executor_returns_error() (+5 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (28): ActionContract, BudgetLedger, error_conflict_metadata_contract, AUTHORITATIVE_RECHECK_REQUIRED, BUDGET_EXCEEDED, DUPLICATE_INTENT, STALE_VERSION, EVENTUAL (+20 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (22): Draft202012Validator, refresh_session endpoint, Intent, IntentRequest, Receipt, Session, SessionRefreshRequest, TrustTier (+14 more)

### Community 6 - "Community 6"
Cohesion: 0.14
Nodes (15): register_actions(), execute_convert_format(), execute_extract_text(), execute_process_chain(), execute_scan_pdf(), execute_validate_schema(), register_executors(), register_guards() (+7 more)

### Community 7 - "Community 7"
Cohesion: 0.31
Nodes (10): NormalizationResult, SessionRefreshRequest, TrustTier, normalize_convert_format(), normalize_extract_text(), normalize_process_chain(), normalize_scan_pdf(), normalize_validate_schema() (+2 more)

### Community 9 - "Community 9"
Cohesion: 0.27
Nodes (4): Normative ordered admission and execution pipeline, Governed execution pipeline mental model, Human surface vs agent surface shared business logic, 11-stage deterministic admission pipeline

### Community 10 - "Community 10"
Cohesion: 0.29
Nodes (7): ActionDiscovery runtime service, ContextScope conditional rules, EntryPoint and AdmissionAdapter, ExecutionEnvironment entity proposal, ReviewBundle human-in-the-loop, Stripe minion architecture gap map, TaskFleet and DispatchRequest

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (6): Post-deploy readiness Phase 4 lifecycle, Deploy category Phase 4 error codes, connection_manifest.yaml and CONNECTION_MANIFEST.md, File-backed contracts and canonical output envelopes, B7 /deploy/status bridge startup gate, GET /deploy/status deployment readiness

### Community 12 - "Community 12"
Cohesion: 0.4
Nodes (5): Every entry point uses same pipeline, Stage 7 IdempotencyCheck, Stage 8 IntentCreation persistence, tools/call full 11-stage pipeline, Intent admission unit

### Community 13 - "Community 13"
Cohesion: 0.5
Nodes (4): Stage 11 ReceiptMinting and ledger update, GET /receipt/{receipt_id}, TypedActionResult and adapter init health contract v0.5.1, Immutable execution receipt

### Community 14 - "Community 14"
Cohesion: 0.5
Nodes (4): Guard Registry host-provided map, Step 1 capability audit to ActionContracts, Guard pre-evaluation dry run, ActionContract capability contract

### Community 15 - "Community 15"
Cohesion: 0.67
Nodes (3): Stage 4 BudgetGate, BudgetSnapshot in OperationContext, GET /budget/status introspection

### Community 16 - "Community 16"
Cohesion: 0.67
Nodes (3): Stage 10 OutputNormalization, REVIEW_REJECTED and REVISION_REQUESTED, ReviewBundle lifecycle states and polling

### Community 17 - "Community 17"
Cohesion: 0.67
Nodes (3): Stage 5 GuardEvaluation, review_approved guard predicate for HITL, GET /budget/estimate planning feasibility

### Community 18 - "Community 18"
Cohesion: 0.67
Nodes (3): ExecutorCallable translation and classification, Exception mapping table for executors, Executor pre-registration validation gate v0.5.1

### Community 19 - "Community 19"
Cohesion: 0.67
Nodes (3): concord:// resources for planning metadata, Dynamic OperationContext planning oracle, Planning surface pre-admission endpoints

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (2): Stage 2 ActionResolution, ACTION_DISABLED and ACTION_UNAVAILABLE v0.5.1

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (2): Stage 6 InputValidation JSON Schema 2020-12, Normative file/resource parameter naming v0.5.1

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (2): Admission boundary stages 1-8 no host side effects, Sequential fail-fast governance philosophy

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (2): Deployment Agent infrastructure actor, Name-derived deterministic host ports

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (2): SessionConstraints expiring_soon near_max_lifetime, POST /session/refresh auditable extension

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (2): Stage 1 SessionResolution, Admission and execution error codes v0.5

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (2): B1 MCP connection to CONCORD Session 1:1, AgentClass and trust tiers

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (2): agent_should required on all catalog entries, CONCORD errors as MCP isError structuredContent

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): CONCORD governance and admission pipeline

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (2): Phase 0 foundation types and error registry, PL-01 complete error code metadata

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (2): FastAPI app instance, create_sample_documents

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (2): get_budget_status endpoint, AdmissionPipeline.get_budget_status

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (2): get_receipt endpoint, AdmissionPipeline.get_receipt

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (2): LEASE_HELD, Lease

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (2): POLICY_BLOCKED, conflict_resolution_strategy

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (2): SESSION_STALE_VIEW, SESSION_MONOTONIC

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (2): READ_YOUR_WRITES, READ_FRESHNESS_UNAVAILABLE

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (2): budget_gateway_vs_intent_layer, BudgetProfile

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (2): QUEUE_REQUIRED, Token

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (2): AgentClass, NOT_AUTHORIZED_FOR_AGENT_CLASS

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (2): CapabilitySet, OVERRIDE_DENIED

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Budget profile and ledger

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Stage 3 TrustGate

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Stage 9 Execution delegate to host

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Docker build validation and health probe sequence

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): MCP to CONCORD admission bridge process

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): MCP readiness Experimental Beta Production

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): DISABLED vs UNAVAILABLE vs COMPLETED flags

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Container networking service names not localhost

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): upload_file endpoint

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): InMemoryReceiptStore

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): InMemoryIntentStore

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): ASYNC_PROJECTION

## Knowledge Gaps
- **125 isolated node(s):** `CONCORD governance and admission pipeline`, `AgentClass and trust tiers`, `ActionContract capability contract`, `Budget profile and ledger`, `Intent admission unit` (+120 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 21`** (2 nodes): `Stage 2 ActionResolution`, `ACTION_DISABLED and ACTION_UNAVAILABLE v0.5.1`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (2 nodes): `Stage 6 InputValidation JSON Schema 2020-12`, `Normative file/resource parameter naming v0.5.1`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (2 nodes): `Admission boundary stages 1-8 no host side effects`, `Sequential fail-fast governance philosophy`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `Deployment Agent infrastructure actor`, `Name-derived deterministic host ports`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (2 nodes): `SessionConstraints expiring_soon near_max_lifetime`, `POST /session/refresh auditable extension`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (2 nodes): `Stage 1 SessionResolution`, `Admission and execution error codes v0.5`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (2 nodes): `B1 MCP connection to CONCORD Session 1:1`, `AgentClass and trust tiers`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (2 nodes): `agent_should required on all catalog entries`, `CONCORD errors as MCP isError structuredContent`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (2 nodes): `CONCORD governance and admission pipeline`, `CONCORDwhitepaper.md`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (2 nodes): `Phase 0 foundation types and error registry`, `PL-01 complete error code metadata`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (2 nodes): `FastAPI app instance`, `create_sample_documents`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `get_budget_status endpoint`, `AdmissionPipeline.get_budget_status`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (2 nodes): `get_receipt endpoint`, `AdmissionPipeline.get_receipt`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (2 nodes): `LEASE_HELD`, `Lease`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (2 nodes): `POLICY_BLOCKED`, `conflict_resolution_strategy`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (2 nodes): `SESSION_STALE_VIEW`, `SESSION_MONOTONIC`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (2 nodes): `READ_YOUR_WRITES`, `READ_FRESHNESS_UNAVAILABLE`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (2 nodes): `budget_gateway_vs_intent_layer`, `BudgetProfile`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (2 nodes): `QUEUE_REQUIRED`, `Token`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (2 nodes): `AgentClass`, `NOT_AUTHORIZED_FOR_AGENT_CLASS`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (2 nodes): `CapabilitySet`, `OVERRIDE_DENIED`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Budget profile and ledger`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Stage 3 TrustGate`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Stage 9 Execution delegate to host`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Docker build validation and health probe sequence`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `MCP to CONCORD admission bridge process`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `MCP readiness Experimental Beta Production`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `DISABLED vs UNAVAILABLE vs COMPLETED flags`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Container networking service names not localhost`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `upload_file endpoint`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `InMemoryReceiptStore`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `InMemoryIntentStore`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `ASYNC_PROJECTION`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Session` connect `Community 3` to `Community 2`, `Community 7`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `AdmissionPipeline` connect `Community 2` to `Community 3`, `Community 6`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `AdmissionPipeline.process_intent` connect `Community 5` to `Community 1`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `AdmissionPipeline` (e.g. with `ExecutionResult` and `Intent`) actually correct?**
  _`AdmissionPipeline` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `Session` (e.g. with `InMemorySessionStore` and `InMemoryReceiptStore`) actually correct?**
  _`Session` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `AdmissionPipeline.process_intent` (e.g. with `submit_intent endpoint` and `_stage_session_resolution`) actually correct?**
  _`AdmissionPipeline.process_intent` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `ExecutionResult` (e.g. with `InMemorySessionStore` and `InMemoryReceiptStore`) actually correct?**
  _`ExecutionResult` has 9 INFERRED edges - model-reasoned connections that need verification._