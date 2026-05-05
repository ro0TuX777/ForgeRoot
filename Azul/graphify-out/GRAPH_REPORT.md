# Graph Report - .  (2026-05-04)

## Corpus Check
- Corpus is ~37,923 words - fits in a single context window. You may not need a graph.

## Summary
- 1026 nodes · 2922 edges · 21 communities detected
- Extraction: 50% EXTRACTED · 50% INFERRED · 0% AMBIGUOUS · INFERRED: 1447 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
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
- [[_COMMUNITY_Community 20|Community 20]]

## God Nodes (most connected - your core abstractions)
1. `TicketStatus` - 151 edges
2. `AzulTicketStore` - 144 edges
3. `XPLedger` - 117 edges
4. `TicketType` - 98 edges
5. `AzulTicket` - 70 edges
6. `verify()` - 61 edges
7. `AzulWorkerPool` - 59 edges
8. `TrainingPairStore` - 57 edges
9. `TicketPriority` - 54 edges
10. `AzulAPIHandler` - 53 edges

## Surprising Connections (you probably didn't know these)
- `Existing Framework Calls` --semantically_similar_to--> `Framework Integration Points`  [INFERRED] [semantically similar]
  Azul_AI_Dev_Briefing.md → Azul_Core_Specification.md
- `Contract and Policy Drift Scanner` --conceptually_related_to--> `Framework Integration Points`  [INFERRED]
  azul/tests/test_loop_drift_scanner.py → Azul_Core_Specification.md
- `tmp_store()` --calls--> `AzulTicketStore`  [INFERRED]
  tests\test_daemon.py → ticket_store.py
- `tmp_store()` --calls--> `AzulTicketStore`  [INFERRED]
  tests\test_verification_engine.py → ticket_store.py
- `tmp_pair_store()` --calls--> `TrainingPairStore`  [INFERRED]
  tests\test_verification_engine.py → training_pairs.py

## Hyperedges (group relationships)
- **Verification Pipeline Flow** — verification_engine_forge_scaffold_phase, verification_engine_governance_guard_phase, verification_engine_forge_harbor_phase, verification_engine_forge_works_phase, verification_engine_gate_evaluation_phase, verification_engine_final_verdict_phase [EXTRACTED 1.00]
- **Ticket Submission Adapters** — api_api_handler, ci_webhook_ci_webhook_adapter, cli_cli_adapter, distillation_distillation_adapter, event_event_adapter [INFERRED 0.86]
- **Reward and Training Outputs** — verification_engine_final_verdict_phase, xp_ledger_xp_calculation, xp_ledger_xp_ledger, training_pairs_training_pair_emission, training_pairs_training_pair_store [EXTRACTED 0.94]
- **Forge Framework Integrations** — forge_atlas_discover_actions, forge_harbor_request_environment, forge_scaffold_analyze_blast_radius, forge_works_execute_verification [EXTRACTED 1.00]
- **Recursive Improvement Loop** — orchestrator_loop_orchestrator, pattern_analyzer_pattern_analyzer, drift_scanner_drift_scanner, recommender_improvement_recommender, applier_improvement_applier, gold_labels_gold_label_store [EXTRACTED 1.00]
- **QA Lifecycle Contract** — test_integration_full_lifecycle, test_gate_severity_policy, test_daemon_reconciliation, test_governance_subprocess_guards, test_adapters_adapter_contract [INFERRED 0.80]
- **Verification Pipeline Contract** — azul_core_specification_entry_adapters, azul_core_specification_verification_engine, azul_core_specification_fw_result_gate, azul_core_specification_verdict_reward [EXTRACTED 1.00]
- **Implemented Core Test Surface** — test_lifecycle_status_machine_tests, test_ticket_store_ticket_persistence, test_xp_ledger_xp_formula, test_training_pairs_training_pair_emission, test_spec_builder_planner_spec_contract, test_verification_engine_verify_flow [INFERRED 0.90]
- **Closed Loop Learning Feedback** — test_loop_orchestrator_loop_orchestrator, test_loop_gold_labels_gold_label_store, test_loop_drift_scanner_contract_policy_drift, test_loop_orchestrator_distillation_batch, azulwhitepaper_xp_training_distillation [INFERRED 0.84]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.03
Nodes (163): AzulAPIHandler, adapters/api.py — Lightweight HTTP-style API adapter ===========================, Return a stored ticket by ID., List tickets with optional status / type filter., Health check endpoint — always returns ok in Phase 4 (Phase 5 adds queue depth)., Stateless request handler.  Injected with a store and ledger on creation.      U, Dispatch a request dict to the appropriate action handler.         Never raises., Submit a change for verification and return the verdict synchronously. (+155 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (101): _error(), _get_daemon(), _ok(), integrations/forge_harbor.py — ForgeHarbor environment management ==============, Reset the module-level singleton (for testing)., Load and return the ForgeHarbor daemon singleton (importlib Pattern 1)., Request a warm environment for the given ticket.      Returns _ok({"environment_, Release an environment back to the pool.     Always called — even on failure pat (+93 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (39): _apply(), begin_analysis(), begin_evaluation(), begin_gating(), begin_provisioning(), can_transition(), complete(), fail() (+31 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (38): _err(), _ok(), _build_change_summary(), _derive_priority(), _detect_provider(), _github_repo_slug(), handle_webhook(), _post_commit_status() (+30 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (29): get_domain_config(), domain_config.py — Per-domain oracle/scoring/mode configuration  (P1-3) ========, Return configuration for the given domain.     Falls back to ci_change_control d, Return the oracle path for the given domain., Return the scoring path for the given domain., Return the default mode for the given domain., Return True if this domain requires ForgeScaffold blast-radius analysis., requires_blast_radius() (+21 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (32): AzulResultGate, GateResult, get_azul_result_gate(), gate.py — AzulResultGate  (P0-4) ================================= Extracted and, Return the module-level singleton AzulResultGate., Result of evaluating a ReviewBundle against a gate policy., Evaluates a ForgeWorks ReviewBundle dict against a configurable policy     and r, Evaluate a ReviewBundle against the given policy.          Args:             rev (+24 more)

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (53): Apply Ledger, Contract Stub Queue, Distillation Ready Signal, Human Review Gate, Improvement Applier, Improvement Plan, Policy Pending Queue, Pending Prompt Draft Queue (+45 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (51): Core Flow, Existing Framework Calls, Gate Policy, XP System, Entry Adapters, Framework Integration Points, FWResultGate, Status Machine (+43 more)

### Community 8 - "Community 8"
Cohesion: 0.07
Nodes (48): API Handler Adapter, CI Webhook Adapter, CI Commit Status Posting, CLI Adapter, Recursive Loop CLI Commands, Azul Configuration, Azul Data Directories, Azul Daemon (+40 more)

### Community 9 - "Community 9"
Cohesion: 0.11
Nodes (11): verify(), make_ticket(), TestFeatureFlags, TestHappyPath, TestOperationalFailures, TestRejection, TestTrainingPairEmission, TestWarning (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (8): handler(), _make_verify_mock(), mock_verify(), TestApiHandler, TestCiWebhook, TestCliAdapter, TestDistillationAdapter, TestEventAdapter

### Community 11 - "Community 11"
Cohesion: 0.15
Nodes (20): _default_catalog_root(), evaluate_diff_against_subprocess_guards(), evaluate_no_destructive_remediation(), _extract_command_candidates(), _extract_core_export_name(), _literal_or_unknown(), load_subprocess_rules(), _load_yaml() (+12 more)

### Community 12 - "Community 12"
Cohesion: 0.19
Nodes (5): send_socket_request(), TestDaemonLifecycle, TestSocketListener, tmp_ledger(), tmp_store()

### Community 13 - "Community 13"
Cohesion: 0.21
Nodes (4): make_ticket(), TestStats, TestSubmission, TestWaitForResult

### Community 14 - "Community 14"
Cohesion: 0.24
Nodes (8): discover_actions(), _get_atlas(), _ok(), integrations/forge_atlas.py — ForgeAtlas action discovery (P2-3) ===============, Reset the module-level singleton (for testing)., Load ForgeAtlas run module once (importlib Pattern 1)., Discover available actions for the verification task context.      Returns _ok({, reset_module()

### Community 15 - "Community 15"
Cohesion: 0.27
Nodes (9): analyze_blast_radius(), compute_blast_radius_score(), _error(), _ok(), integrations/forge_scaffold.py — ForgeScaffold blast-radius analysis ===========, Compute a weighted blast radius score using BFS over the dataflow edge graph., Return units whose path overlaps with any target_file., Map the blast radius of the given target_files in the project.      Args: (+1 more)

### Community 16 - "Community 16"
Cohesion: 0.32
Nodes (5): _metric(), telemetry.py — CONCORD telemetry emitter  (P3-1) ===============================, Append one per-verification telemetry record.         Called by the daemon after, POST a metric record to the CONCORD telemetry endpoint., _ts()

### Community 17 - "Community 17"
Cohesion: 0.39
Nodes (3): _error(), _ok(), mocks/mock_integrations.py — Fake implementations of all 3 integrations ========

### Community 18 - "Community 18"
Cohesion: 0.5
Nodes (2): Return all telemetry records., Return aggregated metrics, optionally filtered.          Returns:             {

### Community 19 - "Community 19"
Cohesion: 0.5
Nodes (4): Action Discovery, Azul Verification Capability Set, Discover Actions, ForgeAtlas Runner

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): Deserialize from a plain dict (as produced by ``to_dict()``).

## Ambiguous Edges - Review These
- `Blast Radius` → `Gate Severity Policy Tests`  [AMBIGUOUS]
  azul/integrations/forge_scaffold.py · relation: conceptually_related_to

## Knowledge Gaps
- **101 isolated node(s):** `config.py — Azul configuration ================================ Reads environmen`, `Create all persistent data directories if they do not already exist.`, `domain_config.py — Per-domain oracle/scoring/mode configuration  (P1-3) ========`, `Return configuration for the given domain.     Falls back to ci_change_control d`, `Return the oracle path for the given domain.` (+96 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 18`** (4 nodes): `Return all telemetry records.`, `Return aggregated metrics, optionally filtered.          Returns:             {`, `.load_records()`, `.summary()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (1 nodes): `Deserialize from a plain dict (as produced by ``to_dict()``).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Blast Radius` and `Gate Severity Policy Tests`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `TicketStatus` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 9`, `Community 10`, `Community 12`, `Community 13`?**
  _High betweenness centrality (0.134) - this node is a cross-community bridge._
- **Why does `verify()` connect `Community 9` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 11`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Why does `AzulTicketStore` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 9`, `Community 10`, `Community 12`, `Community 13`?**
  _High betweenness centrality (0.083) - this node is a cross-community bridge._
- **Are the 146 inferred relationships involving `TicketStatus` (e.g. with `AzulDaemon` and `daemon.py — Azul long-running daemon process  (P2-2) ===========================`) actually correct?**
  _`TicketStatus` has 146 INFERRED edges - model-reasoned connections that need verification._
- **Are the 132 inferred relationships involving `AzulTicketStore` (e.g. with `AzulDaemon` and `daemon.py — Azul long-running daemon process  (P2-2) ===========================`) actually correct?**
  _`AzulTicketStore` has 132 INFERRED edges - model-reasoned connections that need verification._
- **Are the 111 inferred relationships involving `XPLedger` (e.g. with `AzulDaemon` and `daemon.py — Azul long-running daemon process  (P2-2) ===========================`) actually correct?**
  _`XPLedger` has 111 INFERRED edges - model-reasoned connections that need verification._